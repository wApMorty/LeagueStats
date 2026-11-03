"""Suggestions de pool à swiper (SPEC-49) : échanges qui améliorent un pool sur une lane.

Un échange remplace un champion du pool par un entrant, à sa place. Son gain est
la variation de ``pool_score`` : moitié contre-pick (``counter_value``), moitié
blind (force du meilleur champion du pool). Calcul sans maîtrise : décision
de @pj35 du 2026-11-03.
"""

from dataclasses import dataclass
from typing import Collection, List, Optional, Sequence, Tuple

from ..config_constants import pool_stats_config
from .pool_value import PoolEvaluator


@dataclass(frozen=True)
class SwapCard:
    """Un échange proposé : ``incoming`` prend la place de ``outgoing`` dans le pool."""

    lane: Optional[str]
    incoming: str
    outgoing: str
    gain: float  # J(pool après) − J(pool), en points de winrate
    counter_gain: float  # part contre-pick (½ · Δcounter_value)
    blind_gain: float  # part blind (½ · Δforce du meilleur champion)
    below_noise: bool  # gain < POOL_SWIPE_NOISE_PT
    wins: Tuple[Tuple[str, float], ...]  # adversaires où le pool gagne le plus (Δ, en points)
    losses: Tuple[Tuple[str, float], ...]  # adversaires où le pool perd le plus (Δ, en points)


def _blind(evaluator: PoolEvaluator, pool: Sequence[str]) -> float:
    """Force du meilleur champion du pool (le blind pick)."""
    return max(evaluator.strength.get(c.lower(), 0.0) for c in pool)


def _best_per_enemy(evaluator: PoolEvaluator, pool: Sequence[str]) -> List[float]:
    """Meilleure valeur du pool face à chaque adversaire de ``evaluator.enemies``."""
    return [max(column) for column in zip(*(evaluator.values(c) for c in pool))]


def pool_score(evaluator: PoolEvaluator, pool: Sequence[str]) -> float:
    """Valeur d'un pool : ½ contre-pick + ½ blind, en points de winrate. Pool vide : 0."""
    if not pool:
        return 0.0
    return 0.5 * evaluator.counter_value(pool) + 0.5 * _blind(evaluator, pool)


def _duels(
    evaluator: PoolEvaluator, pool: Sequence[str], new: Sequence[str], incoming: str
) -> Tuple[Tuple[Tuple[str, float], ...], Tuple[Tuple[str, float], ...]]:
    """Duels gagnés et perdus, par adversaire, quand ``pool`` devient ``new``.

    L'entrant n'est pas un adversaire de lui-même : sa propre entrée (valeur =
    sa force) est écartée des duels, pas du calcul du gain.
    """
    before = _best_per_enemy(evaluator, pool)
    after = _best_per_enemy(evaluator, new)
    moves = [
        (enemy, popularity * (a - b), a - b)
        for enemy, popularity, b, a in zip(evaluator.enemies, evaluator.popularity, before, after)
        if a != b and enemy.lower() != incoming.lower()
    ]
    wins = sorted((m for m in moves if m[2] > 0), key=lambda m: m[1], reverse=True)
    losses = sorted((m for m in moves if m[2] < 0), key=lambda m: m[1])
    shown = pool_stats_config.POOL_SWIPE_DUELS_SHOWN
    return (
        tuple((enemy, delta) for enemy, _, delta in wins[:shown]),
        tuple((enemy, delta) for enemy, _, delta in losses[:shown]),
    )


def swap_cards(
    evaluator: PoolEvaluator, pool: Sequence[str], passed: Collection[str] = ()
) -> List[SwapCard]:
    """Une carte par entrant candidat : le sortant qui maximise le gain, gain > 0.

    Candidats : adversaires joués dans au moins ``POOL_SWIPE_MIN_POPULARITY`` des
    parties de la lane, hors pool et hors ``passed`` (sans casse). Égalité de gain :
    le premier du pool. Triées par gain décroissant, puis par nom.
    """
    pool = list(pool)
    if not pool or not evaluator.enemies:
        return []
    skipped = {c.lower() for c in pool} | {p.lower() for p in passed}
    base_counter = evaluator.counter_value(pool)
    base_blind = _blind(evaluator, pool)
    cards: List[SwapCard] = []
    for name, popularity in zip(evaluator.enemies, evaluator.popularity):
        if popularity < pool_stats_config.POOL_SWIPE_MIN_POPULARITY or name.lower() in skipped:
            continue
        best = None  # (gain, counter_gain, blind_gain, sortant, pool après)
        for i, outgoing in enumerate(pool):
            new = pool[:i] + [name] + pool[i + 1 :]
            counter_gain = 0.5 * (evaluator.counter_value(new) - base_counter)
            blind_gain = 0.5 * (_blind(evaluator, new) - base_blind)
            gain = counter_gain + blind_gain
            if best is None or gain > best[0]:
                best = (gain, counter_gain, blind_gain, outgoing, new)
        if best is None or best[0] <= 0:
            continue
        gain, counter_gain, blind_gain, outgoing, new = best
        wins, losses = _duels(evaluator, pool, new, name)
        cards.append(
            SwapCard(
                lane=evaluator.lane,
                incoming=name,
                outgoing=outgoing,
                gain=gain,
                counter_gain=counter_gain,
                blind_gain=blind_gain,
                below_noise=gain < pool_stats_config.POOL_SWIPE_NOISE_PT,
                wins=wins,
                losses=losses,
            )
        )
    cards.sort(key=lambda card: (-card.gain, card.incoming.lower()))
    return cards
