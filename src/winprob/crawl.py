"""Collecte de parties tierces via le LCU, en tâche de fond (SPEC-20 §3.1).

Une file de joueurs (`crawl_frontier`), amorcée par les joueurs de tes propres
parties, dont l'historique (20 parties) alimente une file de parties à lire
(`crawl_games`, `raw` NULL tant que non lue). `step()` fait au plus une unité
de travail par appel. `start()` la boucle dans un fil à part, avec son propre
client LCU et sa propre connexion SQLite : une requête lente (3 à 17 s la
timeline d'un inconnu) ne retient plus la boucle du Live Coach, donc ni la file
trouvée ni la draft. Le fil se tait en champ select et pendant l'acceptation.

Cache recalculable : `data/crawl.db`, hors Alembic, hors `db.db`. Best-effort :
rien ici n'interrompt le Live Coach.
"""

import json
import sqlite3
import threading
import time
import zlib
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ..config import config
from ..config_coaching import coaching_config
from ..config_constants import draft_config
from ..lcu_client import LCUClient
from ..config_winprob import winprob_config as cfg
from .form import ranked_games

SCHEMA = """
CREATE TABLE IF NOT EXISTS crawl_games (
    game_id INTEGER PRIMARY KEY,
    queue_id INTEGER,
    game_version TEXT,
    game_creation_utc TEXT NOT NULL,
    duration_s INTEGER,
    blue_win INTEGER,
    depth INTEGER NOT NULL,
    read_utc TEXT,
    raw BLOB  -- NULL : à lire ; vide : indisponible ; sinon zlib(JSON)
);
CREATE TABLE IF NOT EXISTS crawl_frontier (
    puuid TEXT PRIMARY KEY,
    depth INTEGER NOT NULL,  -- 0 : le joueur lui-même, jamais visité
    priority INTEGER NOT NULL,  -- création (ms) de la partie la plus récente vue
    discovered_utc TEXT NOT NULL,
    visited_utc TEXT
);
-- ponytail: pas de purge de crawl_histories (~20 lignes par visite, quelques dizaines de Mo par mois) ;
-- purge par âge à ajouter si la base grossit.
CREATE TABLE IF NOT EXISTS crawl_histories (
    puuid TEXT NOT NULL,
    game_id INTEGER NOT NULL,
    creation_utc TEXT NOT NULL,
    queue_id INTEGER,
    champion_id INTEGER,
    win INTEGER,
    kills INTEGER,
    deaths INTEGER,
    assists INTEGER,
    cs INTEGER,
    duration_s INTEGER,
    PRIMARY KEY (puuid, game_id)
);
"""

# Sans index, chaque requête de la boucle du Live Coach balaie les 500 Mo de `crawl_games` (blobs
# compris) : à froid, la boucle y passait des dizaines de secondes et manquait la file trouvée. Les
# index partiels couvrent le travail à faire ; `read_utc` remplace `length(raw) > 0` dans les comptes.
# `crawl_games_stored` couvre le plafond de la purge : sans lui, `raw IS NOT NULL` lisait chaque ligne.
INDEXES = """
CREATE INDEX IF NOT EXISTS crawl_games_todo ON crawl_games(depth, game_creation_utc DESC)
    WHERE raw IS NULL;
CREATE INDEX IF NOT EXISTS crawl_games_created ON crawl_games(game_creation_utc);
CREATE INDEX IF NOT EXISTS crawl_games_version ON crawl_games(game_version);
CREATE INDEX IF NOT EXISTS crawl_games_read ON crawl_games(read_utc);
CREATE INDEX IF NOT EXISTS crawl_games_stored ON crawl_games(game_creation_utc)
    WHERE raw IS NOT NULL;
CREATE INDEX IF NOT EXISTS crawl_frontier_todo ON crawl_frontier(depth, priority DESC)
    WHERE visited_utc IS NULL;
"""

_UTC_FORMAT = "%Y-%m-%d %H:%M:%S"


def _utc(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime(_UTC_FORMAT)


def _now() -> str:
    return _utc(time.time() * 1000)


def _patch(version: Optional[str]) -> tuple:
    """'16.19.821.7343' -> (16, 19) ; () si illisible."""
    try:
        major, minor = (version or "").split(".")[:2]
        return int(major), int(minor)
    except ValueError:
        return ()


def pack(game: dict, timeline: Optional[dict]) -> bytes:
    """Détail + timeline compressés, identités retirées sauf le puuid."""
    game = dict(game)
    game["participantIdentities"] = [
        {
            "participantId": identity.get("participantId"),
            "player": {"puuid": (identity.get("player") or {}).get("puuid")},
        }
        for identity in game.get("participantIdentities") or []
    ]
    return zlib.compress(json.dumps({"game": game, "timeline": timeline}).encode())


def unpack(raw: bytes) -> dict:
    return json.loads(zlib.decompress(raw))


def store_game(db: sqlite3.Connection, game: dict, timeline: Optional[dict], depth: int) -> None:
    """Range une partie lue (détail + timeline) dans `crawl_games`, ligne créée si absente.

    Partagée par la collecte et l'éclaireur (SPEC-33) : même `pack`, même `blue_win`. Une timeline
    sans images est rangée vide. Sans commit : c'est l'appelant qui valide.
    """
    blue = next((t for t in game.get("teams") or [] if t.get("teamId") == 100), {})
    db.execute(
        "INSERT INTO crawl_games (game_id, queue_id, game_version, game_creation_utc, duration_s, "
        "blue_win, depth, read_utc, raw) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(game_id) DO UPDATE SET game_version = excluded.game_version, "
        "duration_s = excluded.duration_s, blue_win = excluded.blue_win, "
        "read_utc = excluded.read_utc, raw = excluded.raw, depth = MIN(depth, excluded.depth)",
        (
            game["gameId"],
            game.get("queueId"),
            game.get("gameVersion"),
            _utc(game.get("gameCreation") or 0),
            game.get("gameDuration"),
            int(blue["win"] == "Win") if blue else None,
            depth,
            _now(),
            pack(game, timeline if timeline and timeline.get("frames") else None),
        ),
    )


def store_history(db: sqlite3.Connection, puuid: str, games: list) -> None:
    """Range l'historique classé d'un joueur (sorties de `form.ranked_games`) dans `crawl_histories`.

    Une partie déjà rangée est ignorée (une revisite n'ajoute rien). Sans commit : c'est l'appelant
    qui valide.
    """
    db.executemany(
        "INSERT OR IGNORE INTO crawl_histories (puuid, game_id, creation_utc, queue_id, champion_id, "
        "win, kills, deaths, assists, cs, duration_s) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                puuid,
                g["game_id"],
                _utc(g["creation_ms"]),
                g["queue_id"],
                g["champion_id"],
                int(g["win"]),
                g["kills"],
                g["deaths"],
                g["assists"],
                g["cs"],
                g["duration_s"],
            )
            for g in games
        ],
    )


class Crawler:
    def __init__(
        self,
        monitor,
        path: Optional[Path] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.m = monitor
        self.path = path or Path(config.DATABASE_PATH).with_name(cfg.CRAWL_DB_FILENAME)
        self._clock = clock
        self._next_at = 0.0
        # Une connexion par fil : le fil de collecte et la boucle (seed, report) écrivent tous deux.
        self._local = threading.local()
        self._own_lcu: Optional[LCUClient] = None  # celui du fil de collecte, une fois lancé
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._seeded: set = set()
        # Date de création en dessous de laquelle les parties sont déjà purgées (patch ou
        # plafond) : inutile de les redécouvrir, lire et purger en boucle.
        # ponytail: en mémoire, un redémarrage relit au plus CRAWL_PURGE_EVERY parties périmées.
        self._floor = ""
        self._reads = 0
        self._warned = False
        # Visites de couverture (SPEC-33 tâche 162) : (puuid, partie) dont lire l'historique, avant tout
        # autre travail, pour que la mesure du terme de forme connaisse les dix joueurs des parties lues.
        # ponytail: en mémoire, un redémarrage perd au plus les joueurs d'une partie.
        self._cover: deque = deque()

    # ---------- API pour la boucle du Live Coach ----------

    @property
    def lcu(self):
        """Le client du fil de collecte ; sans fil (tests, appel direct), celui du moniteur."""
        return self._own_lcu or self.m.lcu

    def start(self) -> None:
        """Lance le fil de collecte (daemon) ; sans effet s'il tourne déjà."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="crawler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Demande l'arrêt ; le fil, daemon, s'éteint au plus tard à sa prochaine attente."""
        self._stop.set()

    def _paused(self) -> bool:
        """Champ select, acceptation de la file ou éclaireur en cours : le client LoL est pris."""
        tracker = self.m.phase_tracker
        scout = getattr(self.m, "scout", None)  # SPEC-33 : l'éclaireur a le client pour lui
        return (
            tracker.kind == "draft"
            or tracker.phase == "ReadyCheck"
            or bool(getattr(scout, "active", False))
        )

    def _run(self) -> None:
        lcu = self._own_lcu = LCUClient()
        lcu.yield_if = self._paused  # une requête en vol n'est pas coupée, aucune ne part ensuite
        while not self._stop.is_set():
            wait = cfg.CRAWL_REQUEST_INTERVAL_S
            try:
                if (
                    self.m.phase_tracker.phase is None
                ):  # client fermé ou redémarrage : port à relire
                    lcu.credentials = None
                    wait = draft_config.PHASE_CREDENTIALS_RETRY_S
                elif lcu.credentials is None:
                    lcu.credentials = lcu.find_lcu_credentials()
                    wait = 0.0 if lcu.credentials else draft_config.PHASE_CREDENTIALS_RETRY_S
                elif not self._paused():
                    self.step()
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # best-effort : rien ici n'atteint la boucle
            self._stop.wait(wait)

    def step(self) -> None:
        """Une unité de travail (1 à 2 requêtes), si le débit et la pause le permettent."""
        if self._clock() >= self._next_at:
            self._safely(self._step)

    def report(self) -> None:
        """Une ligne d'avancement, une fois par fin de partie (SPEC-20 tâche 40)."""
        self._safely(lambda: print(self.progress()))

    def seed(self) -> None:
        """Amorce la file avec les joueurs de tes dernières parties, et purge."""
        self._safely(self._seed)

    def progress(self) -> str:
        def count(table: str, where: str) -> int:
            return self._db().execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()[0]

        read = count("crawl_games", "read_utc IS NOT NULL")
        recent = count("crawl_games", "read_utc >= datetime('now', '-1 day')")
        pending = count("crawl_games", "raw IS NULL")
        players = count("crawl_frontier", "visited_utc IS NULL")
        return (
            f"[DATA] Collecte : {read} parties lues (+{recent} en 24 h), "
            f"{pending} à lire, {players} joueurs en attente"
        )

    # ---------- travail ----------

    def _step(self) -> None:
        db = self._db()
        while self._cover:
            puuid, game_id = self._cover.popleft()
            known = db.execute(
                "SELECT 1 FROM crawl_histories WHERE puuid = ? AND game_id = ?", (puuid, game_id)
            ).fetchone()
            if not known:
                return self._cover_visit(puuid, game_id)
        game = db.execute(
            "SELECT game_id, depth FROM crawl_games WHERE raw IS NULL "
            "ORDER BY depth, game_creation_utc DESC LIMIT 1"
        ).fetchone()
        if game:
            return self._read_game(*game)
        player = db.execute(
            "SELECT puuid, depth FROM crawl_frontier WHERE visited_utc IS NULL "
            "ORDER BY depth, priority DESC LIMIT 1"
        ).fetchone()
        if player:
            self._visit(*player)

    def _visit(self, puuid: str, depth: int) -> None:
        payload = self.lcu.get_player_history(puuid)
        if self._throttled(1) or (payload is None and self.lcu.last_status_code is None):
            return  # 429, ou client injoignable : on réessaiera
        games = ranked_games(
            ((payload or {}).get("games") or {}).get("games"), coaching_config.QUEUE_IDS
        )
        db = self._db()
        oldest = max(_utc((time.time() - cfg.CRAWL_MAX_AGE_DAYS * 86400) * 1000), self._floor)
        for g in games:
            created = _utc(g["creation_ms"])
            if created >= oldest:
                db.execute(
                    "INSERT OR IGNORE INTO crawl_games (game_id, queue_id, game_creation_utc, depth) "
                    "VALUES (?, ?, ?, ?)",
                    (g["game_id"], g["queue_id"], created, depth),
                )
        store_history(db, puuid, games)
        db.execute("UPDATE crawl_frontier SET visited_utc = ? WHERE puuid = ?", (_now(), puuid))
        db.commit()

    def _cover_visit(self, puuid: str, game_id: int) -> None:
        """Historique seul d'un joueur d'une partie lue : rangé dans `crawl_histories`, sans partie
        ajoutée à lire ni joueur marqué visité (SPEC-33 tâche 162)."""
        payload = self.lcu.get_player_history(puuid)
        if self._throttled(1) or (payload is None and self.lcu.last_status_code is None):
            self._cover.appendleft((puuid, game_id))  # 429, ou client injoignable : plus tard
            return
        games = ranked_games(
            ((payload or {}).get("games") or {}).get("games"), coaching_config.QUEUE_IDS
        )
        db = self._db()
        store_history(db, puuid, games)
        db.commit()

    def _read_game(self, game_id: int, depth: int) -> None:
        lcu = self.lcu
        game = lcu.get_game_detail(game_id)
        if self._throttled(1) or (not game and lcu.last_status_code is None):
            return
        db = self._db()
        if not game or not game.get("participants"):
            db.execute("UPDATE crawl_games SET raw = x'' WHERE game_id = ?", (game_id,))
            db.commit()
            return
        timeline = lcu.get_game_timeline(game_id)
        if self._throttled(1) or (not timeline and lcu.last_status_code is None):
            return  # limite de débit, ou requête abandonnée (draft en cours, SPEC-28) : plus tard
        store_game(db, {**game, "gameId": game_id}, timeline, depth)
        for identity in game.get("participantIdentities") or []:
            puuid = (identity.get("player") or {}).get("puuid")
            if puuid:
                self._cover.append((puuid, game_id))
        if depth + 1 <= cfg.CRAWL_MAX_DEPTH:
            priority = game.get("gameCreation") or 0
            for identity in game.get("participantIdentities") or []:
                puuid = (identity.get("player") or {}).get("puuid")
                if puuid:
                    self._add_player(puuid, depth + 1, priority)
        db.commit()
        self._reads += 1
        if self._reads % cfg.CRAWL_PURGE_EVERY == 0:
            self._purge()

    def _seed(self) -> None:
        db = self.m.assistant.db
        fresh = False
        for game_id, participant_id in db.get_recent_games(cfg.CRAWL_SEED_GAMES):
            if game_id in self._seeded:
                continue
            fresh = True
            raw = db.get_raw_game(game_id)
            game = json.loads(raw) if raw else {}
            priority = game.get("gameCreation") or 0
            for identity in game.get("participantIdentities") or []:
                puuid = (identity.get("player") or {}).get("puuid")
                if not puuid:
                    continue
                if identity.get("participantId") == participant_id:
                    self._mark_self(puuid, priority)
                else:
                    self._add_player(puuid, 1, priority, from_my_game=True)
            self._seeded.add(game_id)
        self._db().commit()
        if (
            fresh
        ):  # `seed()` repasse toutes les 5 s en après-partie : la purge n'a rien de neuf à voir
            self._purge()

    def _add_player(
        self, puuid: str, depth: int, priority: int, from_my_game: bool = False
    ) -> None:
        """Ajoute un joueur à visiter. Venu d'une de tes parties, plus récente que sa
        dernière visite, il est à revisiter (sauf toi-même, depth 0)."""
        self._db().execute(
            "INSERT INTO crawl_frontier (puuid, depth, priority, discovered_utc) "
            "VALUES (:puuid, :depth, :priority, :now) "
            "ON CONFLICT(puuid) DO UPDATE SET "
            "depth = MIN(depth, excluded.depth), "
            "visited_utc = CASE WHEN :mine AND excluded.priority > priority AND depth > 0 "
            "THEN NULL ELSE visited_utc END, "
            "priority = CASE WHEN :mine THEN MAX(priority, excluded.priority) ELSE priority END",
            {
                "puuid": puuid,
                "depth": depth,
                "priority": priority,
                "now": _now(),
                "mine": int(from_my_game),
            },
        )

    def mark_visited(self, puuid: str, priority: int) -> None:
        """Le joueur dont l'éclaireur vient de lire l'historique (SPEC-33) : visité, sans commit."""
        self._db().execute(
            "INSERT INTO crawl_frontier (puuid, depth, priority, discovered_utc, visited_utc) "
            "VALUES (:puuid, 1, :priority, :now, :now) "
            "ON CONFLICT(puuid) DO UPDATE SET visited_utc = :now",
            {"puuid": puuid, "priority": priority, "now": _now()},
        )

    def _mark_self(self, puuid: str, priority: int) -> None:
        self._db().execute(
            "INSERT INTO crawl_frontier (puuid, depth, priority, discovered_utc, visited_utc) "
            "VALUES (:puuid, 0, :priority, :now, :now) "
            "ON CONFLICT(puuid) DO UPDATE SET depth = 0, visited_utc = :now",
            {"puuid": puuid, "priority": priority, "now": _now()},
        )

    def _purge(self) -> None:
        """Supprime les parties trop vieilles, hors des patchs conservés, puis au-delà
        du plafond (les plus anciennes d'abord)."""
        db = self._db()
        oldest = _utc((time.time() - cfg.CRAWL_MAX_AGE_DAYS * 86400) * 1000)
        db.execute("DELETE FROM crawl_games WHERE game_creation_utc < ?", (oldest,))

        per_patch: dict = {}
        for version, n in db.execute(
            "SELECT game_version, COUNT(*) FROM crawl_games "
            "WHERE game_version IS NOT NULL GROUP BY game_version"
        ).fetchall():
            if _patch(version):
                per_patch[_patch(version)] = per_patch.get(_patch(version), 0) + n
        keep, total = set(), 0
        for patch in sorted(per_patch, reverse=True):
            if len(keep) >= cfg.WINPROB_PATCH_WINDOW and total >= cfg.WINPROB_MIN_PATCH_GAMES:
                break
            keep.add(patch)
            total += per_patch[patch]
        trimmed = 0
        for version in db.execute(
            "SELECT DISTINCT game_version FROM crawl_games WHERE game_version IS NOT NULL"
        ).fetchall():
            if _patch(version[0]) and _patch(version[0]) not in keep:
                trimmed += db.execute(
                    "DELETE FROM crawl_games WHERE game_version = ?", version
                ).rowcount
        trimmed += db.execute(
            "DELETE FROM crawl_games WHERE game_id IN (SELECT game_id FROM crawl_games "
            "WHERE raw IS NOT NULL ORDER BY game_creation_utc DESC LIMIT -1 OFFSET ?)",
            (cfg.CRAWL_MAX_GAMES,),
        ).rowcount
        if trimmed:
            (first,) = db.execute(
                "SELECT MIN(game_creation_utc) FROM crawl_games WHERE length(raw) > 0"
            ).fetchone()
            self._floor = max(self._floor, first or "")
            db.execute(
                "DELETE FROM crawl_games WHERE raw IS NULL AND game_creation_utc < ?",
                (self._floor,),
            )
        db.commit()

    # ---------- infrastructure ----------

    def _throttled(self, requests_made: int) -> bool:
        """Règle le débit après `requests_made` requêtes ; True au 429 (pause)."""
        wait = requests_made * cfg.CRAWL_REQUEST_INTERVAL_S
        throttled = self.lcu.last_status_code == 429
        if throttled:
            wait = cfg.CRAWL_BACKOFF_S
            print(f"[ALERTE] Collecte SPEC-20 : 429 du LCU, pause de {wait / 60:.0f} min")
        self._next_at = self._clock() + wait
        return throttled

    def _db(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._local.conn = sqlite3.connect(self.path)
            conn.executescript(SCHEMA)
            # Bases créées avant `read_utc` (commit 8c80f03) : colonne ajoutée, les parties
            # déjà lues datent de la veille au plus, donc comptées dans les dernières 24 h.
            columns = [row[1] for row in conn.execute("PRAGMA table_info(crawl_games)")]
            if "read_utc" not in columns:
                conn.execute("ALTER TABLE crawl_games ADD COLUMN read_utc TEXT")
                conn.execute("UPDATE crawl_games SET read_utc = ? WHERE length(raw) > 0", (_now(),))
                conn.commit()
            conn.executescript(INDEXES)
        return conn

    def rollback(self) -> None:
        """Annule la transaction en cours de la connexion de ce fil. Après un commit en échec
        (« database is locked »), la connexion garde son verrou et plus aucun lecteur ne lit la base.
        """
        conn = getattr(self._local, "conn", None)
        try:
            if conn is not None and conn.in_transaction:
                conn.rollback()
        except sqlite3.Error:
            pass  # best-effort : la prochaine écriture réessaiera

    def _safely(self, work: Callable[[], None]) -> None:
        try:
            work()
        except Exception as e:
            self.rollback()
            if getattr(self.m, "verbose", False) or not self._warned:
                self._warned = True
                print(f"[WARNING] Collecte SPEC-20 : {e}")
