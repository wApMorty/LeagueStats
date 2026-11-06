"""Générateur de pool (SPEC-50) : le pool de taille ``size`` qui maximise le score moyen.

Le score d'un pool est ``pool_score`` (``pool_swipe``) moyenné sur les scrapes donnés. Recherche
gloutonne (ajouts successifs du meilleur candidat), puis échanges un pour un jusqu'à stabilité :
le résultat est un optimum local, pas une garantie d'optimum global. Sur la vraie base, il égale
l'énumération exhaustive dans les 40 configurations vérifiées le 2026-11-06 (5 postes, 2 modes,
tailles 3 à 6) ; sur des valeurs aléatoires, il peut la manquer. Python pur, sans numpy.
"""

from dataclasses import dataclass
from typing import Collection, List, Optional, Sequence, Tuple

from ..config_constants import pool_stats_config
from .pool_swipe import PoolScorer, pool_score

# Gain minimal d'un échange pour être appliqué : sous ce seuil, l'échange est considéré nul.
_SWAP_EPSILON = 1e-12


@dataclass(frozen=True)
class GeneratedPool:
    """Pool généré sur une lane, avec son détail par scrape."""

    lane: Optional[str]
    champions: Tuple[str, ...]  # ordre : meilleur blind d'abord
    score: float  # J moyen
    per_scrape: Tuple[float, ...]  # J de chaque scrape, du plus récent au plus ancien
    blind: Tuple[Tuple[str, float], ...]  # blind de chaque champion (scrape le plus récent)
    counter_share: Tuple[Tuple[str, float], ...]  # part de popularité où il est le meilleur counter
    counters: Tuple[Tuple[str, float, str, float], ...]  # (adversaire, popularité, counter, value')
    candidates: int


def mean_score(scorers: Sequence[PoolScorer], pool: Sequence[str]) -> float:
    """Moyenne des ``pool_score`` du pool sur chaque scrape."""
    return sum(pool_score(scorer, pool) for scorer in scorers) / len(scorers)


def _candidates(scorers: Sequence[PoolScorer], excluded: Collection[str]) -> List[str]:
    """Noms présents à ``POOL_SWIPE_MIN_POPULARITY`` dans chaque scrape, hors exclus, triés.

    Comparaison sans casse ; le nom retenu est celui du scrape le plus récent.
    """
    minimum = pool_stats_config.POOL_SWIPE_MIN_POPULARITY
    excluded_keys = {name.casefold() for name in excluded}
    eligible = None
    for scorer in scorers:
        keys = {
            name.casefold()
            for name, popularity in zip(scorer.enemies, scorer.popularity)
            if popularity >= minimum
        }
        eligible = keys if eligible is None else eligible & keys
    names = {
        name.casefold(): name
        for name in scorers[0].enemies
        if name.casefold() in (eligible or set()) and name.casefold() not in excluded_keys
    }
    return [names[key] for key in sorted(names)]


def _first_improving_swap(
    scorers: Sequence[PoolScorer], pool: List[str], candidates: Sequence[str]
) -> Optional[List[str]]:
    """Premier échange (position × candidat hors pool) qui gagne plus de ``_SWAP_EPSILON``."""
    current = mean_score(scorers, pool)
    for i in range(len(pool)):
        for candidate in candidates:
            if candidate in pool:
                continue
            trial = pool[:i] + [candidate] + pool[i + 1 :]
            if mean_score(scorers, trial) > current + _SWAP_EPSILON:
                return trial
    return None


def _counter_rows(
    scorer: PoolScorer, champions: Sequence[str]
) -> List[Tuple[str, float, str, float]]:
    """Par adversaire du scrape : (adversaire, popularité, meilleur champion, sa valeur nette).

    Égalité : le premier champion de ``champions``.
    """
    rows = [scorer.values(champion) for champion in champions]
    result = []
    for i, (enemy, popularity) in enumerate(zip(scorer.enemies, scorer.popularity)):
        best = max(range(len(champions)), key=lambda j: rows[j][i])
        result.append((enemy, popularity, champions[best], rows[best][i]))
    return result


def generate_pool(
    scorers: Sequence[PoolScorer], size: int, excluded: Collection[str]
) -> Optional[GeneratedPool]:
    """Meilleur pool de ``size`` champions pour le score moyen sur ``scorers``.

    ``scorers[0]`` est le scrape le plus récent : il donne l'ordre, les blinds, les parts et les
    counters. Renvoie ``None`` sans scorer, si ``size`` < 1 ou s'il y a moins de ``size``
    candidats.
    """
    if not scorers or size < 1:
        return None
    candidates = _candidates(scorers, excluded)
    if len(candidates) < size:
        return None

    pool: List[str] = []
    for _ in range(size):
        best_name = None
        best_value = 0.0
        for candidate in candidates:
            if candidate in pool:
                continue
            value = mean_score(scorers, pool + [candidate])
            if best_name is None or value > best_value:
                best_name, best_value = candidate, value
        pool.append(best_name)

    while True:
        swapped = _first_improving_swap(scorers, pool, candidates)
        if swapped is None:
            break
        pool = swapped

    recent = scorers[0]
    champions = sorted(pool, key=lambda c: (-recent.blind(c), c.casefold()))
    per_scrape = tuple(pool_score(scorer, champions) for scorer in scorers)
    rows = _counter_rows(recent, champions)
    share = {champion: 0.0 for champion in champions}
    for _, popularity, counter, _ in rows:
        share[counter] += popularity
    counters = tuple(
        sorted(
            (row for row in rows if row[1] >= pool_stats_config.POOL_GEN_COUNTERS_MIN_POPULARITY),
            key=lambda row: -row[1],
        )
    )
    return GeneratedPool(
        lane=recent.lane,
        champions=tuple(champions),
        score=sum(per_scrape) / len(per_scrape),
        per_scrape=per_scrape,
        blind=tuple((c, recent.blind(c)) for c in champions),
        counter_share=tuple((c, share[c]) for c in champions),
        counters=counters,
        candidates=len(candidates),
    )
