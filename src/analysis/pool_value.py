"""Valeur d'un pool pour une lane : un blind pick et des contre-picks (SPEC-18 §4).

La valeur d'un champion ``c`` face à un ennemi ``e`` est, en points de winrate
au-dessus de la moyenne de la lane :

    value(c, e) = force(c) + duel(c, e)

- ``force(c)`` : winrate de lane rétréci, moins la moyenne de la lane
  (``shrink.shrunk_lane_winrates``) ;
- ``duel(c, e)`` : delta2 antisymétrique rétréci (``GameEvaluator.duel_points``).

La force de l'ennemi est la même pour tous nos champions : elle ne change pas
lequel on choisit contre lui, on l'omet.

Un pool se juge au contre-pick : face à chaque ennemi, on joue le meilleur de
nos champions. D'où ``counter_value(pool) = Σ_e popularité(e) · max_c value(c, e)``,
la popularité étant la part des games jouées contre l'ennemi sur la lane.
"""

from typing import Dict, List, Optional, Sequence

from .game_eval import GameEvaluator
from .shrink import shrunk_lane_winrates


class PoolEvaluator:
    """Valeurs de contre-pick sur une lane, calculées une fois par champion."""

    def __init__(self, db, lane: Optional[str]) -> None:
        self.lane = lane
        raw = db.get_lane_winrates(lane)
        total = sum(games for _, games in raw.values())
        mean = sum(wr * games for wr, games in raw.values()) / total if total else 0.0
        self.strength = {
            name.lower(): value - mean for name, value in shrunk_lane_winrates(db, lane).items()
        }
        enemy_games = db.get_lane_enemy_games(lane)
        faced = sum(enemy_games.values())
        self.enemies: List[str] = list(enemy_games)
        self.popularity = [enemy_games[name] / faced for name in self.enemies] if faced else []
        self._evaluator = GameEvaluator(db)
        self._values: Dict[str, List[float]] = {}

    def values(self, champion: str) -> List[float]:
        """``value(champion, e)`` pour chaque ennemi de ``self.enemies``."""
        key = champion.lower()
        if key not in self._values:
            force = self.strength.get(key, 0.0)
            self._values[key] = [
                force
                + (
                    self._evaluator.duel_points((champion, self.lane), (enemy, self.lane))
                    if enemy.lower() != key
                    else 0.0
                )
                for enemy in self.enemies
            ]
        return self._values[key]

    def measured(self, champion: str, enemy: str) -> bool:
        """Vrai si le duel ``champion`` / ``enemy`` a des données sur la lane."""
        return self._evaluator.has_matchup_data((champion, self.lane), (enemy, self.lane))

    def counter_value(self, pool: Sequence[str], floor: Optional[float] = None) -> float:
        """Gain moyen en points de winrate quand on contre-pick avec ``pool``.

        ``floor`` : valeur d'un repli hors pool (0 = un champion moyen de la
        lane). Sert à noter un champion seul en contre-pick : on ne le joue
        que là où il bat la moyenne.
        """
        columns = zip(*(self.values(champion) for champion in pool))
        total = 0.0
        for weight, column in zip(self.popularity, columns):
            best = max(column)
            total += weight * (best if floor is None else max(best, floor))
        return total

    def coverage(self, pool: Sequence[str]) -> float:
        """Part des games de la lane où le pool a un contre-pick au-dessus de la moyenne."""
        columns = zip(*(self.values(champion) for champion in pool))
        return sum(w for w, column in zip(self.popularity, columns) if max(column) > 0.0)


def dominant_lane(db, champions: Sequence[str]) -> Optional[str]:
    """Lane où les champions d'un pool sont le plus joués (somme des parts).

    Pour un pool sans rôle déclaré (``custom``) : sans lane, les bans et les
    valeurs agrégeraient toutes les lanes, et un pool de tanks top se verrait
    conseiller de bannir des ADC.
    """
    distributions = db.get_lane_distributions_by_name()
    totals: Dict[str, float] = {}
    for champion in champions:
        for lane, share in distributions.get(champion.lower(), {}).items():
            totals[lane] = totals.get(lane, 0.0) + share
    return max(totals, key=totals.get) if totals else None
