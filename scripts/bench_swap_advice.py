"""Banc du conseil d'échange d'ordre de pick (SPEC-24 tâche 103).

Rejoue des drafts fixes sur une COPIE TEMPORAIRE de la base (jamais la production, jamais d'écriture) :
pour chaque allié avec qui échanger son ordre, imprime le gain (points de victoire prédite) mesuré
par la recherche minimax à budget réduit puis à budget plein, et si le signe tient d'un budget à l'autre.

Critère de livraison (SPEC-24 §4.6) : le signe du gain à 2 s est identique à celui à 0,5 s pour au moins
80 % des cas qui dépassent ``SWAP_MIN_GAIN_PTS`` ; sinon, pas de conseil d'ordre.

Limite connue (relevé du 2026-10-07) : la recherche écarte les tours qui PRÉCÈDENT le mien (cf.
``DraftRecommender._turns_from_our_next_pick``). Un échange change donc surtout le nombre de picks
alliés considérés, pas leur ordre : la stabilité d'un budget à l'autre est satisfaite sans que le gain
ait un sens (la recherche finit dans les 0,5 s, les deux budgets rendent le même chiffre).

Ce n'est pas un test : les chiffres dépendent de la base réelle et du CPU.

USAGE:
    python scripts/bench_swap_advice.py
    python scripts/bench_swap_advice.py --short 0.5 --long 2
"""

import argparse
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(Path(__file__).parent))

from bench_search import (  # noqa: E402
    DRAFT_ORDER,
    PLAYER_LANE,
    POOL_SIZE,
    SCENARIOS,
    _lane_popularity,
)
from src.analysis.game_eval import GameEvaluator, Placed  # noqa: E402
from src.config import config  # noqa: E402
from src.config_constants import draft_config, scraping_config  # noqa: E402
from src.db import Database  # noqa: E402
from src.draft.search import CandidatePool, DraftSearch, PickTurn  # noqa: E402
from src.draft.state import Swap  # noqa: E402
from src.draft.snapshot import SnapshotSwapAdvice  # noqa: E402
from src.draft.swap_advice import OPEN_STATES  # noqa: E402


def turns_from_mine(turns: Sequence[PickTurn]) -> List[PickTurn]:
    """Les tours à partir du mien (ceux qui le précèdent sont écartés, comme le Live Coach)."""
    for index, turn in enumerate(turns):
        if turn.is_local_player:
            return list(turns[index:])
    return []


def order_swaps(
    search,
    allies: Sequence[Placed],
    enemies: Sequence[Placed],
    pool: Sequence[str],
    turns: Sequence[PickTurn],
    cells: Sequence[int],
    me: Optional[int],
    swaps: Sequence[Swap],
    names: Dict[int, str],
    banned: Sequence[str] = (),
    player_lane: Optional[str] = None,
    budget_seconds: Optional[float] = None,
) -> List[SnapshotSwapAdvice]:
    """Les échanges d'ordre de pick dont la recherche minimax tire au moins ``SWAP_MIN_GAIN_PTS``.

    ``turns`` : tous les picks restants dans l'ordre de la draft, ``cells`` la cellule qui joue chacun.
    Échanger l'ordre avec l'allié X permute nos deux tours ; la meilleure victoire prédite de mon pool
    avec les tours permutés est comparée à celle de l'ordre actuel, AU MÊME budget (la profondeur
    atteinte en dépend). ``names`` : cellule -> champion de l'allié, pour le libellé.
    """
    if me not in cells:
        return []
    mine = cells.index(me)

    def best(order: Sequence[PickTurn]) -> Optional[float]:
        results = search.rank(
            allies,
            enemies,
            pool,
            turns_from_mine(order),
            banned=banned,
            player_lane=player_lane,
            budget_seconds=budget_seconds,
        )
        return results[0].win_probability if results else None

    before = best(turns)
    advice: List[SnapshotSwapAdvice] = []
    for swap in swaps:
        if swap.kind != "pick_order" or swap.state not in OPEN_STATES or swap.cell_id not in cells:
            continue
        other = cells.index(swap.cell_id)
        permuted = list(turns)
        permuted[mine], permuted[other] = turns[other], turns[mine]
        after = best(permuted)
        if before is None or after is None:
            continue
        gain = (after - before) * 100.0
        if gain >= draft_config.SWAP_MIN_GAIN_PTS:
            later = "plus tard" if other > mine else "plus tôt"
            advice.append(
                SnapshotSwapAdvice(
                    "pick_order",
                    swap.cell_id,
                    names.get(swap.cell_id, ""),
                    gain,
                    f"picker {later} (n° {other + 1} au lieu de {mine + 1} des picks restants)",
                )
            )
    return sorted(advice, key=lambda item: -item.gain_pts)


def full_turns(first_turn: int, ally_lanes: List[str]) -> Tuple[List[PickTurn], List[int]]:
    """Tous les tours restants (le nôtre en tête) et la cellule qui joue chacun (bleu 0-4, rouge 5-9)."""
    lanes = iter(ally_lanes)
    blue, red = iter(range(1, 5)), iter(range(5, 10))
    turns = [PickTurn(is_ally=True, is_local_player=True)]
    cells = [0]
    for side in DRAFT_ORDER[first_turn + 1 :]:
        if side == "B":
            turns.append(PickTurn(is_ally=True, lane=next(lanes)))
            cells.append(next(blue))
        else:
            turns.append(PickTurn(is_ally=False))
            cells.append(next(red))
    return turns, cells


def main() -> None:
    parser = argparse.ArgumentParser(description="SPEC-24 : banc du conseil d'ordre de pick")
    parser.add_argument("--db-path", default=config.DATABASE_PATH)
    parser.add_argument("--short", type=float, default=0.5)
    parser.add_argument("--long", type=float, default=draft_config.SEARCH_BUDGET_SECONDS)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "db.db"
        shutil.copy2(args.db_path, copy)
        db = Database(str(copy))
        db.connect()
        try:
            pool = _lane_popularity(db.connection, PLAYER_LANE)[:POOL_SIZE]
            evaluator = GameEvaluator(db)
            candidates = CandidatePool(db, draft_config.SEARCH_TOP_N)
            evaluator.warm(scraping_config.LANES)
            for lane in scraping_config.LANES:
                candidates.best(lane, set())
            search = DraftSearch(evaluator, candidates)

            threshold = draft_config.SWAP_MIN_GAIN_PTS
            above, stable = 0, 0
            print(
                f"Budgets {args.short:g} s et {args.long:g} s, seuil {threshold:g} pt, pool {POOL_SIZE}"
            )
            for label, scenario in SCENARIOS.items():
                turns, cells = full_turns(scenario["first_turn"], scenario["ally_lanes"])
                allies_cells = [c for c in cells if c < 5 and c != 0]
                swaps = [Swap("pick_order", 100 + c, c, "AVAILABLE") for c in allies_cells]
                names = {c: f"cellule {c}" for c in allies_cells}

                def gains(budget: float) -> dict:
                    # Sans seuil : le gain brut de chaque candidat, gains négatifs compris.
                    draft_config.SWAP_MIN_GAIN_PTS = -100.0
                    try:
                        advice = order_swaps(
                            search,
                            scenario["allies"],
                            scenario["enemies"],
                            pool,
                            turns,
                            cells,
                            0,
                            swaps,
                            names,
                            player_lane=PLAYER_LANE,
                            budget_seconds=budget,
                        )
                    finally:
                        draft_config.SWAP_MIN_GAIN_PTS = threshold
                    return {a.cell_id: a.gain_pts for a in advice}

                short, long_ = gains(args.short), gains(args.long)
                print(f"\n[{label}] tours restants {len(turns)}")
                for cell in allies_cells:
                    a, b = short.get(cell), long_.get(cell)
                    if a is None or b is None:
                        print(f"  cellule {cell}: pas de résultat")
                        continue
                    big = max(a, b) >= threshold
                    same = (a > 0) == (b > 0)
                    if big:
                        above += 1
                        stable += same
                    print(
                        f"  cellule {cell} (tour n° {cells.index(cell) + 1}) : "
                        f"{a:+6.2f} pts à {args.short:g} s, {b:+6.2f} pts à {args.long:g} s"
                        f"{'  [au-dessus du seuil]' if big else ''}"
                        f"{'' if same else '  [SIGNE DIFFÉRENT]'}"
                    )
            ratio = stable / above if above else 0.0
            print(f"\nCas au-dessus du seuil : {above}, signe stable : {stable} ({ratio:.0%})")
            print(
                "Limite : voir l'en-tête du script, la stabilité ne prouve pas que le gain a un sens."
            )
            print(
                "Critère (>= 80 %) : "
                + (
                    "stabilité tenue (la livraison reste à décider : voir la limite)"
                    if above and ratio >= 0.8
                    else "NON tenu"
                )
            )
        finally:
            db.close()


if __name__ == "__main__":
    main()
