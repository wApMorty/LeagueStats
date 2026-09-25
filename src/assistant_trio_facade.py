"""Trio/duo analysis facade mixin for Assistant (dette de code, TODO.md P4).

Extracted from src/assistant.py : déplacement verbatim, aucun changement de
comportement. Regroupe les délégations vers trio_counterpick/trio_finder/
trio_tactics (Team Builder, menu 5) — la section la plus
volumineuse du fichier, cohérente en elle-même. Mixin plutôt que
composition : les méthodes utilisent ``self.trio_counterpick``,
``self.trio_finder``, ``self.trio_tactics``,
``self._validate_champion_pool``/``self._validate_champion_data``, tous
construits par ``Assistant._init_components()`` (reste dans assistant.py),
sans rien recâbler.
"""

from typing import List, Optional


class _TrioFacadeMixin:
    """optimal_trio_from_pool / find_optimal_trios_holistic et compagnie."""

    # ==================== Optimal Trio Analysis ====================
    # These methods find optimal champion compositions for draft phases

    def _find_optimal_counterpick_duo(
        self, remaining_pool: List[str], blind_champion: str, show_ranking: bool = False
    ) -> tuple:
        """Find the best duo of counterpicks to maximize coverage against all champions."""
        return self.trio_counterpick._find_optimal_counterpick_duo(
            remaining_pool, blind_champion, show_ranking
        )

    def optimal_trio_from_pool(self, champion_pool: List[str], lane: Optional[str] = None) -> tuple:
        """
        Find optimal 3-champion composition from a given pool.

        Algorithm:
        1. Validate champion pool data availability
        2. Find champion with best average delta2 as blind pick
        3. From remaining champions, find duo that maximizes counterpick coverage

        Args:
            lane: Lane optionnelle transmise aux requêtes matchups internes
                  (SPEC-04, pool_manager.pool_role_to_lane). None = agrégation
                  toutes lanes, comportement inchangé.

        Returns:
            Tuple of (blind_pick, counterpick1, counterpick2, total_score)
        """
        return self.trio_counterpick.optimal_trio_from_pool(
            champion_pool,
            validate_pool=lambda pool: self._validate_champion_pool(pool, lane=lane),
            lane=lane,
        )

    def optimal_duo_for_champion(
        self,
        fixed_champion: str,
        champion_pool: List[str] = None,
        lane: Optional[str] = None,
    ) -> tuple:
        """
        Find the best duo of champions to pair with a fixed champion.

        Algorithm:
        1. Validate fixed champion has data
        2. Validate companion pool has sufficient data
        3. Find the duo that maximizes total counterpick coverage alongside fixed champion

        Args:
            lane: Lane optionnelle transmise aux requêtes matchups internes.
                  None = agrégation toutes lanes, comportement inchangé.

        Returns:
            Tuple of (fixed_champion, companion1, companion2, total_score)
        """
        return self.trio_counterpick.optimal_duo_for_champion(
            fixed_champion,
            champion_pool,
            validate_pool=lambda pool: self._validate_champion_pool(pool, lane=lane),
            validate_champion=lambda champ: self._validate_champion_data(champ, lane=lane),
            lane=lane,
        )

    def _analyze_trio_tactics(self, trio: tuple) -> None:
        """Provide tactical analysis on how to use the optimal trio."""
        self.trio_tactics.analyze(trio)

    def _analyze_trio_coverage(self, trio: List[str]) -> None:
        """Analyze what the trio covers and potential gaps."""
        self.trio_tactics._analyze_coverage(trio)

    # ==================== Holistic Trio Analysis ====================

    def find_optimal_trios_holistic(
        self,
        champion_pool: List[str],
        num_results: int = 5,
        lane: Optional[str] = None,
    ) -> List[dict]:
        """Tous les trios du pool classés par valeur de contre-pick (SPEC-18 §4)."""
        return self.trio_finder.find(
            champion_pool,
            num_results=num_results,
            validate_pool=lambda pool: self._validate_champion_pool(pool, lane=lane),
            lane=lane,
        )
