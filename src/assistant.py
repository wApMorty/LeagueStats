"""
Main Assistant class - Coordinator for champion analysis and recommendations.

This is the new modular version that delegates to specialized modules while
maintaining backward compatibility with the original API.
"""

from typing import List, Optional

from .db import Database
from .config import config
from .config_constants import analysis_config

# Import specialized modules
from .analysis.scoring import ChampionScorer
from .analysis.tier_list import TierListGenerator
from .analysis.recommendations import RecommendationEngine
from .analysis.team_analysis import TeamAnalyzer
from .utils.champion_utils import (
    validate_champion_name,
    validate_champion_data,
    validate_champion_pool,
    select_champion_pool,
    select_extended_champion_pool,
    print_champion_list
)


class Assistant:
    """
    Main coordinator for League of Legends draft analysis.

    Delegates to specialized modules while maintaining backward compatibility
    with the original monolithic API.
    """

    def __init__(self, verbose: bool = False) -> None:
        """
        Initialize Assistant and all sub-components.

        Args:
            verbose: Enable verbose logging
        """
        self.MIN_GAMES = analysis_config.MIN_GAMES_THRESHOLD
        self.db = Database(config.DATABASE_PATH)
        self.db.connect()
        self.verbose = verbose

        # Initialize specialized components
        self.scorer = ChampionScorer(self.db, verbose=verbose)
        self.tier_list_gen = TierListGenerator(self.db, self.scorer)
        self.recommender = RecommendationEngine(self.db, self.scorer)
        self.team_analyzer = TeamAnalyzer(self.db, self.scorer)

        # Performance: In-memory cache for matchups (speeds up draft analysis)
        self._matchups_cache: Dict[str, List[tuple]] = {}
        self._cache_enabled = False
        self._cache_hits = 0  # Track cache hits for statistics
        self._cache_misses = 0  # Track cache misses for statistics

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

    # ==================== Cache Management (Performance) ====================

    def warm_cache(self, champion_pool: List[str]) -> None:
        """
        Pre-load matchups for all champions in pool into cache.

        This significantly speeds up draft analysis by eliminating repeated SQL queries.
        Should be called once at the start of a draft session.

        Performance impact:
        - First call: Loads data from DB (~10-20ms per champion)
        - Subsequent calls: ~99% faster (0 SQL queries after warm-up)

        Args:
            champion_pool: List of champion names to cache matchups for
        """
        if not champion_pool:
            return

        print(f"[CACHE] Warming cache for {len(champion_pool)} champions...")
        cached_count = 0

        for champion in champion_pool:
            # Use optimized query (4 columns instead of 6)
            matchups = self.db.get_champion_matchups_for_draft(champion)
            if matchups:
                self._matchups_cache[champion] = matchups
                cached_count += 1

        self._cache_enabled = True
        print(f"[CACHE] Cache warmed: {cached_count}/{len(champion_pool)} champions loaded")

    def clear_cache(self) -> None:
        """
        Clear matchup cache and disable caching.

        Should be called when exiting draft mode to free memory.
        """
        # Print statistics before clearing
        self.print_cache_stats()

        cache_size = len(self._matchups_cache)
        self._matchups_cache.clear()
        self._cache_enabled = False
        self._cache_hits = 0
        self._cache_misses = 0
        if cache_size > 0:
            print(f"[CACHE] Cache cleared ({cache_size} champions removed)")

    def print_cache_stats(self) -> None:
        """
        Print cache performance statistics.

        Shows:
        - Total cache hits vs misses
        - Hit rate percentage
        - Estimated performance gain
        """
        if not self._cache_enabled and self._cache_hits == 0 and self._cache_misses == 0:
            return  # No stats to print

        total_queries = self._cache_hits + self._cache_misses
        if total_queries == 0:
            return

        hit_rate = (self._cache_hits / total_queries) * 100 if total_queries > 0 else 0

        print(f"\n[CACHE] Performance Statistics:")
        print(f"  - Total queries: {total_queries}")
        print(f"  - Cache hits: {self._cache_hits} ({hit_rate:.1f}%)")
        print(f"  - Cache misses: {self._cache_misses}")
        print(f"  - Champions cached: {len(self._matchups_cache)}")

        # Estimated performance gain (assuming 10ms per SQL query vs 0.01ms cache lookup)
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

    def get_matchups_for_draft(self, champion: str) -> List[tuple]:
        """
        Get matchups for draft analysis (optimized with cache support).

        This method:
        1. Uses cache if enabled (99% faster after warm-up)
        2. Falls back to optimized DB query if cache miss
        3. Returns standard 6-column format for compatibility with scoring methods

        Performance:
        - Cache hit: ~0.01ms (memory lookup)
        - Cache miss: ~10-20ms (optimized SQL query)
        - Without cache: ~10-20ms per call (repeated SQL queries)

        Args:
            champion: Champion name to get matchups for

        Returns:
            List of matchup tuples in standard format:
            [(enemy_name, winrate, delta1, delta2, pickrate, games), ...]
        """
        # Get from cache or DB (optimized 4-column format)
        draft_matchups = self.get_cached_matchups(champion)

        # Convert to standard 6-column format for scoring methods
        return self._convert_draft_matchups_to_standard(draft_matchups)

    def _convert_draft_matchups_to_standard(self, draft_matchups: List[tuple]) -> List[tuple]:
        """
        Convert draft format (4 cols) to standard format (6 cols) for scoring methods.

        Draft format: (enemy_name, delta2, pickrate, games)
        Standard format: (enemy_name, winrate, delta1, delta2, pickrate, games)

        Since winrate and delta1 are not used in draft calculations, we fill with dummy values:
        - winrate = 50.0 (neutral)
        - delta1 = 0.0 (neutral)

        Args:
            draft_matchups: List of matchups in draft format (4 elements)

        Returns:
            List of matchups in standard format (6 elements)
        """
        standard_matchups = []
        for matchup in draft_matchups:
            if len(matchup) == 4:
                # Draft format: (enemy_name, delta2, pickrate, games)
                enemy_name, delta2, pickrate, games = matchup
                # Convert to standard: (enemy_name, winrate, delta1, delta2, pickrate, games)
                standard_matchup = (enemy_name, 50.0, 0.0, delta2, pickrate, games)
                standard_matchups.append(standard_matchup)
            else:
                # Already in standard format (6 elements) - pass through
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

    def _filter_valid_matchups(self, matchups: List[tuple]) -> List[tuple]:
        """Filter matchups with sufficient pick rate and games data."""
        return self.scorer.filter_valid_matchups(matchups)

    def avg_delta1(self, matchups: List[tuple]) -> float:
        """Calculate weighted average delta1 from valid matchups."""
        return self.scorer.avg_delta1(matchups)

    def avg_delta2(self, matchups: List[tuple]) -> float:
        """Calculate weighted average delta2 from valid matchups."""
        return self.scorer.avg_delta2(matchups)

    def avg_winrate(self, matchups: List[tuple]) -> float:
        """Calculate weighted average winrate from valid matchups."""
        return self.scorer.avg_winrate(matchups)

    def score_against_team(
        self,
        matchups: List[tuple],
        team: List[str],
        champion_name: str = None
    ) -> float:
        """Calculate advantage against a team composition."""
        return self.scorer.score_against_team(matchups, team, champion_name)

    def _delta2_to_win_advantage(self, delta2: float, champion_name: str) -> float:
        """Convert delta2 value to win advantage using logistic transformation."""
        return self.scorer.delta2_to_win_advantage(delta2, champion_name)

    def _calculate_team_winrate(self, individual_winrates: List[float]) -> dict:
        """Calculate team win probability from individual champion winrates."""
        return self.scorer.calculate_team_winrate(individual_winrates)

    # ==================== Tier List Generation ====================
    # Delegated to analysis.tier_list.TierListGenerator

    def tierlist_delta1(self, champion_list: List[str]) -> List[tuple]:
        """Generate tier list ranked by average delta1."""
        return self.tier_list_gen.generate_by_delta1(champion_list)

    def tierlist_delta2(self, champion_list: List[str]) -> List[tuple]:
        """Generate tier list ranked by average delta2."""
        return self.tier_list_gen.generate_by_delta2(champion_list)

    def tierlist_lane(self, lane: str) -> List[tuple]:
        """Generate tier list for a specific lane using delta2."""
        return self.tier_list_gen.generate_for_lane(lane)

    # ==================== Recommendations ====================
    # Delegated to analysis.recommendations.RecommendationEngine

    def draft(self, nb_results: int) -> None:
        """Interactive draft recommendation (legacy simple version)."""
        return self.recommender.draft_simple(nb_results)

    def _calculate_and_display_recommendations(
        self,
        enemy_team: List[str],
        ally_team: List[str],
        nb_results: int,
        champion_pool: List[str] = None,
        banned_champions: List[str] = None
    ) -> List[tuple]:
        """Calculate champion recommendations and display top results."""
        return self.recommender.calculate_and_display_recommendations(
            enemy_team, ally_team, nb_results, champion_pool, banned_champions
        )

    # ==================== Team Analysis ====================
    # Delegated to analysis.team_analysis.TeamAnalyzer

    def score_teams(self, team1: List[str], team2: List[str]) -> None:
        """Statistical team analysis using geometric mean for team winrates."""
        return self.team_analyzer.analyze_teams(team1, team2)

    def score_teams_no_input(self) -> None:
        """Interactive team analysis with user input."""
        return self.team_analyzer.analyze_teams_interactive()
