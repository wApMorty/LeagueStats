"""Recherche de trio globale : tous les trios du pool évalués comme des unités.

Différence avec ``trio_counterpick`` (options 1 et 2 du Team Builder), qui fixe
d'abord le blind puis cherche le duo : ici, aucun champion n'est fixé, et le
classement liste plusieurs trios pour laisser le choix.

Même critère que le reste de SPEC-18 §4 (``pool_value.PoolEvaluator``) : la
valeur de contre-pick du trio, et son blind est son champion le plus fort.
Les anciens scores (couverture, équilibre, régularité, méta, profils de
pondération) étaient dérivés du ``delta2`` brut et avaient la dispersion du
bruit pur.
"""

import itertools
from typing import Callable, List, Optional, Tuple

from ..db import Database
from .pool_value import PoolEvaluator


class HolisticTrioFinder:
    """Classe tous les trios d'un pool par valeur de contre-pick."""

    def __init__(self, db: Database, verbose: bool = False) -> None:
        self.db = db
        self.verbose = verbose

    def find(
        self,
        champion_pool: List[str],
        num_results: int = 5,
        validate_pool: Optional[Callable[[List[str]], Tuple[List[str], dict]]] = None,
        lane: Optional[str] = None,
    ) -> List[dict]:
        """Les ``num_results`` meilleurs trios du pool.

        Returns:
            [{"trio": (blind, contre-pick, contre-pick), "total_score": gain en
            contre-pick (pts), "coverage": part des games couvertes,
            "blind_strength": force du blind (pts)}], meilleur d'abord.
        """
        if len(champion_pool) < 3:
            raise ValueError("Champion pool must contain at least 3 champions")

        viable = validate_pool(champion_pool)[0] if validate_pool else list(champion_pool)
        if len(viable) < 3:
            raise ValueError(f"Insufficient data: only {len(viable)}/3 champions viable")

        evaluator = PoolEvaluator(self.db, lane)

        def strength(champion: str) -> float:
            return evaluator.strength.get(champion.lower(), 0.0)

        results = []
        for trio in itertools.combinations(viable, 3):
            blind = max(trio, key=strength)
            results.append(
                {
                    "trio": (blind, *(c for c in trio if c != blind)),
                    "total_score": evaluator.counter_value(trio),
                    "coverage": evaluator.coverage(trio),
                    "blind_strength": strength(blind),
                }
            )
        results.sort(key=lambda r: r["total_score"], reverse=True)
        return results[:num_results]
