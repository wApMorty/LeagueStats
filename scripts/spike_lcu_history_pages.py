"""Spike SPEC-41 tâche 197 : profondeur réelle de l'historique LCU, page par page.

À lancer sur le PC où tourne le client League of Legends, hors partie. Interroge
`/lol-match-history/v1/products/lol/current-summoner/matches` par pages de 20
(`begIndex=B`, `endIndex=B+19`, borne INCLUSIVE) pour B = 0, 20, 40... Répond à la
question : le LCU sert-il des parties au-delà des 20 dernières ?

Arrêt sur une page vide ou None, sur une page aux mêmes gameId que la précédente
(pagination ignorée), ou dès que `--max-games` parties distinctes sont servies.

Pour la partie la plus ancienne servie, lit le détail et la timeline (participants
présents ? nombre de frames ?). Lecture seule : aucune écriture dans le client ni
en base (`data/db.db` ouvert en `mode=ro`, table `game_records`).

USAGE:
    python scripts/spike_lcu_history_pages.py                 # jusqu'à 500 parties
    python scripts/spike_lcu_history_pages.py --max-games 100
"""

import argparse
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lcu_client import LCUClient  # noqa: E402

PAGE_SIZE = 20  # l'endpoint sert par pages de 20 ; endIndex est inclusif
DEFAULT_MAX_GAMES = 500
SOLOQ_QUEUE_ID = 420
DB_PATH = project_root / "data" / "db.db"
MATCHES_PATH = "/lol-match-history/v1/products/lol/current-summoner/matches"


def fetch_page(lcu: LCUClient, beg: int) -> Optional[List[Dict[str, Any]]]:
    """Parties d'une page (dans l'ordre servi), None si la page est indisponible."""
    end = beg + PAGE_SIZE - 1
    payload = lcu._make_request(f"{MATCHES_PATH}?begIndex={beg}&endIndex={end}")
    if payload is None:
        return None
    games = (payload.get("games") or {}).get("games")
    if not isinstance(games, list):
        return None
    return [g for g in games if isinstance(g, dict) and "gameId" in g and "gameCreation" in g]


def utc_date(creation_ms: int) -> str:
    """Date UTC lisible depuis un `gameCreation` en millisecondes."""
    return datetime.fromtimestamp(creation_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")


def load_db_game_ids() -> Optional[set]:
    """game_id présents dans game_records, lecture seule ; None si base inaccessible."""
    try:
        with closing(sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True)) as conn:
            return {row[0] for row in conn.execute("SELECT game_id FROM game_records")}
    except sqlite3.Error as exc:
        print(f"[ERREUR] lecture de data/db.db impossible : {exc}")
        return None


def describe_oldest(lcu: LCUClient, game: Dict[str, Any]) -> None:
    """Détail et timeline de la partie la plus ancienne servie, avec le code HTTP de chacun."""
    game_id = game["gameId"]
    detail = lcu.get_game_detail(game_id)
    detail_status = lcu.last_status_code
    timeline = lcu.get_game_timeline(game_id)
    timeline_status = lcu.last_status_code

    participants = detail.get("participants") if isinstance(detail, dict) else None
    if isinstance(participants, list):
        detail_text = f"participants présents ({len(participants)})"
    else:
        detail_text = "participants absents"
    frames = timeline.get("frames") if isinstance(timeline, dict) else None
    frames_text = f"{len(frames)} frames" if isinstance(frames, list) else "pas de frames"

    print(f"[DATA] partie la plus ancienne {game_id} ({utc_date(game['gameCreation'])} UTC)")
    print(f"[DATA]   détail : {detail_text}, last_status_code={detail_status}")
    print(f"[DATA]   timeline : {frames_text}, last_status_code={timeline_status}")


def main() -> int:
    """Point d'entrée : pagine l'historique, affiche une ligne par page et une synthèse."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--max-games",
        type=int,
        default=DEFAULT_MAX_GAMES,
        help=f"arrêt après ce nombre de parties distinctes (défaut {DEFAULT_MAX_GAMES})",
    )
    args = parser.parse_args()

    lcu = LCUClient()
    if not lcu.connect():
        print("[ERREUR] client LoL injoignable : ouvrir le client, hors partie")
        return 1

    all_games: Dict[int, Dict[str, Any]] = {}
    previous_ids: Optional[set] = None
    beg = 0
    while len(all_games) < args.max_games:
        page = fetch_page(lcu, beg)
        if not page:
            print(f"[INFO] B={beg} : page vide ou indisponible, arrêt")
            break
        ids = [g["gameId"] for g in page]
        if previous_ids is not None and set(ids) == previous_ids:
            print(
                f"[INFO] B={beg} : mêmes gameId que la page précédente, pagination ignorée, arrêt"
            )
            break

        creations = [g["gameCreation"] for g in page]
        queues = Counter(g.get("queueId") for g in page)
        queues_text = ", ".join(f"{q}:{n}" for q, n in sorted(queues.items(), key=str))
        overlap = len(set(ids) & previous_ids) if previous_ids is not None else 0
        print(
            f"[DATA] B={beg} parties={len(page)} gameId {min(ids)}..{max(ids)} "
            f"du {utc_date(min(creations))} au {utc_date(max(creations))} UTC "
            f"files [{queues_text}] recouvrement précédente={overlap}"
        )

        for game in page:
            all_games.setdefault(game["gameId"], game)
        previous_ids = set(ids)
        beg += PAGE_SIZE

    print(f"[INFO] {beg // PAGE_SIZE} page(s) interrogée(s)")
    if all_games:
        oldest = min(all_games.values(), key=lambda g: g["gameCreation"])
        describe_oldest(lcu, oldest)

    db_ids = load_db_game_ids()
    soloq = sum(1 for g in all_games.values() if g.get("queueId") == SOLOQ_QUEUE_ID)
    absent_text = "base inaccessible" if db_ids is None else str(len(set(all_games) - db_ids))
    print(
        f"[DATA] synthèse : {len(all_games)} parties distinctes servies, dont SoloQ {soloq}, "
        f"dont absentes de game_records {absent_text}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
