"""Règle D (SPEC-55) : score d'un champion dans la draft, et arbre du pool qui en découle.

D = connu + exposition, en logit, la même pour tous les postes :

- ``known`` : contribution calibrée du champion aux paires déjà posées, moins son tirage
  complet (ADR-004). Sans maîtrise : les matrices seules.
- ``exposure`` : pour chaque lane ennemie sans champion posé, E[min] sur ``POOL_BLIND_DRAWS``
  tirages du ``matchup_logit`` contre les adversaires de cette lane, pondérés par leur part
  des parties (``lane_popularity``).

``lane_popularity`` est la seule fonction qui lit la base. Le reste ne fait aucune I/O.
"""

from dataclasses import dataclass
from typing import Collection, Dict, List, Sequence, Tuple

from ..config_constants import analysis_config, pool_stats_config, scraping_config
from .game_eval import GameEvaluator, Placed
from .mastery import to_win_points
from .pool_swipe import _expected_min
from .pool_tree import PoolTree, TreeChoice, _ranked
from .probability import winrate_points_to_logit

# lane -> [(champion, part des parties de la lane)], parts >= POOL_SWIPE_MIN_POPULARITY
Popularity = Dict[str, List[Tuple[str, float]]]


@dataclass(frozen=True)
class DScore:
    """Score D d'un candidat : ``known`` et ``exposure`` en logit, ``total`` leur somme."""

    champion: str
    known: float  # contribution calibrée − tirage complet
    exposure: float  # Σ E[min] des lanes ennemies sans champion posé (≤ 0 en général)

    @property
    def total(self) -> float:
        """Score D : connu + exposition, en logit."""
        return self.known + self.exposure


def lane_popularity(db) -> Popularity:
    """Champions joués à ``POOL_SWIPE_MIN_POPULARITY`` au moins, sur chaque lane de
    ``scraping_config.LANES``. Parts = games / total de la lane, lues dans
    ``db.get_lane_winrates``. Triées par part décroissante puis nom sans casse ; lane
    sans parties : liste vide."""
    popularity: Popularity = {}
    floor = pool_stats_config.POOL_SWIPE_MIN_POPULARITY
    for lane in scraping_config.LANES:
        raw = db.get_lane_winrates(lane)
        total = sum(games for _, games in raw.values())
        shares = [(name, games / total) for name, (_, games) in raw.items()] if total else []
        kept = [(name, share) for name, share in shares if share >= floor]
        kept.sort(key=lambda item: (-item[1], item[0].casefold()))
        popularity[lane] = kept
    return popularity


def d_scores(
    evaluator: GameEvaluator,
    lane: str,
    candidates: Sequence[str],
    allies: Sequence[Placed],
    enemies: Sequence[Placed],
    unavailable: Collection[str],
    popularity: Popularity,
) -> List[DScore]:
    """Score D de chaque candidat, trié par total décroissant puis nom sans casse (SPEC-55 §1.2).

    ``unavailable`` : pris et bannis. Un candidat déjà dans la draft, ou en double, est écarté.
    Une lane ennemie posée n'entre pas dans l'exposition ; un allié non posé n'en fait pas partie.
    """
    posed = {enemy_lane for _, enemy_lane in enemies if enemy_lane}
    taken = {name.casefold() for name in unavailable} | {
        name.casefold() for name, _ in [*allies, *enemies]
    }
    scores: List[DScore] = []
    seen = set()
    for name in candidates:
        key = name.casefold()
        if key in seen or key in taken:
            continue
        seen.add(key)
        me: Placed = (name, lane)
        known = evaluator.contribution(me, allies, enemies) - winrate_points_to_logit(
            evaluator.draw_points(me) * analysis_config.K_INTRINSIC
        )
        exposure = 0.0
        for enemy_lane, enemy_pool in popularity.items():
            if enemy_lane in posed:
                continue
            duels = [
                (evaluator.matchup_logit(me, (enemy, enemy_lane)), share)
                for enemy, share in enemy_pool
                if enemy.casefold() not in taken and enemy.casefold() != key
            ]
            exposure += _expected_min(duels, pool_stats_config.POOL_BLIND_DRAWS)
        scores.append(DScore(name, known, exposure))
    scores.sort(key=lambda score: (-score.total, score.champion.casefold()))
    return scores


def _choices(scores: Sequence[DScore]) -> List[TreeChoice]:
    """Scores D lus en points de victoire, pour les tables de ``PoolTree``."""
    return [TreeChoice(score.champion, to_win_points(score.total)) for score in scores]


def exposure_tree(
    evaluator: GameEvaluator, lane: str, pool: Sequence[str], popularity: Popularity
) -> PoolTree:
    """L'arbre lu dans D, en points de victoire.

    ``blind`` : ``d_scores`` avec une draft vide. Une table par adversaire de ``popularity[lane]``,
    ``d_scores`` avec ce seul ennemi, qui n'est pas proposé dans sa propre table.
    """
    if not pool:
        return PoolTree(lane=lane, blind=(), counters=())
    blind = _ranked(_choices(d_scores(evaluator, lane, pool, [], [], [], popularity)))
    counters = []
    for enemy, share in popularity.get(lane, []):
        table = d_scores(evaluator, lane, pool, [], [(enemy, lane)], [enemy], popularity)
        counters.append((enemy, share, _ranked(_choices(table))))
    counters.sort(key=lambda row: (-row[1], row[0].casefold()))
    return PoolTree(lane=lane, blind=blind, counters=tuple(counters))
