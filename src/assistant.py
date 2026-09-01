"""
Main Assistant class - Coordinator for champion analysis and recommendations.

This is the new modular version that delegates to specialized modules while
maintaining backward compatibility with the original API.
"""

from typing import Dict, List, Optional

from .config import config
from .config_constants import analysis_config
from .db import Database
from .models import Matchup, MatchupDraft

# Import specialized modules
from .analysis.scoring import ChampionScorer
from .analysis.tier_list import TierListGenerator
from .analysis.recommendations import RecommendationEngine
from .analysis.team_analysis import TeamAnalyzer
from .analysis.champion_scores import GlobalScoreCalculator
from .analysis.ban_recommendations import BanRecommender
from .analysis import trio_metrics
from .analysis.trio_weights import AdaptiveWeightCalculator
from .analysis.trio_holistic import HolisticTrioFinder
from .analysis.trio_tactics import TrioTacticsReporter
from .analysis.trio_counterpick import CounterpickTrioFinder
from .utils.champion_utils import (
    validate_champion_name,
    validate_champion_data,
    validate_champion_pool,
    select_champion_pool,
    select_extended_champion_pool,
    print_champion_list,
)


class Assistant:
    """
    Main coordinator for League of Legends draft analysis.

    Delegates to specialized modules while maintaining backward compatibility
    with the original monolithic API.

    Data access goes through a local SQLite ``Database`` — the only supported
    backend since the remote PostgreSQL/Neon layer was decommissioned (H2).
    """

    def __init__(self, db: Optional[Database] = None, verbose: bool = False) -> None:
        """
        Initialize Assistant and all sub-components.

        Args:
            db: Optional Database instance to use for data access. Defaults to
                a Database on ``config.DATABASE_PATH``. Connected on init.
            verbose: Enable verbose logging

        Examples:
            >>> # Default: local SQLite at config.DATABASE_PATH
            >>> assistant = Assistant()

            >>> # Explicit database (e.g. a test fixture)
            >>> from src.db import Database
            >>> assistant = Assistant(Database("data/db.db"))
        """
        self.MIN_GAMES = analysis_config.MIN_GAMES_THRESHOLD
        self.verbose = verbose

        self.db = db if db is not None else Database(config.DATABASE_PATH)
        self.db.connect()

        # Performance: In-memory cache for matchups (speeds up draft analysis)
        # Direct cache: champion (as picker) -> [(enemy, delta2, ...)]
        # Reverse cache: champion (as enemy) -> [(picker, delta2, ...)]
        self._matchups_cache: Dict[str, List[tuple]] = {}
        self._reverse_cache: Dict[str, List[tuple]] = {}
        self._cache_enabled = False
        self._cache_hits = 0  # Track cache hits for statistics
        self._cache_misses = 0  # Track cache misses for statistics

    @property
    def db(self) -> Database:
        return self._db

    @db.setter
    def db(self, value: Database) -> None:
        """Rebranche self._db et reconstruit tous les composants spécialisés.

        Rebrancher self.db (fixtures de test, ex. tests/test_ban_recommendations.py)
        sans reconstruire scorer/ban_recommender/etc. laisserait ces composants
        pointer vers l'ancienne base (souvent celle de production) : le setter
        garantit qu'un seul point de vérité (_init_components) les tient à jour.
        """
        self._db = value
        self._init_components()

    def _init_components(self) -> None:
        """(Re)initialise les composants spécialisés à partir de self.db/self.verbose."""
        self.scorer = ChampionScorer(self._db, verbose=self.verbose)
        self.tier_list_gen = TierListGenerator(self._db, self.scorer)
        self.recommender = RecommendationEngine(self._db, self.scorer)
        self.team_analyzer = TeamAnalyzer(self._db, self.scorer)
        self.global_scores = GlobalScoreCalculator(self._db, self.scorer, verbose=self.verbose)
        self.ban_recommender = BanRecommender(self._db, verbose=self.verbose)
        self.trio_weights = AdaptiveWeightCalculator(self._db, verbose=self.verbose)
        self.trio_finder = HolisticTrioFinder(self._db, self.trio_weights, verbose=self.verbose)
        self.trio_tactics = TrioTacticsReporter(self._db, verbose=self.verbose)
        self.trio_counterpick = CounterpickTrioFinder(
            self._db, self.trio_tactics, verbose=self.verbose
        )

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

    # ==================== Cache Management (Performance) ====================

    def warm_cache(self, champion_pool: List[str]) -> None:
        """
        Pre-load matchups for all champions in pool into cache (bidirectional).

        Loads BOTH:
        - Direct cache: champion as picker -> enemies
        - Reverse cache: champion as enemy -> pickers (for ban recommendations)

        Performance impact:
        - First call: ~20ms per champion (2x queries)
        - Reverse lookups: ~99% faster (0 SQL queries after warm-up)

        Args:
            champion_pool: List of champion names to cache matchups for
        """
        if not champion_pool:
            return

        print(f"[CACHE] Warming bidirectional cache for {len(champion_pool)} champions...")
        direct_cached = 0
        reverse_cached = 0

        for champion in champion_pool:
            # Direct cache: champion -> enemies
            matchups = self.db.get_champion_matchups_for_draft(champion)
            if matchups:
                self._matchups_cache[champion] = matchups
                direct_cached += 1

            # Reverse cache: champion as enemy -> pickers
            reverse_matchups = self.db.get_reverse_matchups_for_draft(champion)
            if reverse_matchups:
                self._reverse_cache[champion] = reverse_matchups
                reverse_cached += 1

        self._cache_enabled = True
        print(f"[CACHE] Direct cache: {direct_cached}/{len(champion_pool)} champions")
        print(f"[CACHE] Reverse cache: {reverse_cached}/{len(champion_pool)} champions")

    def clear_cache(self) -> None:
        """
        Clear matchup caches (both direct and reverse) and disable caching.

        Should be called when exiting draft mode to free memory.
        """
        # Print statistics before clearing
        self.print_cache_stats()

        direct_size = len(self._matchups_cache)
        reverse_size = len(self._reverse_cache)
        total_size = direct_size + reverse_size

        self._matchups_cache.clear()
        self._reverse_cache.clear()
        self._cache_enabled = False
        self._cache_hits = 0
        self._cache_misses = 0

        if total_size > 0:
            print(
                f"[CACHE] Cache cleared ({direct_size} direct + {reverse_size} reverse = {total_size} entries)"
            )

    def print_cache_stats(self) -> None:
        """
        Print cache performance statistics (bidirectional cache).

        Shows stats for both direct and reverse cache.
        """
        total_queries = self._cache_hits + self._cache_misses
        if total_queries == 0:
            return

        hit_rate = (self._cache_hits / total_queries) * 100 if total_queries > 0 else 0
        direct_count = len(self._matchups_cache)
        reverse_count = len(self._reverse_cache)

        print(f"\n[CACHE] Performance Statistics:")
        print(f"  - Total queries: {total_queries}")
        print(f"  - Cache hits: {self._cache_hits} ({hit_rate:.1f}%)")
        print(f"  - Cache misses: {self._cache_misses}")
        print(f"  - Direct cache entries: {direct_count} champions")
        print(f"  - Reverse cache entries: {reverse_count} champions")
        print(f"  - Total cached: {direct_count + reverse_count} entries")

        # Estimated performance gain
        if self._cache_hits > 0:
            time_saved_ms = self._cache_hits * 10  # ~10ms per avoided SQL query
            print(f"  - Estimated time saved: ~{time_saved_ms}ms ({time_saved_ms/1000:.2f}s)")

    def get_cached_matchups(self, champion: str) -> List[tuple]:
        """
        Get matchups from cache if available, otherwise fetch from database.

        Returns matchups in optimized format for draft:
        [(enemy_name, delta2, pickrate, games), ...]

        Args:
            champion: Champion name to get matchups for

        Returns:
            List of matchup tuples (4 elements for draft vs 6 for standard query)
        """
        # If cache is enabled and champion is in cache, use it
        if self._cache_enabled and champion in self._matchups_cache:
            self._cache_hits += 1
            return self._matchups_cache[champion]

        # Otherwise fall back to database (optimized query)
        self._cache_misses += 1
        return self.db.get_champion_matchups_for_draft(champion)

    def get_cached_matchup_delta2(self, champion: str, enemy: str) -> Optional[float]:
        """
        Get delta2 for a specific matchup using bidirectional cache.

        Tries BOTH cache directions before falling back to SQL:
        1. Direct cache: champion -> enemy
        2. Reverse cache: enemy -> champion (inverted delta2)

        Performance:
        - Cache hit: ~0.01ms (instant lookup)
        - Cache miss: ~10ms (SQL fallback via db.get_matchup_delta2)

        Args:
            champion: Our champion name
            enemy: Enemy champion name

        Returns:
            Delta2 value if matchup found, None otherwise

        Example:
            >>> delta2 = assistant.get_cached_matchup_delta2("Darius", "Jax")
            >>> # Tries direct cache first, then reverse cache, then SQL
        """
        # Try direct cache: champion -> enemy
        if self._cache_enabled and champion in self._matchups_cache:
            for matchup in self._matchups_cache[champion]:
                if matchup[0] == enemy:  # matchup[0] is enemy_name
                    self._cache_hits += 1
                    return matchup[1]  # matchup[1] is delta2

        # Try reverse cache: enemy -> champion (invert delta2)
        if self._cache_enabled and enemy in self._reverse_cache:
            for matchup in self._reverse_cache[enemy]:
                # In reverse cache, matchup[0] is the "picker" (our champion)
                if matchup[0] == champion:
                    self._cache_hits += 1
                    # Invert delta2: if Jax vs Darius = +3, then Darius vs Jax = -3
                    return -matchup[1]  # matchup[1] is delta2

        # Cache miss - fallback to SQL
        self._cache_misses += 1
        return self.db.get_matchup_delta2(champion, enemy)

    def get_matchups_for_draft(self, champion: str) -> List[Matchup]:
        """
        Get matchups for draft analysis (optimized with cache support).

        This method:
        1. Uses cache if enabled (99% faster after warm-up)
        2. Falls back to optimized DB query if cache miss
        3. Returns Matchup objects for compatibility with scoring methods

        Performance:
        - Cache hit: ~0.01ms (memory lookup)
        - Cache miss: ~10-20ms (optimized SQL query)
        - Without cache: ~10-20ms per call (repeated SQL queries)

        Args:
            champion: Champion name to get matchups for

        Returns:
            List of Matchup objects with complete statistics
        """
        # Get from cache or DB (optimized 4-column format)
        draft_matchups = self.get_cached_matchups(champion)

        # Convert to Matchup objects for scoring methods
        return self._convert_draft_matchups_to_standard(draft_matchups)

    def _convert_draft_matchups_to_standard(self, draft_matchups: List) -> List[Matchup]:
        """
        Convert draft format (4 cols) to Matchup objects for scoring methods.

        Draft format: MatchupDraft(enemy_name, delta2, pickrate, games)
        Standard format: Matchup(enemy_name, winrate, delta1, delta2, pickrate, games)

        Since winrate and delta1 are not used in draft calculations, we fill with dummy values:
        - winrate = 50.0 (neutral)
        - delta1 = 0.0 (neutral)

        Args:
            draft_matchups: List of MatchupDraft objects or tuples (4 elements)

        Returns:
            List of Matchup objects
        """
        standard_matchups = []
        for matchup in draft_matchups:
            if isinstance(matchup, MatchupDraft):
                # MatchupDraft object - use built-in to_matchup() method
                standard_matchups.append(matchup.to_matchup())
            elif isinstance(matchup, tuple) and len(matchup) == 4:
                # Draft format tuple: (enemy_name, delta2, pickrate, games)
                enemy_name, delta2, pickrate, games = matchup
                # Convert to Matchup object
                standard_matchup = Matchup(enemy_name, 50.0, 0.0, delta2, pickrate, games)
                standard_matchups.append(standard_matchup)
            elif isinstance(matchup, Matchup):
                # Already a Matchup object - pass through
                standard_matchups.append(matchup)
            elif isinstance(matchup, tuple) and len(matchup) == 6:
                # Legacy 6-tuple format - convert to Matchup
                standard_matchups.append(Matchup.from_tuple(matchup))
            else:
                # Unknown format - try to pass through
                standard_matchups.append(matchup)

        return standard_matchups

    # ==================== Champion Pool Selection ====================
    # Delegated to utils.champion_utils

    def select_champion_pool(self) -> List[str]:
        """Interactive pool selection for the user."""
        return select_champion_pool()

    def select_extended_champion_pool(self) -> List[str]:
        """Interactive extended pool selection for Team Builder analysis."""
        return select_extended_champion_pool()

    def validate_champion_name(self, name: str) -> Optional[str]:
        """Validate and normalize champion name with fuzzy matching."""
        return validate_champion_name(name)

    def _validate_champion_data(self, champion: str) -> tuple:
        """Validate if a champion has sufficient data in database."""
        return validate_champion_data(self.db, champion)

    def _validate_champion_pool(self, champion_pool: List[str]) -> tuple:
        """Validate entire champion pool and return viable champions."""
        return validate_champion_pool(self.db, champion_pool)

    def print_champion_list(self, champion_list: List[tuple]) -> None:
        """Print formatted champion list."""
        print_champion_list(champion_list)

    # ==================== Scoring Methods ====================
    # Delegated to analysis.scoring.ChampionScorer

    def score_against_team(
        self,
        matchups: List[tuple],
        team: List[str],
        champion_name: str = None,
        banned_champions: List[str] = None,
        lane: Optional[str] = None,
        enemy_lanes: Optional[dict] = None,
        player_lane: Optional[str] = None,
    ) -> float:
        """Calculate advantage against a team composition."""
        return self.scorer.score_against_team(
            matchups,
            team,
            champion_name,
            banned_champions,
            lane=lane,
            enemy_lanes=enemy_lanes,
            player_lane=player_lane,
        )

    def _calculate_team_winrate(self, individual_winrates: List[float]) -> dict:
        """Calculate team win probability from individual champion winrates."""
        return self.scorer.calculate_team_winrate(individual_winrates)

    # ==================== Tier List Generation ====================
    # Delegated to analysis.tier_list.TierListGenerator

    def tierlist_delta2(self, champion_list: List[str]) -> List[tuple]:
        """Generate tier list ranked by average delta2."""
        return self.tier_list_gen.generate_by_delta2(champion_list)

    def generate_tier_list(
        self, champion_pool: List[str], analysis_type: str = "blind_pick"
    ) -> List[dict]:
        """
        Generate tier list with S/A/B/C classification using global normalization.

        Delegates to TierListGenerator for actual implementation.
        """
        return self.tier_list_gen.generate_tier_list(
            champion_pool, analysis_type, verbose=self.verbose
        )

    # ==================== Recommendations ====================
    # Delegated to analysis.recommendations.RecommendationEngine
    # NOTE: draft() is NOT delegated — the active implementation lives in the
    # "Draft & Competitive Methods" section below (a shadowed duplicate that
    # delegated to recommender.draft_simple was removed; pylint E0102).

    def _calculate_and_display_recommendations(
        self,
        enemy_team: List[str],
        ally_team: List[str],
        nb_results: int,
        champion_pool: List[str] = None,
        banned_champions: List[str] = None,
    ) -> List[tuple]:
        """Calculate champion recommendations and display top results."""
        return self.recommender.calculate_and_display_recommendations(
            enemy_team, ally_team, nb_results, champion_pool, banned_champions
        )

    # ==================== Team Analysis ====================
    # Delegated to analysis.team_analysis.TeamAnalyzer

    # ==================== Global Score Calculation ====================

    def calculate_global_scores(self) -> int:
        """
        Calculate and save scores for all champions in the database.

        Should be called after parsing/updating matchup data.

        Returns:
            Number of champions scored and saved
        """
        return self.global_scores.calculate_all()

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

    def optimal_trio_from_pool(self, champion_pool: List[str]) -> tuple:
        """
        Find optimal 3-champion composition from a given pool.

        Algorithm:
        1. Validate champion pool data availability
        2. Find champion with best average delta2 as blind pick
        3. From remaining champions, find duo that maximizes counterpick coverage

        Returns:
            Tuple of (blind_pick, counterpick1, counterpick2, total_score)
        """
        return self.trio_counterpick.optimal_trio_from_pool(
            champion_pool, validate_pool=self._validate_champion_pool
        )

    def optimal_duo_for_champion(
        self, fixed_champion: str, champion_pool: List[str] = None
    ) -> tuple:
        """
        Find the best duo of champions to pair with a fixed champion.

        Algorithm:
        1. Validate fixed champion has data
        2. Validate companion pool has sufficient data
        3. Find the duo that maximizes total counterpick coverage alongside fixed champion

        Returns:
            Tuple of (fixed_champion, companion1, companion2, total_score)
        """
        return self.trio_counterpick.optimal_duo_for_champion(
            fixed_champion,
            champion_pool,
            validate_pool=self._validate_champion_pool,
            validate_champion=self._validate_champion_data,
        )

    def _analyze_trio_tactics(self, trio: tuple) -> None:
        """Provide tactical analysis on how to use the optimal trio."""
        self.trio_tactics.analyze(trio)

    def _analyze_trio_coverage(self, trio: List[str]) -> None:
        """Analyze what the trio covers and potential gaps."""
        self.trio_tactics._analyze_coverage(trio)

    # ==================== Ban Recommendations ====================

    def get_ban_recommendations(self, champion_pool: List[str], num_bans: int = 5) -> List[tuple]:
        """
        Get ban recommendations against a specific champion pool using reverse lookup.

        For each potential enemy pick, finds your BEST response from your pool.
        Prioritizes banning enemies where even your best response is insufficient.

        Returns:
            List of tuples (enemy_name, threat_score, best_response_delta2,
                           best_response_champion, matchups_count)
            Sorted by threat_score (descending)
        """
        return self.ban_recommender.get_ban_recommendations(champion_pool, num_bans)

    def precalculate_pool_bans(self, pool_name: str, champion_pool: List[str]) -> bool:
        """
        Pre-calculate and store ban recommendations for a champion pool in database.

        Should be called during data updates.

        Returns:
            True if successful, False otherwise
        """
        return self.ban_recommender.precalculate_pool_bans(pool_name, champion_pool)

    def precalculate_all_custom_pool_bans(self) -> Dict[str, int]:
        """
        Pre-calculate ban recommendations for all custom (user-created) pools.

        System pools are skipped because they're too large for meaningful ban calculations
        and aren't typically used for draft.

        Returns:
            Dictionary mapping pool names to number of bans calculated
        """
        return self.ban_recommender.precalculate_all_custom_pool_bans()

    # ==================== Holistic Trio Analysis ====================

    def find_optimal_trios_holistic(
        self, champion_pool: List[str], num_results: int = 5, profile: str = "balanced"
    ) -> List[dict]:
        """
        Find optimal 3-champion combinations using holistic evaluation.

        Unlike the blind-pick approach, this evaluates all possible trios as complete units.
        """
        return self.trio_finder.find(
            champion_pool,
            num_results=num_results,
            profile=profile,
            validate_pool=self._validate_champion_pool,
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
