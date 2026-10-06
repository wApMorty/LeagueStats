"""Conseil d'échange de rôle (SPEC-24 tâche 102) : ce que gagne la victoire prédite si deux alliés
échangent leurs rôles, mesuré par le même évaluateur que le Live Coach.

Un conseil n'existe que si les deux joueurs ont un champion (le mien survolé ou verrouillé, l'autre
verrouillé) et si le gain atteint ``SWAP_MIN_GAIN_PTS`` : sans cela, aucune métrique, donc rien à dire.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from ..analysis.game_eval import Placed
from ..config_constants import draft_config
from .snapshot import SnapshotSwapAdvice
from .state import Swap

OPEN_STATES = ("AVAILABLE", "RECEIVED")  # un échange qu'on peut demander ou accepter


def has_open_swap(swaps: Sequence[Swap], kind: str) -> bool:
    """La session liste au moins un échange de ce type qu'on peut demander ou accepter."""
    return any(swap.kind == kind and swap.state in OPEN_STATES for swap in swaps)


def role_swaps(
    evaluator,
    allies: Dict[int, Placed],
    enemies: Sequence[Placed],
    me: Optional[int],
    swaps: Sequence[Swap],
) -> List[SnapshotSwapAdvice]:
    """Les échanges de rôle qui améliorent la victoire prédite d'au moins ``SWAP_MIN_GAIN_PTS``.

    ``allies`` : cellule -> (champion, lane) pour les seuls alliés qui ont un champion, moi compris.
    Meilleur gain d'abord. L'évaluateur qui lève n'est pas rattrapé ici : l'appelant est best-effort.
    """
    mine = allies.get(me)
    if mine is None or not mine[1]:
        return []
    base = evaluator.win_probability(list(allies.values()), list(enemies))
    advice: List[SnapshotSwapAdvice] = []
    for swap in swaps:
        other = allies.get(swap.cell_id)
        if (
            swap.kind != "position"
            or swap.state not in OPEN_STATES
            or other is None
            or not other[1]
        ):
            continue
        swapped = {**allies, me: (mine[0], other[1]), swap.cell_id: (other[0], mine[1])}
        gain = (evaluator.win_probability(list(swapped.values()), list(enemies)) - base) * 100.0
        if gain >= draft_config.SWAP_MIN_GAIN_PTS:
            advice.append(
                SnapshotSwapAdvice(
                    "position",
                    swap.cell_id,
                    other[0],
                    gain,
                    f"{mine[0]} en {other[1]}, {other[0]} en {mine[1]}",
                )
            )
    return sorted(advice, key=lambda item: -item.gain_pts)
