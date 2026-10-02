"""Collecte de parties tierces via le LCU, en tâche de fond (SPEC-20 §3.1).

Une file de joueurs (`crawl_frontier`), amorcée par les joueurs de tes propres
parties, dont l'historique (20 parties) alimente une file de parties à lire
(`crawl_games`, `raw` NULL tant que non lue). `step()` fait au plus une unité
de travail par appel, depuis la boucle du Live Coach : pas de thread, la pause
en draft va de soi (la boucle ne l'appelle pas).

Cache recalculable : `data/crawl.db`, hors Alembic, hors `db.db`. Best-effort :
rien ici n'interrompt le Live Coach.
"""

import json
import sqlite3
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from ..config import config
from ..config_coaching import coaching_config
from ..config_winprob import winprob_config as cfg

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
        self._conn: Optional[sqlite3.Connection] = None
        self._seeded: set = set()
        # Date de création en dessous de laquelle les parties sont déjà purgées (patch ou
        # plafond) : inutile de les redécouvrir, lire et purger en boucle.
        # ponytail: en mémoire, un redémarrage relit au plus CRAWL_PURGE_EVERY parties périmées.
        self._floor = ""
        self._reads = 0
        self._warned = False

    # ---------- API pour la boucle du Live Coach ----------

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

        read = count("crawl_games", "length(raw) > 0")
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
        games = self.m.lcu.get_player_games(puuid)
        if self._throttled(1) or (games is None and self.m.lcu.last_status_code is None):
            return  # 429, ou client injoignable : on réessaiera
        db = self._db()
        oldest = max(_utc((time.time() - cfg.CRAWL_MAX_AGE_DAYS * 86400) * 1000), self._floor)
        for g in games or []:
            created = _utc(g["game_creation_ms"])
            if g["queue_id"] in coaching_config.QUEUE_IDS and created >= oldest:
                db.execute(
                    "INSERT OR IGNORE INTO crawl_games (game_id, queue_id, game_creation_utc, depth) "
                    "VALUES (?, ?, ?, ?)",
                    (g["game_id"], g["queue_id"], created, depth),
                )
        db.execute("UPDATE crawl_frontier SET visited_utc = ? WHERE puuid = ?", (_now(), puuid))
        db.commit()

    def _read_game(self, game_id: int, depth: int) -> None:
        lcu = self.m.lcu
        game = lcu.get_game_detail(game_id)
        if self._throttled(1) or (not game and lcu.last_status_code is None):
            return
        db = self._db()
        if not game or not game.get("participants"):
            db.execute("UPDATE crawl_games SET raw = x'' WHERE game_id = ?", (game_id,))
            db.commit()
            return
        timeline = lcu.get_game_timeline(game_id)
        if self._throttled(1):
            return
        blue = next((t for t in game.get("teams") or [] if t.get("teamId") == 100), {})
        db.execute(
            "UPDATE crawl_games SET game_version = ?, duration_s = ?, blue_win = ?, read_utc = ?, raw = ? "
            "WHERE game_id = ?",
            (
                game.get("gameVersion"),
                game.get("gameDuration"),
                int(blue["win"] == "Win") if blue else None,
                _now(),
                pack(game, timeline if timeline and timeline.get("frames") else None),
                game_id,
            ),
        )
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
        for game_id, participant_id in db.get_recent_games(cfg.CRAWL_SEED_GAMES):
            if game_id in self._seeded:
                continue
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
        throttled = self.m.lcu.last_status_code == 429
        if throttled:
            wait = cfg.CRAWL_BACKOFF_S
            print(f"[ALERTE] Collecte SPEC-20 : 429 du LCU, pause de {wait / 60:.0f} min")
        self._next_at = self._clock() + wait
        return throttled

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
            self._conn.executescript(SCHEMA)
            # Bases créées avant `read_utc` (commit 8c80f03) : colonne ajoutée, les parties
            # déjà lues datent de la veille au plus, donc comptées dans les dernières 24 h.
            columns = [row[1] for row in self._conn.execute("PRAGMA table_info(crawl_games)")]
            if "read_utc" not in columns:
                self._conn.execute("ALTER TABLE crawl_games ADD COLUMN read_utc TEXT")
                self._conn.execute(
                    "UPDATE crawl_games SET read_utc = ? WHERE length(raw) > 0", (_now(),)
                )
                self._conn.commit()
        return self._conn

    def _safely(self, work: Callable[[], None]) -> None:
        try:
            work()
        except Exception as e:
            if getattr(self.m, "verbose", False) or not self._warned:
                self._warned = True
                print(f"[WARNING] Collecte SPEC-20 : {e}")
