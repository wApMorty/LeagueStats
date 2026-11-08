"""Rappel de place en draft (SPEC-53 §4.2) : quelle place de pick viser, et avec qui demander l'échange.

Module pur : la ligne de pick vient de ``src/analysis/pick_order.py``, les rangs et les échanges de
la session (``DraftState.pick_order`` et ``DraftState.swaps``). Aucune entrée-sortie ici.
"""

from dataclasses import dataclass
from typing import List, Mapping, Optional, Sequence, Tuple

from ..analysis.pick_order import Pick
from .state import Swap


@dataclass(frozen=True)
class PickAdvice:
    """Le conseil de place pour mon pick.

    Attributes:
        lane: mon poste.
        side: ``"blue"`` ou ``"red"``.
        mode: ``"blind"`` si mon pick précède celui du même poste côté adverse, sinon ``"counter"``.
        target: rang visé, de 1 à 10.
        current: mon rang actuel.
        cell_id: allié avec qui demander l'échange d'ordre, ou None.
        target_cell: True si cet échange donne exactement la place visée.
    """

    lane: str
    side: str
    mode: str
    target: int
    current: int
    cell_id: Optional[int]
    target_cell: bool


def _side_of(ranks: Mapping[int, int]) -> str:
    """Le côté de mon équipe : bleu si une de mes cellules a le rang 1, sinon rouge."""
    return "blue" if 1 in ranks.values() else "red"


def pick_advice(
    line: Sequence[Pick],
    lane: Optional[str],
    my_cell: Optional[int],
    ranks: Mapping[int, int],
    swaps: Sequence[Swap],
) -> Optional[PickAdvice]:
    """Le conseil de place pour mon pick, ou None s'il n'y a rien à dire.

    Args:
        line: la ligne principale de pick (10 picks, de ``pick_order``).
        lane: mon poste, ``scraping_config.LANES``.
        my_cell: ma cellule.
        ranks: cellule alliée -> rang de pick (1 à 10). Seules les cellules alliées y figurent.
        swaps: les échanges de la session ; seuls les ``pick_order`` ``AVAILABLE`` sont demandables.

    Returns:
        Le conseil, ou None sans ligne, sans poste, sans rang pour moi, ou sans pick adverse au même poste.
    """
    if not line or lane is None or my_cell not in ranks:
        return None
    side = _side_of(ranks)
    other = "red" if side == "blue" else "blue"
    mine = next((p for p in line if p.side == side and p.lane == lane), None)
    theirs = next((p for p in line if p.side == other and p.lane == lane), None)
    if mine is None or theirs is None:
        return None
    target = mine.slot
    current = ranks[my_cell]
    mode = "blind" if target < theirs.slot else "counter"

    # Un échange ne compte que s'il rapproche strictement mon rang de la place visée. Entre deux
    # rangs à égale distance, un counter prend le plus tardif, un blind le plus tôt.
    candidates: List[Tuple[int, int]] = []
    for swap in swaps:
        if swap.kind != "pick_order" or swap.state != "AVAILABLE":
            continue
        rank = ranks.get(swap.cell_id)
        if rank is not None and abs(rank - target) < abs(current - target):
            candidates.append((rank, swap.cell_id))
    if not candidates:
        return PickAdvice(lane, side, mode, target, current, None, False)
    best_rank, cell_id = min(
        candidates,
        key=lambda c: (abs(c[0] - target), -c[0] if mode == "counter" else c[0]),
    )
    return PickAdvice(lane, side, mode, target, current, cell_id, best_rank == target)


def request_effect(advice: PickAdvice, ranks: Mapping[int, int], cell_id: int) -> Optional[str]:
    """Effet sur mon rang si j'accepte l'échange avec ``cell_id``.

    Returns:
        ``"closer"`` si le rang de l'autre rapproche de ma place visée, ``"farther"`` s'il s'en
        éloigne, None s'il ne change rien ou si son rang est inconnu.
    """
    rank = ranks.get(cell_id)
    if rank is None:
        return None
    gain = abs(advice.current - advice.target) - abs(rank - advice.target)
    if gain > 0:
        return "closer"
    if gain < 0:
        return "farther"
    return None
