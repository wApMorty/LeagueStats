"""Banc de mesure de la recherche minimax du Live Coach (SPEC-17 §4.4).

Rejoue les deux scénarios de SPEC-17 §1 sur une COPIE TEMPORAIRE de la base
(jamais la base de production, jamais d'écriture) et affiche, pour chacun, la
profondeur atteinte, les nœuds par seconde, le top 3 et la variante principale.

- **B1** : premier pick, board vide, 10 tours restants.
- **B2** : Jinx bot alliée, Garen top et Lee Sin jungle ennemis, 7 tours restants.

Les alliés à venir ont leur lane assignée, comme en file classée (SPEC-17 §4.2).

Pool : les 20 champions les plus joués sur notre lane (``middle``). Dans la
variante principale, ``*`` marque un champion hors des ``--top-n`` plus joués
de sa lane (critère SPEC-17 §6.2).

Ce n'est pas un test : les chiffres dépendent de la base réelle et du CPU.

USAGE:
    python scripts/bench_search.py
    python scripts/bench_search.py --budget 10 --top-n 12
"""

import argparse
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Sequence

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.game_eval import GameEvaluator, Placed
from src.config import config
from src.config_constants import draft_config, scraping_config
from src.db import Database
from src.draft.search import CandidatePool, DraftSearch, PickTurn

PLAYER_LANE = "middle"
POOL_SIZE = 20
# Ordre de draft SoloQ : B1 R1 R2 B2 B3 R3 R4 B4 B5 R5 (nous sommes côté bleu).
DRAFT_ORDER = "BRRBBRRBBR"
SCENARIOS = {
    "B1": {
        "allies": [],
        "enemies": [],
        "first_turn": 0,
        "ally_lanes": ["bottom", "top", "jungle", "support"],
    },
    "B2": {
        "allies": [("Jinx", "bottom")],
        "enemies": [("Garen", "top"), ("LeeSin", "jungle")],
        "first_turn": 3,
        "ally_lanes": ["top", "jungle", "support"],
    },
}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SPEC-17 : banc de la recherche minimax")
    parser.add_argument("--db-path", default=config.DATABASE_PATH)
    parser.add_argument("--budget", type=float, default=draft_config.SEARCH_BUDGET_SECONDS)
    parser.add_argument("--top-n", type=int, default=draft_config.SEARCH_TOP_N)
    return parser.parse_args()


def _lane_popularity(connection: sqlite3.Connection, lane: str) -> List[str]:
    """Champions joués sur ``lane``, du plus joué au moins joué (somme des games)."""
    rows = connection.execute(
        "SELECT c.name FROM matchups m JOIN champions c ON c.id = m.champion "
        "WHERE m.lane = ? GROUP BY m.champion ORDER BY SUM(m.games) DESC",
        (lane,),
    ).fetchall()
    return [row[0] for row in rows]


def _turns(first_turn: int, ally_lanes: List[str]) -> List[PickTurn]:
    """Tours restants à partir du nôtre ; les alliés suivants prennent
    ``ally_lanes`` dans l'ordre."""
    lanes = iter(ally_lanes)
    turns = [PickTurn(is_ally=True, is_local_player=True)]
    for side in DRAFT_ORDER[first_turn + 1 :]:
        turns.append(
            PickTurn(is_ally=True, lane=next(lanes)) if side == "B" else PickTurn(is_ally=False)
        )
    return turns


def _format_line(line: Sequence[Placed], popular: Dict[str, set]) -> str:
    return ", ".join(
        f"{name}{'' if name in popular.get(lane, ()) else '*'} {lane}" for name, lane in line
    )


def main() -> None:
    args = _parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "db.db"
        shutil.copy2(args.db_path, copy)
        db = Database(str(copy))
        db.connect()
        try:
            ranking = {
                lane: _lane_popularity(db.connection, lane) for lane in scraping_config.LANES
            }
            popular = {lane: set(names[: args.top_n]) for lane, names in ranking.items()}
            pool = ranking[PLAYER_LANE][:POOL_SIZE]

            evaluator = GameEvaluator(db)
            candidates = CandidatePool(db, args.top_n)
            # Hors chrono : le monitor charge ces tables en début de draft.
            evaluator.warm(scraping_config.LANES)
            for lane in scraping_config.LANES:
                candidates.best(lane, set())
            search = DraftSearch(evaluator, candidates)

            print(f"Budget {args.budget:g} s, top-n {args.top_n}, pool {POOL_SIZE} {PLAYER_LANE}")
            for label, scenario in SCENARIOS.items():
                turns = _turns(scenario["first_turn"], scenario["ally_lanes"])
                start = time.monotonic()
                results = search.rank(
                    scenario["allies"],
                    scenario["enemies"],
                    pool,
                    turns,
                    player_lane=PLAYER_LANE,
                    budget_seconds=args.budget,
                )
                elapsed = time.monotonic() - start
                print(
                    f"\n[{label}] profondeur {results[0].depth}/{len(turns)}, "
                    f"{search.nodes} nœuds, {search.nodes / elapsed:,.0f} nœuds/s"
                )
                for result in results[:3]:
                    print(f"  {result.champion:<14} {result.win_probability * 100:6.2f} %")
                print(f"  variante : {_format_line(results[0].principal_variation, popular)}")
        finally:
            db.close()


if __name__ == "__main__":
    main()
