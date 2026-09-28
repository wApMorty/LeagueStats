"""Capture brute des parties SoloQ/Flex (SPEC-19 §8, tâche 30).

Le brut est la source de vérité : les métriques en seront recalculées. Les
parties viennent de l'historique LCU, qui a ~5 min de retard sur la fin de
partie et ne sert que 20 parties : chaque passage capture toutes celles qui
manquent, au démarrage (rattrapage) comme pendant l'après-partie.

L'écran de fin (`raw_eog`) disparaît dès la draft suivante, bien avant que
l'historique ait la partie : il est mis de côté en mémoire à chaque passage,
puis rangé avec la partie. Seule source fiable du poste de chaque joueur.

Best-effort, comme src/draft/outcome_tracker.py : rien ici n'interrompt la
boucle du Live Coach.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Dict

from ..config_constants import coaching_config
from . import ranked

# Jetons de session du chat d'après-partie : jamais stockés.
EOG_SECRET_KEYS = ("mucJwtDto", "multiUserChatPassword")


class GameCapture:
    """Capture des parties et photos de classement pour le coach de gameplay."""

    def __init__(self, monitor) -> None:
        self.m = monitor
        self._eog_by_game: Dict[int, str] = {}
        self._warned_missing_tables = False

    def on_startup(self) -> None:
        """Rattrapage des parties jouées app fermée, et photo du classement."""
        self._safely(self.capture_recent)
        self._safely(lambda: ranked.snapshot_current(self.m.lcu, self.m.assistant.db))

    def on_post_game(self) -> None:
        """Un passage de la fenêtre d'après-partie."""
        self._safely(self.remember_end_of_game)
        self._safely(lambda: ranked.snapshot_after_game(self.m.lcu, self.m.assistant.db))
        self._safely(self.capture_recent)

    def remember_end_of_game(self) -> None:
        """Met de côté l'écran de fin d'une partie classée, sans ses secrets."""
        block = self.m.lcu.get_end_of_game_block()
        if not block or block.get("queueType") not in coaching_config.RANKED_QUEUES:
            return
        clean = {key: value for key, value in block.items() if key not in EOG_SECRET_KEYS}
        self._eog_by_game[block["gameId"]] = json.dumps(clean)

    def capture_recent(self) -> int:
        """Capture les parties SoloQ/Flex de l'historique absentes de la base."""
        lcu, db = self.m.lcu, self.m.assistant.db
        captured_ids = db.get_captured_game_ids()
        count = 0
        for match in lcu.get_recent_matches(coaching_config.HISTORY_DEPTH):
            game_id = match["game_id"]
            if match["queue_id"] not in coaching_config.QUEUE_IDS or game_id in captured_ids:
                continue
            game = lcu.get_game_detail(game_id)
            if not game or not game.get("participants"):
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
                raw_eog=self._eog_by_game.pop(game_id, None),
            )
            count += int(inserted)
        if count:
            print(f"[DATA] Coach de gameplay : {count} partie(s) capturée(s)")
        return count

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
        if getattr(self.m, "verbose", False):
            print(f"[WARNING] Capture de partie : {error}")
