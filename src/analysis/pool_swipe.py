"""Suggestions de pool à swiper (SPEC-49) : échanges qui améliorent un pool sur une lane.

Un échange remplace un champion du pool par un entrant, à sa place. Son gain est
la variation de ``pool_score`` : moitié contre-pick (``counter_value``), moitié
blind (meilleur blind du pool). Calcul sans maîtrise : décision de @pj35 du
2026-11-03.

Les valeurs sont nettes du tirage (``draw_shifts``) : ``PoolScorer`` porte ce
tirage au-dessus de ``PoolEvaluator``, qui ne change pas. Le blind d'un champion
est sa force nette, plus le pire duel attendu sur ``POOL_BLIND_DRAWS`` tirages
d'adversaires.
"""

from dataclasses import dataclass
from typing import Collection, Dict, List, Mapping, Optional, Sequence, Tuple

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
    blind_gain: float  # part blind (½ · Δmax blind)
    below_noise: bool  # gain < POOL_SWIPE_NOISE_PT
    wins: Tuple[Tuple[str, float], ...]  # adversaires où le pool gagne le plus (Δ, en points)
    losses: Tuple[Tuple[str, float], ...]  # adversaires où le pool perd le plus (Δ, en points)


def _expected_min(duels: Sequence[Tuple[float, float]], draws: int) -> float:
    """E[min] de ``draws`` tirages avec remise, sur des duels ``(valeur, poids)``.

    Les poids sont renormalisés ; sans poids, 0. Sur les duels triés, P(min = v_i) =
    S_i^k − S_(i+1)^k, S_i étant la part de poids des duels à partir de i (P(≥ v_i)).
    """
    ordered = sorted(duels)
    total = sum(weight for _, weight in ordered)
    if total <= 0:
        return 0.0
    tails = [0.0] * (len(ordered) + 1)
    for i in range(len(ordered) - 1, -1, -1):
        tails[i] = tails[i + 1] + ordered[i][1] / total
    return sum(
        value * (tails[i] ** draws - tails[i + 1] ** draws) for i, (value, _) in enumerate(ordered)
    )


class PoolScorer:
    """Valeurs nettes du tirage et blind exposé au counter, sur un ``PoolEvaluator``.

    ``draws`` : ``{nom: points}`` de ``draw_shifts``, comparé sans casse ; champion absent : 0.
    """

    def __init__(self, evaluator: PoolEvaluator, draws: Mapping[str, float]) -> None:
        self.lane = evaluator.lane
        self.enemies: List[str] = evaluator.enemies
        self.popularity: List[float] = evaluator.popularity
        self._evaluator = evaluator
        self._draws = {name.lower(): shift for name, shift in draws.items()}
        self._values: Dict[str, List[float]] = {}
        self._blind: Dict[str, float] = {}

    def _shift(self, champion: str) -> float:
        """Tirage du champion (0 s'il n'en a pas)."""
        return self._draws.get(champion.lower(), 0.0)

    def values(self, champion: str) -> List[float]:
        """``value(champion, e)`` net du tirage, pour chaque ennemi de ``self.enemies``."""
        key = champion.lower()
        if key not in self._values:
            shift = self._shift(champion)
            self._values[key] = [value - shift for value in self._evaluator.values(champion)]
        return self._values[key]

    def blind(self, champion: str) -> float:
        """Force − tirage + E[min des duels du champion sur POOL_BLIND_DRAWS tirages]."""
        key = champion.lower()
        if key not in self._blind:
            force = self._evaluator.strength.get(key, 0.0)
            # Duel = valeur brute − force ; le champion ne se bat pas contre lui-même.
            duels = [
                (value - force, weight)
                for enemy, value, weight in zip(
                    self.enemies, self._evaluator.values(champion), self.popularity
                )
                if enemy.lower() != key
            ]
            expected = _expected_min(duels, pool_stats_config.POOL_BLIND_DRAWS)
            self._blind[key] = force - self._shift(champion) + expected
        return self._blind[key]

    def counter_value(self, pool: Sequence[str]) -> float:
        """Σ popularité · meilleure valeur nette du pool, face à chaque ennemi."""
        columns = zip(*(self.values(champion) for champion in pool))
        return sum(weight * max(column) for weight, column in zip(self.popularity, columns))


def _blind(scorer: PoolScorer, pool: Sequence[str]) -> float:
    """Blind du pool : le meilleur blind de ses champions."""
    return max(scorer.blind(c) for c in pool)


def _best_per_enemy(scorer: PoolScorer, pool: Sequence[str]) -> List[float]:
    """Meilleure valeur nette du pool face à chaque adversaire de ``scorer.enemies``."""
    return [max(column) for column in zip(*(scorer.values(c) for c in pool))]


def pool_score(scorer: PoolScorer, pool: Sequence[str]) -> float:
    """Valeur d'un pool : ½ contre-pick + ½ blind, en points de winrate. Pool vide : 0."""
    if not pool:
        return 0.0
    return 0.5 * scorer.counter_value(pool) + 0.5 * _blind(scorer, pool)


def _duels(
    scorer: PoolScorer, pool: Sequence[str], new: Sequence[str], incoming: str
) -> Tuple[Tuple[Tuple[str, float], ...], Tuple[Tuple[str, float], ...]]:
    """Duels gagnés et perdus, par adversaire, quand ``pool`` devient ``new``.

    L'entrant n'est pas un adversaire de lui-même : sa propre entrée (valeur =
    sa force) est écartée des duels, pas du calcul du gain.
    """
    before = _best_per_enemy(scorer, pool)
    after = _best_per_enemy(scorer, new)
    moves = [
        (enemy, popularity * (a - b), a - b)
        for enemy, popularity, b, a in zip(scorer.enemies, scorer.popularity, before, after)
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
    scorer: PoolScorer,
    pool: Sequence[str],
    passed: Collection[str] = (),
    excluded: Collection[str] = (),
) -> List[SwapCard]:
    """Une carte par entrant candidat : le sortant qui maximise le gain, gain > 0.

    Candidats : adversaires joués dans au moins ``POOL_SWIPE_MIN_POPULARITY`` des
    parties de la lane, hors pool, hors ``passed`` et hors ``excluded`` (sans casse).
    Égalité de gain : le premier du pool. Triées par gain décroissant, puis par nom.
    """
    pool = list(pool)
    if not pool or not scorer.enemies:
        return []
    skipped = (
        {c.lower() for c in pool} | {p.lower() for p in passed} | {e.lower() for e in excluded}
    )
    base_counter = scorer.counter_value(pool)
    base_blind = _blind(scorer, pool)
    cards: List[SwapCard] = []
    for name, popularity in zip(scorer.enemies, scorer.popularity):
        if popularity < pool_stats_config.POOL_SWIPE_MIN_POPULARITY or name.lower() in skipped:
            continue
        best = None  # (gain, counter_gain, blind_gain, sortant, pool après)
        for i, outgoing in enumerate(pool):
            new = pool[:i] + [name] + pool[i + 1 :]
            counter_gain = 0.5 * (scorer.counter_value(new) - base_counter)
            blind_gain = 0.5 * (_blind(scorer, new) - base_blind)
            gain = counter_gain + blind_gain
            if best is None or gain > best[0]:
                best = (gain, counter_gain, blind_gain, outgoing, new)
        if best is None or best[0] <= 0:
            continue
        gain, counter_gain, blind_gain, outgoing, new = best
        wins, losses = _duels(scorer, pool, new, name)
        cards.append(
            SwapCard(
                lane=scorer.lane,
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
