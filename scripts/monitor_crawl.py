"""Suivi en direct de la collecte de `crawl.db` (SPEC-20, SPEC-33), Live Coach ouvert.

Une ligne par relevé : parties lues et joueurs visités sur la dernière heure, taille de `crawl_histories`,
couverture de la mesure du terme de forme (parties lues dont 10 / 8 / 5 joueurs ont au moins
`SCOUT_MIN_IMPACT_GAMES` parties antérieures, reprise par `scripts/measure_form_term.py`, calculée
en mémoire en moins d'une seconde) et état du verrou. Lecture seule, lectures courtes : la base n'est
jamais tenue plus de quelques secondes, le Live Coach continue d'écrire.

USAGE:
    python scripts/monitor_crawl.py                # un relevé par minute, Ctrl+C pour arrêter
    python scripts/monitor_crawl.py --interval 300
    python scripts/monitor_crawl.py --once
"""

import argparse
import sqlite3
import sys
import time
from bisect import bisect_left
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config_winprob import winprob_config as cfg  # noqa: E402
from src.winprob.train import crawl_path  # noqa: E402

DEFAULT_INTERVAL_S = 60
DB_TIMEOUT_S = 2.0  # au-delà, la base est tenue par un écrivain : signalé, pas attendu
JOURNAL_STUCK_S = 60  # un journal plus vieux que ça : transaction bloquée (bug du 2026-10-15)
COVERAGE_PLAYERS = tuple(sorted({10, cfg.FORM_COVERED_PLAYERS, 5}, reverse=True))
UTC_FORMAT = "%Y-%m-%d %H:%M:%S"


def coverage(db: sqlite3.Connection, min_games: int) -> Dict[int, int]:
    """Parties lues dont au moins 10 / 8 / 5 joueurs ont la partie dans `crawl_histories` et au moins
    `min_games` parties antérieures (utilisée aussi par `measure_form_term`)."""
    rows: Dict[str, list] = defaultdict(list)
    for puuid, game_id, creation in db.execute(
        "SELECT puuid, game_id, creation_utc FROM crawl_histories"
    ):
        rows[puuid].append((creation, game_id))
    players: Dict[int, int] = defaultdict(int)
    for history in rows.values():
        history.sort()
        for creation, game_id in history:
            if bisect_left(history, (creation,)) >= min_games:
                players[game_id] += 1
    candidates = [g for g, n in players.items() if n >= min(COVERAGE_PLAYERS)]
    read = set()
    for start in range(0, len(candidates), 500):  # limite de variables SQLite
        chunk = candidates[start : start + 500]
        marks = ",".join("?" * len(chunk))
        read.update(
            g
            for (g,) in db.execute(
                f"SELECT game_id FROM crawl_games WHERE read_utc IS NOT NULL AND game_id IN ({marks})",
                chunk,
            )
        )
    return {k: sum(1 for g in read if players[g] >= k) for k in COVERAGE_PLAYERS}


def snapshot(path: Path) -> Optional[dict]:
    """Un relevé, None si la base est verrouillée au-delà de `DB_TIMEOUT_S`."""
    hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime(UTC_FORMAT)
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=DB_TIMEOUT_S)
    try:
        return {
            "read_1h": db.execute(
                "SELECT COUNT(*) FROM crawl_games WHERE read_utc >= ?", (hour_ago,)
            ).fetchone()[0],
            "visited_1h": db.execute(
                "SELECT COUNT(*) FROM crawl_frontier WHERE visited_utc >= ?", (hour_ago,)
            ).fetchone()[0],
            "histories": db.execute(
                "SELECT COUNT(*), COUNT(DISTINCT puuid) FROM crawl_histories"
            ).fetchone(),
            "coverage": coverage(db, cfg.SCOUT_MIN_IMPACT_GAMES),
        }
    except sqlite3.OperationalError:
        return None
    finally:
        db.close()


def journal_age(path: Path) -> Optional[float]:
    """Âge en secondes du journal de transaction, None sans journal."""
    journal = path.with_name(path.name + "-journal")
    try:
        return time.time() - journal.stat().st_mtime
    except OSError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Suivi en direct de la collecte de crawl.db")
    parser.add_argument("--db-path", default=str(crawl_path()))
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL_S, help="secondes")
    parser.add_argument("--once", action="store_true", help="un seul relevé")
    args = parser.parse_args()
    path = Path(args.db_path)
    if not path.exists():
        print(f"[ERREUR] Pas de base de collecte : {path}")
        return 1
    goal = cfg.FORM_MIN_COVERED_GAMES
    first: Optional[dict] = None
    try:
        while True:
            now = datetime.now().strftime("%H:%M:%S")
            age = journal_age(path)
            if age is not None and age > JOURNAL_STUCK_S:
                print(f"[ALERTE] {now} journal figé depuis {age:.0f} s : transaction bloquée ?")
            s = snapshot(path)
            if s is None:
                print(f"[ALERTE] {now} base verrouillée (> {DB_TIMEOUT_S:g} s), relevé sauté")
            else:
                first = first or s
                cov = s["coverage"]
                k = cfg.FORM_COVERED_PLAYERS
                gained = cov[k] - first["coverage"][k]
                rows, players = s["histories"]
                print(
                    f"[DATA] {now}  1 h : {s['read_1h']} parties lues, {s['visited_1h']} joueurs "
                    f"visités | historiques {rows} lignes, {players} joueurs | couverture "
                    f"{cov[k]} / {goal} à {k} joueurs (+{gained} depuis le lancement), "
                    f"10 j. {cov[10]}, 5 j. {cov[5]}",
                    flush=True,
                )
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
