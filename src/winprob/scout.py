"""Éclaireur des joueurs en partie (SPEC-33 §4.3).

Dès l'écran de chargement, lit l'historique des dix joueurs (forme brute, un à la fois : le LCU les sert
un par un), puis leurs parties classées par rang (la plus récente de chacun, puis la deuxième...) pour en
tirer l'impact ΔP de SPEC-20 (bancs des 2026-10-13 et 2026-10-15, SPEC-33 §7).

- Un pool de threads (`ThreadPoolExecutor`) ne fait que les requêtes LCU et le calcul d'impact ; son
  client LCU a une session à pool dimensionné et un statut HTTP par thread (SPEC-33 tâche 151).
- Un fil coordinateur (`step()`, toutes les `SCOUT_TICK_S`) récolte, range dans `crawl.db`, publie le
  sujet `players`. Aucune écriture SQLite hors de ce fil : chaque fil a sa connexion (`Crawler._db`).
- Une partie déjà dans `crawl.db` est servie sans requête ; une partie lue y est rangée.
- La collecte se tait tant que l'éclaireur est actif (`Crawler._paused`).

Chaque lancement (`start`) crée un `_Run` neuf : `stop()`, appelé depuis la boucle du Live Coach, ne fait
qu'en détacher la référence et fermer son pool, sans attendre le fil coordinateur. Best-effort : rien ici
n'interrompt le Live Coach.
"""

import threading
import time
from concurrent.futures import Executor, Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..config_coaching import coaching_config
from ..config_winprob import winprob_config as cfg
from ..lcu_client import LCUClient
from . import live
from .crawl import store_game, store_history, unpack
from .form import form, player_impact, ranked_games
from .model import WinModel
from .train import load_model

TOPIC = "players"

# Résultat d'une tâche du pool : (valeur, statut HTTP lu dans le worker, [(type de requête, secondes)]).
TaskResult = Tuple[Any, Optional[int], List[Tuple[str, float]]]


def _seconds(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}"


class _Run:
    """Un éclairage : les dix joueurs d'une partie, du premier historique à la dernière partie lue."""

    def __init__(self, scout: "Scout", players: List[dict], executor: Executor, own: bool) -> None:
        self.s = scout
        self.players = {p["puuid"]: p for p in players}
        self.executor = executor
        self.own_executor = own
        self.t0 = scout._clock()
        self.active = True
        self.closed = False
        self.in_flight: Dict[Future, Tuple[str, Any]] = {}
        self.histories: Dict[str, Optional[List[dict]]] = {}  # None : historique en échec
        self.to_ask = list(self.players)  # historiques pas encore demandés
        self.cursor: Dict[str, int] = {p: 0 for p in self.players}  # rang de la prochaine partie
        self.claimed: Dict[str, set] = {p: set() for p in self.players}  # parties soumises pour lui
        self.unavailable: set = set()  # parties illisibles : pas de nouvelle requête
        self.idle = False  # dernière soumission : plus rien à lancer pour l'instant
        self.impacts: Dict[str, Dict[int, float]] = {p: {} for p in self.players}
        self.resolved: Dict[str, set] = {p: set() for p in self.players}
        self.throttled = False
        self.in_game = False
        self.next_live = 0.0
        self.stats: Dict[str, Any] = {
            "requests": 0,
            "errors": 0,
            "throttled": 0,
            "games": 0,
            "cache_hits": 0,
            "timings": {"history": [], "detail": [], "timeline": []},
            "forms_s": None,
            "impacts_s": None,
            "loading_s": None,
        }
        self.logged = False

    # ---------- fil coordinateur ----------

    def step(self) -> bool:
        """Un tour : récolte, lecture de la fin du chargement, soumissions. True si l'état a changé."""
        changed = self._harvest()
        self._watch_loading()
        self._submit()
        if not self.in_flight and self._nothing_left():
            self.active = False
            self.close()
            changed = True
        return changed

    def _harvest(self) -> bool:
        done = [f for f in self.in_flight if f.done()]
        if not done:
            return False
        db = self.s.crawler._db()
        for future in done:
            kind, key = self.in_flight.pop(future)
            try:
                value, status, timings = future.result()
            except Exception:  # pylint: disable=broad-exception-caught
                value, status, timings = None, None, []
            for request, seconds in timings:
                self.stats["timings"][request].append(seconds)
            self.stats["requests"] += len(timings)
            if status == 429:
                self._throttle()
            elif value is None:
                self.stats["errors"] += 1
            if kind == "history":
                self.histories[key] = value
                if value is not None:
                    store_history(db, key, value)
                    self.s.crawler.mark_visited(key, value[0]["creation_ms"] if value else 0)
            else:
                game_id, puuids = key
                self.stats["games"] += 1
                if value is None and status != 429:
                    self.unavailable.add(game_id)
                if value is not None:
                    if "game" in value:
                        store_game(db, value["game"], value["timeline"], 1)
                    for puuid, points in value["impacts"].items():
                        self.impacts[puuid][game_id] = points
                for puuid in puuids:
                    self.resolved[puuid].add(game_id)
        db.commit()
        self._note_times()
        return True

    def _note_times(self) -> None:
        elapsed = self.s._clock() - self.t0
        if self.stats["forms_s"] is None and len(self.histories) == len(self.players):
            self.stats["forms_s"] = elapsed
        all_known = len(self.histories) == len(self.players)
        if self.stats["impacts_s"] is None and all_known and not self.throttled:
            badge = cfg.SCOUT_BADGE_WINDOW
            if all(
                {g["game_id"] for g in (self.histories[p] or [])[:badge]} <= self.resolved[p]
                for p in self.players
            ):
                self.stats["impacts_s"] = elapsed

    def _watch_loading(self) -> None:
        """Fin du chargement : premier `gameTime` > 0 de la Live Client API, lue au plus une fois par
        `SCOUT_LIVE_POLL_S` ; ensuite plus aucune lecture."""
        now = self.s._clock()
        if self.in_game or now < self.next_live:
            return
        self.next_live = now + cfg.SCOUT_LIVE_POLL_S
        data = self.s._fetch() or {}
        if float((data.get("gameData") or {}).get("gameTime") or 0) > 0:
            self.in_game = True
            self.stats["loading_s"] = now - self.t0

    def _submit(self) -> None:
        """Historiques d'abord, `SCOUT_HISTORY_WORKERS` à la fois (le LCU les sert un par un) ; le reste
        du pool lit les parties des joueurs dont l'historique est revenu."""
        limit = cfg.SCOUT_IN_GAME_WORKERS if self.in_game else cfg.SCOUT_WORKERS
        self.idle = False
        while len(self.in_flight) < limit and not self.throttled:
            histories = sum(kind == "history" for kind, _ in self.in_flight.values())
            if self.to_ask and histories < cfg.SCOUT_HISTORY_WORKERS:
                puuid = self.to_ask.pop(0)
                self._send(("history", puuid), self.s._read_history, puuid)
                continue
            found = self._next_game()
            if found is None:
                self.idle = True
                return
            game_id, puuids = found
            row = (
                self.s.crawler._db()
                .execute(
                    "SELECT raw FROM crawl_games WHERE game_id = ? AND length(raw) > 0", (game_id,)
                )
                .fetchone()
            )
            if row:
                self.stats["cache_hits"] += 1
                self._send(("game", (game_id, puuids)), self.s._cached_game, row[0], puuids)
            else:
                self._send(("game", (game_id, puuids)), self.s._read_game, game_id, puuids)

    def _send(self, key: Tuple[str, Any], work: Callable[..., TaskResult], *args: Any) -> None:
        self.in_flight[self.executor.submit(work, *args)] = key

    def _next_game(self) -> Optional[Tuple[int, List[str]]]:
        """La prochaine partie à lire, une fois les dix historiques revenus : lues en même temps, les
        parties ralentissaient les historiques (banc du 2026-10-15, formes en 17,6 s au lieu de 3,6 s).
        Le plus petit rang d'abord (à rang égal, l'ordre des joueurs). Une partie déjà soumise, lue ou
        illisible est sautée ; une partie en vol pour un autre joueur est attendue (elle sera ensuite
        servie par le cache). La partie est soumise pour tous les joueurs qui l'ont jouée.
        Sans modèle de win chance, aucun impact à calculer : aucune partie à lire."""
        if self.s._model is None or len(self.histories) < len(self.players):
            return None
        depth = max(cfg.SCOUT_WINDOWS)
        flying = {key[0] for kind, key in self.in_flight.values() if kind == "game"}
        best: Optional[Tuple[int, str]] = None
        for puuid in self.players:
            games = (self.histories.get(puuid) or [])[:depth]
            while self.cursor[puuid] < len(games):
                game_id = games[self.cursor[puuid]]["game_id"]
                if game_id in self.unavailable:
                    self.resolved[puuid].add(game_id)
                if game_id not in self.resolved[puuid] and game_id not in self.claimed[puuid]:
                    break
                self.cursor[puuid] += 1
            rank = self.cursor[puuid]
            if rank < len(games) and games[rank]["game_id"] not in flying:
                if best is None or rank < best[0]:
                    best = (rank, puuid)
        if best is None:
            return None
        rank, puuid = best
        game_id = self.histories[puuid][rank]["game_id"]
        players = [
            p
            for p in self.players
            if game_id in {g["game_id"] for g in (self.histories.get(p) or [])[:depth]}
            and game_id not in self.resolved[p]
            and game_id not in self.claimed[p]
        ]
        for p in players:
            self.claimed[p].add(game_id)
        return game_id, players

    def _nothing_left(self) -> bool:
        return self.throttled or (
            not self.to_ask and len(self.histories) == len(self.players) and self.idle
        )

    def _throttle(self) -> None:
        self.stats["throttled"] += 1
        if self.throttled:
            return
        self.throttled = True
        crawler = self.s.crawler
        crawler._next_at = crawler._clock() + cfg.CRAWL_BACKOFF_S  # la collecte reprend plus tard
        print("[ALERTE] Éclaireur SPEC-33 : 429 du LCU, plus aucune requête pour cette partie")

    def close(self) -> None:
        """Ferme le pool sans attendre (les tâches en attente sont annulées) et journalise une fois."""
        if self.closed:
            return
        self.closed = True
        self.active = False
        if self.own_executor:
            self.executor.shutdown(wait=False, cancel_futures=True)
        if not self.logged:
            self.logged = True
            st = self.stats
            cache = 100 * st["cache_hits"] / st["games"] if st["games"] else 0
            print(
                f"[DATA] Éclaireur : formes en {_seconds(st['forms_s'])} s, "
                f"10 impacts en {_seconds(st['impacts_s'])} s, "
                f"chargement {_seconds(st['loading_s'])} s, {st['requests']} requêtes, "
                f"{cache:.0f} % du cache"
            )

    # ---------- lecture ----------

    def snapshot(self) -> Dict[str, Any]:
        """{puuid: {champion_id, team, ready, windows: {fenêtre: forme}, pending, failed}}."""
        out = {}
        depth = max(cfg.SCOUT_WINDOWS)
        for puuid, player in self.players.items():
            games = (self.histories.get(puuid) or [])[:depth]
            out[puuid] = {
                "champion_id": player.get("champion_id"),
                "team": player.get("team"),
                "ready": puuid in self.histories,
                "windows": {
                    w: form(games, self.impacts[puuid], player.get("champion_id"), w)
                    for w in cfg.SCOUT_WINDOWS
                },
                "pending": sum(g["game_id"] not in self.resolved[puuid] for g in games),
                "failed": puuid in self.histories and self.histories[puuid] is None,
            }
        return out


class Scout:
    """L'éclaireur : `start(players)` l'arme pour une partie, `step()` le fait avancer, `stop()` l'arrête.

    `serve()` lance le fil coordinateur qui appelle `step()` toutes les `SCOUT_TICK_S` ; les tests et le
    banc appellent `step()` eux-mêmes. `executor` injecté (tests) : partagé, jamais fermé ici.
    """

    def __init__(
        self,
        monitor,
        crawler,
        executor: Optional[Executor] = None,
        clock: Callable[[], float] = time.monotonic,
        fetch: Callable[[], Optional[dict]] = live.fetch,
    ) -> None:
        self.m = monitor
        self.crawler = crawler
        self._executor = executor
        self._clock = clock
        self._fetch = fetch
        self.lcu = LCUClient()
        self.lcu.session = self.lcu.pooled_session(cfg.SCOUT_WORKERS)
        # Les historiques font la queue côté LCU : au-delà de 5 s, une file lente n'est pas une erreur.
        self.lcu.request_timeout_s = cfg.SCOUT_REQUEST_TIMEOUT_S
        # Une requête en vol rend None dès qu'une draft commence (SPEC-28).
        self.lcu.yield_if = getattr(monitor, "draft_pending", None)
        self._model: Optional[WinModel] = None
        self._model_tried = False
        self._run: Optional[_Run] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._warned = False

    @property
    def armed(self) -> bool:
        """Lancé pour la partie en cours (fini ou non) : la boucle ne relit pas la session."""
        return self._run is not None

    @property
    def active(self) -> bool:
        """Des requêtes restent à faire : la collecte se tait."""
        run = self._run
        return run is not None and run.active

    def start(self, players: List[dict]) -> None:
        """players : [{puuid, champion_id, team}] des dix ; sans effet si déjà lancé pour ces puuid."""
        run = self._run
        if run is not None and set(run.players) == {p["puuid"] for p in players}:
            return
        self.stop()
        if not self._model_tried:
            self._model, self._model_tried = load_model(), True
        self.lcu.credentials = getattr(getattr(self.m, "lcu", None), "credentials", None)
        own = self._executor is None
        executor = self._executor or ThreadPoolExecutor(
            max_workers=cfg.SCOUT_WORKERS, thread_name_prefix="scout"
        )
        self._run = _Run(self, players, executor, own)

    def step(self) -> None:
        """Un tour du coordinateur ; publie `players` si quelque chose a changé. Ne lève jamais."""
        run = self._run
        if run is None or run.closed:
            return
        try:
            if run.step() and self._run is run:
                self._publish(run.snapshot())
        except Exception as error:  # pylint: disable=broad-exception-caught
            self.crawler.rollback()  # un commit en échec garderait crawl.db verrouillée
            run.close()  # une erreur qui se répéterait à chaque tour tairait la collecte toute la partie
            if not self._warned:
                self._warned = True
                print(f"[INFO] Éclaireur SPEC-33 : {type(error).__name__}: {error}")

    def stop(self) -> None:
        """Arrête l'éclairage en cours sans attendre ; les résultats qui arriveraient sont jetés."""
        run, self._run = self._run, None
        if run is not None:
            run.close()

    def snapshot(self) -> Dict[str, Any]:
        """La forme des dix joueurs (voir `_Run.snapshot`), {} sans éclairage."""
        run = self._run
        return run.snapshot() if run is not None else {}

    def stats(self) -> Dict[str, Any]:
        """Compteurs de l'éclairage en cours (banc, journal) : requêtes, erreurs, 429, cache, durées."""
        run = self._run
        return dict(run.stats) if run is not None else {}

    def serve(self) -> None:
        """Lance le fil coordinateur (daemon), une seule fois."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="scout", daemon=True)
        self._thread.start()

    def shutdown(self) -> None:
        """Arrête l'éclairage et le fil coordinateur (fermeture du Live Coach)."""
        self._stop.set()
        self.stop()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.step()
            self._stop.wait(cfg.SCOUT_TICK_S)

    def _publish(self, payload: Optional[Dict[str, Any]]) -> None:
        bus = getattr(self.m, "bus", None)
        if bus is not None:
            bus.publish(TOPIC, payload)

    # ---------- tâches du pool (aucune base ici) ----------

    def _timed(self, kind: str, request: Callable[[Any], Any], arg: Any) -> Tuple[Any, Any, Any]:
        began = time.perf_counter()
        value = request(arg)
        return value, self.lcu.last_status_code, (kind, time.perf_counter() - began)

    def _read_history(self, puuid: str) -> TaskResult:
        raw, status, timing = self._timed("history", self.lcu.get_player_history, puuid)
        if raw is None:
            return None, status, [timing]
        games = ranked_games((raw.get("games") or {}).get("games"), coaching_config.QUEUE_IDS)
        return games, status, [timing]

    def _read_game(self, game_id: int, puuids: List[str]) -> TaskResult:
        game, status, detail = self._timed("detail", self.lcu.get_game_detail, game_id)
        if status == 429 or not game or not game.get("participants"):
            return None, status, [detail]
        timeline, status, timing = self._timed("timeline", self.lcu.get_game_timeline, game_id)
        if status == 429 or not timeline:
            return None, status, [detail, timing]
        value = {
            "game": game,
            "timeline": timeline,
            "impacts": self._impacts(game, timeline, puuids),
        }
        return value, status, [detail, timing]

    def _cached_game(self, raw: bytes, puuids: List[str]) -> TaskResult:
        packed = unpack(raw)
        return {"impacts": self._impacts(packed["game"], packed["timeline"], puuids)}, 200, []

    def _impacts(self, game: dict, timeline: Optional[dict], puuids: List[str]) -> Dict[str, float]:
        if self._model is None:
            return {}
        found = {p: player_impact(self._model, game, timeline, p) for p in puuids}
        return {p: points for p, points in found.items() if points is not None}
