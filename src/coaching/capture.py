"""Capture brute des parties SoloQ/Flex (SPEC-19 §8, tâche 30).

Le brut est la source de vérité : les métriques en seront recalculées. Les
parties viennent de l'historique LCU, qui a ~5 min de retard sur la fin de
partie et ne sert que 20 parties : chaque passage capture toutes celles qui
manquent, au démarrage (rattrapage) comme pendant l'après-partie.

L'écran de fin (`raw_eog`) disparaît dès la draft suivante, bien avant que
l'historique ait la partie : il est mis de côté en mémoire à chaque passage,
puis rangé avec la partie. Seule source fiable du poste de chaque joueur.

Chaque passage enchaîne sur l'analyse des parties nouvellement capturées
(findings.py) : rapport de fin de partie en direct, synthèse au démarrage.

La lecture des deux endpoints transitoires (écran de fin, notification de LP) se sépare de
l'écriture en base (SPEC-25) : `read_transients` ne touche pas à la base et tourne dans le fil de
`PostGameWatcher`, cadencé par la phase gameflow et non par la boucle du monitor ; `on_post_game`,
dans le fil du coach, écrit ce qui a été mis de côté.

Best-effort, comme src/draft/outcome_tracker.py : rien ici n'interrompt la
boucle du Live Coach.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Set

from ..config_constants import coaching_config
from ..draft.final_analysis import _to_points as to_points
from ..repositories.coaching import CoachingRepository
from ..winprob.pending import compute_pending
from . import findings, goals, ranked, report

# Jetons de session du chat d'après-partie : jamais stockés.
EOG_SECRET_KEYS = ("mucJwtDto", "multiUserChatPassword")


class GameCapture:
    """Capture des parties et photos de classement pour le coach de gameplay."""

    def __init__(self, monitor) -> None:
        self.m = monitor
        self._eog_by_game: Dict[int, str] = {}
        self._lp_by_game: Dict[int, dict] = {}  # notification de LP mise de côté, pas encore écrite
        self._lock = threading.Lock()  # le fil de PostGameWatcher et celui du coach s'y croisent
        self._warned_missing_tables = False
        self._alerted: Set[str] = set()

    def on_startup(self) -> None:
        """Rattrapage des parties jouées app fermée, et photo du classement."""
        self._safely(self.capture_recent)
        self._safely(lambda: ranked.snapshot_current(self.m.lcu, self.m.assistant.db))
        self._safely(lambda: self.analyze(live=False))
        self._safely(lambda: self.impact(live=False))

    def on_post_game(self) -> None:
        """Un passage de la fenêtre d'après-partie."""
        known = self._captured_ids()
        self.read_transients()  # filet : le fil de PostGameWatcher les a déjà lues en général
        self._safely(self.write_lp_snapshots)
        self._safely(self.capture_recent)
        self._safely(lambda: self.analyze(live=True))
        self._safely(lambda: self.impact(live=True))
        self._safely(lambda: self._announce(known))

    def read_transients(self, lcu=None) -> None:
        """Met de côté l'écran de fin et la notification de LP, sans toucher à la base.

        Ils ne répondent que sur l'écran de fin (SPEC-19, SPEC-25 §4.0) : appelé par le fil de
        `PostGameWatcher` avec son propre client LCU, et par la boucle du monitor avec le sien.
        """
        self._safely(lambda: self.remember_end_of_game(lcu))
        self._safely(lambda: self.remember_lp_notification(lcu))

    def on_lcu_event(self, event: dict) -> None:
        """Événement WebSocket du client LoL (fil du tracker de phase) : la notification de LP est
        mise de côté dès qu'elle naît, sans attendre une lecture. Ne touche pas à la base."""
        if event.get("uri") != ranked.LP_NOTIFICATION_URI:
            return
        note = ranked.valid_notification(event.get("data"))
        if note is not None:
            with self._lock:
                self._lp_by_game[note["gameId"]] = note

    def write_lp_snapshots(self) -> None:
        """Écrit les notifications de LP mises de côté ; celle qu'une base verrouillée a refusée
        reste en mémoire et repart au passage suivant."""
        with self._lock:
            pending = dict(self._lp_by_game)
        for game_id, note in pending.items():
            ranked.snapshot_after_game(note, self.m.assistant.db)
            with self._lock:
                self._lp_by_game.pop(game_id, None)

    @property
    def _client_mode(self) -> bool:
        """Le client LeagueStats est branché : sa page de revue remplace le rapport console (SPEC-21 §4.5)."""
        return getattr(self.m, "bus", None) is not None

    def _captured_ids(self) -> Set[int]:
        try:
            return set(self.m.assistant.db.get_captured_game_ids())
        except Exception:  # best-effort : ne pas annoncer à tort vaut mieux que planter
            return set()

    def _announce(self, known: Set[int]) -> None:
        """Annonce au client la partie qui vient d'être capturée (sujet `game_captured`) ; la plus
        récente si le passage en a pris plusieurs (les identifiants de partie croissent avec le temps).
        """
        bus = getattr(self.m, "bus", None)
        fresh = self._captured_ids() - known
        if bus is not None and fresh:
            bus.publish("game_captured", {"game_id": max(fresh)})

    def analyze(self, live: bool) -> None:
        """Analyse les parties capturées (tâches 34 à 38).

        En direct, chaque partie a son rapport ; au démarrage (rattrapage, ou
        recalcul après un changement de grille), une ligne de synthèse suffit.
        """
        db = self.m.assistant.db
        repo = CoachingRepository(db)
        analyses = findings.analyze_pending(db)
        for analysis in analyses:
            lines = goals.judge(repo, analysis)
            if live and not self._client_mode:
                lines = self._game_report(analysis) + lines
            for line in lines:
                print(line)
        if not analyses:
            return
        if not live:
            print(f"[DATA] Coach de gameplay : {len(analyses)} partie(s) analysée(s)")
        proposal = goals.propose(repo, analyses[-1].role) if analyses[-1].role else None
        if proposal:
            print(proposal)
        total = sum(repo.player_roles().values())
        every = coaching_config.REVIEW_EVERY
        if live and total // every > (total - len(analyses)) // every:
            print("\n".join(report.review(db)))

    def impact(self, live: bool) -> None:
        """Impact sur la win chance des parties capturées (SPEC-20) ; en direct, le rapport de la dernière."""
        reports = compute_pending(self.m.assistant.db)
        if live and reports and not self._client_mode:
            print("\n".join([""] + reports[-1][1]))

    def _game_report(self, analysis) -> list:
        db = self.m.assistant.db

        def name_of(champion_id: int) -> str:
            return db.get_champion_by_id(champion_id) or f"Champion{champion_id}"

        duel = None
        evaluator = getattr(self.m, "evaluator", None)
        if evaluator and analysis.role and analysis.opponent_champion_id:
            me = (name_of(analysis.champion_id), analysis.role)
            them = (name_of(analysis.opponent_champion_id), analysis.role)
            if evaluator.has_matchup_data(me, them):
                duel = to_points(evaluator.matchup_logit(me, them))
        predicted = CoachingRepository(db).predicted_probability(analysis.game_id)
        return [""] + report.game_report(analysis, name_of, predicted, duel)

    def remember_end_of_game(self, lcu=None) -> None:
        """Met de côté l'écran de fin d'une partie classée, sans ses secrets."""
        block = (lcu or self.m.lcu).get_end_of_game_block()
        if not block or block.get("queueType") not in coaching_config.RANKED_QUEUES:
            return
        clean = {key: value for key, value in block.items() if key not in EOG_SECRET_KEYS}
        with self._lock:
            self._eog_by_game[block["gameId"]] = json.dumps(clean)

    def remember_lp_notification(self, lcu=None) -> None:
        """Met de côté la notification de LP de la partie classée qui vient de finir."""
        note = ranked.valid_notification((lcu or self.m.lcu).get_lp_change_notification())
        if note is not None:
            with self._lock:
                self._lp_by_game[note["gameId"]] = note

    def capture_recent(self) -> int:
        """Capture les parties SoloQ/Flex de l'historique absentes de la base."""
        lcu, db = self.m.lcu, self.m.assistant.db
        captured_ids = db.get_captured_game_ids()
        matches = {m["game_id"]: m for m in lcu.get_recent_matches(coaching_config.HISTORY_DEPTH)}
        # Seule la liste de l'historique a ~5 min de retard : le détail et la
        # timeline d'une partie de l'écran de fin sont servis tout de suite
        # (mesuré le 2026-09-30). Sans ça, le rapport arrivait pendant, voire
        # après, la partie suivante.
        with self._lock:
            eog_by_game = dict(self._eog_by_game)
        for game_id in eog_by_game:
            matches.setdefault(game_id, None)
        count = 0
        for game_id, match in matches.items():
            if game_id in captured_ids or (
                match and match["queue_id"] not in coaching_config.QUEUE_IDS
            ):
                continue
            game = lcu.get_game_detail(game_id)
            if not game or not game.get("participants"):
                continue
            match = match or self._match_from_detail(game, eog_by_game.get(game_id))
            if not match or match["queue_id"] not in coaching_config.QUEUE_IDS:
                continue
            duration_s = game.get("gameDuration") or 0
            timeline = lcu.get_game_timeline(game_id)
            if not (timeline and timeline.get("frames")):
                timeline = None
                ended_ms = match["game_creation_ms"] + duration_s * 1000
                age_s = datetime.now(timezone.utc).timestamp() - ended_ms / 1000
                if age_s < coaching_config.TIMELINE_GRACE_S:
                    continue  # sans doute pas encore servie : prochain passage
            inserted = db.insert_game_record(
                game_id=game_id,
                queue_id=match["queue_id"],
                game_creation_utc=datetime.fromtimestamp(
                    match["game_creation_ms"] / 1000, tz=timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S"),
                duration_s=duration_s,
                player_participant_id=match.get("participant_id"),
                raw_game=json.dumps(game),
                raw_timeline=json.dumps(timeline) if timeline else None,
                raw_eog=eog_by_game.get(game_id),
            )
            with self._lock:
                self._eog_by_game.pop(game_id, None)
            count += int(inserted)
        if count:
            print(f"[DATA] Coach de gameplay : {count} partie(s) capturée(s)")
        return count

    def _match_from_detail(self, game: dict, raw_eog: Optional[str]) -> Optional[dict]:
        """Les champs de get_recent_matches utiles à la capture, depuis le
        détail ; le joueur est retrouvé par le puuid de l'écran de fin."""
        eog = json.loads(raw_eog or "{}")
        puuid = (eog.get("localPlayer") or {}).get("puuid")
        participant_id = next(
            (
                identity["participantId"]
                for identity in game.get("participantIdentities") or []
                if puuid and (identity.get("player") or {}).get("puuid") == puuid
            ),
            None,
        )
        if participant_id is None:
            return None  # la liste de l'historique prendra le relais
        return {
            "game_creation_ms": game["gameCreation"],
            "queue_id": game.get("queueId"),
            "participant_id": participant_id,
        }

    def _safely(self, step: Callable[[], object]) -> None:
        try:
            step()
        except sqlite3.OperationalError as e:
            if "no such table" not in str(e):
                self._warn(e)
            elif not self._warned_missing_tables:
                self._warned_missing_tables = True
                print(
                    "[ALERTE] Coach de gameplay : base non migrée, parties non capturées. "
                    "Lancez `python -m alembic upgrade head`."
                )
        except Exception as e:
            self._warn(e)

    def _warn(self, error: Exception) -> None:
        """Chaque erreur distincte s'affiche une fois, même hors `-v` : une capture qui échoue ne se
        distinguerait sinon pas d'un écran de fin manqué (SPEC-25)."""
        message = f"{type(error).__name__}: {error}"
        with self._lock:
            first = message not in self._alerted
            self._alerted.add(message)
        if first:
            print(f"[ALERTE] Capture de partie : {message}")
        elif getattr(self.m, "verbose", False):
            print(f"[WARNING] Capture de partie : {message}")
