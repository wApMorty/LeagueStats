"""Trio/duo analysis facade mixin for Assistant (dette de code, TODO.md P4).

Extracted from src/assistant.py : déplacement verbatim, aucun changement de
comportement. Regroupe les délégations vers trio_counterpick/trio_finder/
trio_weights/trio_tactics (Team Builder, menu 5) — la section la plus
volumineuse du fichier, cohérente en elle-même. Mixin plutôt que
composition : les méthodes utilisent ``self.trio_counterpick``,
``self.trio_finder``, ``self.trio_weights``, ``self.trio_tactics``,
``self._validate_champion_pool``/``self._validate_champion_data``, tous
construits par ``Assistant._init_components()`` (reste dans assistant.py),
sans rien recâbler.
"""

from typing import Dict, List, Optional

from .analysis import trio_metrics


class _TrioFacadeMixin:
    """optimal_trio_from_pool / find_optimal_trios_holistic et compagnie."""

    # ==================== Optimal Trio Analysis ====================
    # These methods find optimal champion compositions for draft phases

    def _display_live_podium(
        self, top_duos: List[dict], tested: int, total: int, viable: int
    ) -> None:
        """Display live podium of top 3 duos during evaluation."""
        self.trio_counterpick._display_live_podium(top_duos, tested, total, viable)

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
        profile: str = "balanced",
        lane: Optional[str] = None,
    ) -> List[dict]:
        """
        Find optimal 3-champion combinations using holistic evaluation.

        Unlike the blind-pick approach, this evaluates all possible trios as complete units.

        Args:
            lane: Lane optionnelle transmise aux requêtes matchups internes
                  (SPEC-04, pool_manager.pool_role_to_lane). None = agrégation
                  toutes lanes, comportement inchangé.
        """
        return self.trio_finder.find(
            champion_pool,
            num_results=num_results,
            profile=profile,
            validate_pool=lambda pool: self._validate_champion_pool(pool, lane=lane),
            lane=lane,
        )

    def _calculate_coverage_score(self, enemy_coverage: dict, all_enemies: set) -> float:
        """Calculate how well the trio covers all potential enemies."""
        return trio_metrics.coverage_score(enemy_coverage, all_enemies)

    def _calculate_balance_score_reverse(
        self, trio_list: List[str], enemy_coverage: dict, matchup_cache: dict
    ) -> float:
        """Calculate diversity of matchup profiles using reverse lookup data."""
        return trio_metrics.balance_score_reverse(
            trio_list, enemy_coverage, matchup_cache, verbose=self.verbose
        )

    def _calculate_consistency_score_reverse(
        self, trio_list: List[str], enemy_coverage: dict
    ) -> float:
        """Calculate consistency using reverse lookup data."""
        return trio_metrics.consistency_score_reverse(
            trio_list, enemy_coverage, verbose=self.verbose
        )

    def _calculate_balance_score(self, trio: tuple, all_matchups: List[List]) -> float:
        """Calculate diversity of matchup profiles to avoid same weaknesses."""
        return trio_metrics.balance_score(trio, all_matchups, verbose=self.verbose)

    def _calculate_consistency_score(self, trio: tuple, all_matchups: List[List]) -> float:
        """Calculate how consistently the trio performs across matchups."""
        return trio_metrics.consistency_score(trio, all_matchups, verbose=self.verbose)

    def _calculate_meta_score(self, enemy_coverage: dict) -> float:
        """Calculate performance against popular/meta champions."""
        return trio_metrics.meta_score(self._db, enemy_coverage, verbose=self.verbose)

    def _calculate_enemy_coverage(self, matchups_list: List[List]) -> Dict[str, tuple]:
        """Calculate enemy coverage for a set of champions."""
        return trio_metrics.enemy_coverage_from_matchups(matchups_list)

    def _calculate_adaptive_base_weights(self, sample_trios: List[tuple]) -> Dict[str, float]:
        """Calculate base weights using variance analysis."""
        return self.trio_weights.calculate_adaptive_base_weights(sample_trios)

    def _get_profile_modifiers(self, profile: str = "balanced") -> Dict[str, float]:
        """Get profile-specific modifiers for weight adjustment."""
        return self.trio_weights.get_profile_modifiers(profile)

    def _calculate_contextual_total_score(
        self, scores: Dict[str, float], profile: str = "balanced"
    ) -> tuple:
        """Calculate total score using adaptive weights + profile modifiers."""
        return self.trio_weights.calculate_contextual_total_score(scores, profile)

    def _generate_sample_trios_for_weights(self, sample_size: int = 15) -> List[tuple]:
        """Generate a sample of trios for adaptive weight calculation."""
        return self.trio_weights.generate_sample_trios_for_weights(sample_size)

    def set_scoring_profile(self, profile: str) -> None:
        """
        Set the scoring profile for trio evaluation.

        Args:
            profile: One of "safe", "meta", "aggressive", "balanced"
        """
        self.trio_weights.set_scoring_profile(profile)

    @property
    def _cached_base_weights(self):
        return self.trio_weights._cached_base_weights

    @_cached_base_weights.setter
    def _cached_base_weights(self, value):
        self.trio_weights._cached_base_weights = value

    @_cached_base_weights.deleter
    def _cached_base_weights(self):
        del self.trio_weights._cached_base_weights

    @property
    def scoring_profile(self):
        return self.trio_weights.scoring_profile

    @scoring_profile.setter
    def scoring_profile(self, value):
        self.trio_weights.scoring_profile = value
