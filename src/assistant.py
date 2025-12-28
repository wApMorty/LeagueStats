"""
Main Assistant class - Coordinator for champion analysis and recommendations.

This is the new modular version that delegates to specialized modules while
maintaining backward compatibility with the original API.
"""

from typing import Dict, List, Optional

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
    print_champion_list,
)
from .utils.display import safe_print
from .constants import CHAMPION_POOL


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
        self, matchups: List[tuple], team: List[str], champion_name: str = None
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

    def draft(self, nb_results: int) -> None:
        """Interactive draft recommendation (legacy simple version)."""
        return self.recommender.draft_simple(nb_results)

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

    def score_teams(self, team1: List[str], team2: List[str]) -> None:
        """Statistical team analysis using geometric mean for team winrates."""
        return self.team_analyzer.analyze_teams(team1, team2)

    def score_teams_no_input(self) -> None:
        """Interactive team analysis with user input."""
        return self.team_analyzer.analyze_teams_interactive()

    # ==================== Global Score Calculation ====================

    def calculate_global_scores(self) -> int:
        """
        Calculate and save scores for all champions in the database.

        This function computes raw metrics (avg_delta2, variance, coverage,
        peak_impact, volatility, target_ratio) for all champions and stores
        them in the champion_scores table.

        Should be called after parsing/updating matchup data.

        Returns:
            Number of champions scored and saved
        """
        from .config import tierlist_config
        import statistics

        print("[INFO] Calculating global champion scores...")

        champions_scored = 0
        all_champions = list(self.db.get_all_champion_names().values())

        for champion in all_champions:
            try:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if not matchups:
                    if self.verbose:
                        print(f"  [SKIP] {champion}: No matchups found")
                    continue

                valid_matchups = self._filter_valid_matchups(matchups)
                if not valid_matchups:
                    if self.verbose:
                        print(f"  [SKIP] {champion}: No valid matchups after filtering")
                    continue

                # Calculate raw metrics
                avg_delta2 = self.avg_delta2(matchups)

                delta2_values = [m[3] for m in valid_matchups]
                variance = statistics.variance(delta2_values) if len(delta2_values) > 1 else 0.0

                # Coverage (blind pick metric)
                decent_weight = sum(
                    m[4] for m in matchups if m[3] > tierlist_config.DECENT_MATCHUP_THRESHOLD
                )
                total_weight = sum(m[4] for m in matchups)
                coverage = decent_weight / total_weight if total_weight > 0 else 0.0

                # Peak impact (counter pick metric)
                excellent_impact = sum(
                    m[3] * m[4]
                    for m in matchups
                    if m[3] > tierlist_config.EXCELLENT_MATCHUP_THRESHOLD
                )
                good_impact = sum(
                    m[3] * m[4]
                    for m in matchups
                    if tierlist_config.GOOD_MATCHUP_THRESHOLD
                    < m[3]
                    <= tierlist_config.EXCELLENT_MATCHUP_THRESHOLD
                )
                peak_impact = excellent_impact + good_impact * 0.5

                # Volatility (counter pick metric) - same as variance
                volatility = variance

                # Target ratio (counter pick metric)
                viable_weight = sum(
                    m[4] for m in matchups if m[3] > tierlist_config.GOOD_MATCHUP_THRESHOLD
                )
                target_ratio = viable_weight / total_weight if total_weight > 0 else 0.0

                # Get champion ID and save scores
                champion_id = self.db.get_champion_id(champion)
                if champion_id is None:
                    if self.verbose:
                        print(f"  [ERROR] {champion}: Could not get champion ID")
                    continue

                self.db.save_champion_scores(
                    champion_id=champion_id,
                    avg_delta2=avg_delta2,
                    variance=variance,
                    coverage=coverage,
                    peak_impact=peak_impact,
                    volatility=volatility,
                    target_ratio=target_ratio,
                )

                champions_scored += 1
                if self.verbose:
                    print(
                        f"  [OK] {champion}: avg_delta2={avg_delta2:.3f}, variance={variance:.3f}, coverage={coverage:.3f}"
                    )

            except Exception as e:
                print(f"  [ERROR] {champion}: {e}")
                continue

        print(f"[SUCCESS] Scored {champions_scored}/{len(all_champions)} champions")
        return champions_scored

    # ==================== Optimal Trio Analysis ====================
    # These methods find optimal champion compositions for draft phases

    def _display_live_podium(
        self, top_duos: List[dict], tested: int, total: int, viable: int
    ) -> None:
        """Display live podium of top 3 duos during evaluation."""
        import sys

        # Clear previous lines (move cursor up 6 lines and clear)
        if tested > 50:  # Don't clear on first display
            sys.stdout.write("\033[6A")  # Move up 6 lines
            sys.stdout.write("\033[J")  # Clear from cursor to end of screen

        progress_pct = (tested / total) * 100
        bar_width = 30
        filled = int(bar_width * tested / total)
        bar = "█" * filled + "░" * (bar_width - filled)

        print(f"Progress: [{bar}] {progress_pct:.1f}% ({tested}/{total}) | Viable: {viable}")
        print("─" * 80)

        if not top_duos:
            print("🔍 Searching for optimal duos...")
            print()
            return

        medals = ["🥇", "🥈", "🥉"]
        for i, duo_info in enumerate(top_duos):
            duo = duo_info["duo"]
            score = duo_info["total_score"]
            coverage = duo_info["coverage"]

            medal = medals[i] if i < len(medals) else f"{i+1}."
            print(f"{medal} {duo[0]} + {duo[1]} | Score: {score:.1f} | Coverage: {coverage:.1%}")

        # Add empty lines to keep spacing consistent
        for _ in range(3 - len(top_duos)):
            print()

        sys.stdout.flush()

    def _find_optimal_counterpick_duo(
        self, remaining_pool: List[str], blind_champion: str, show_ranking: bool = False
    ) -> tuple:
        """Find the best duo of counterpicks to maximize coverage against all champions."""
        from itertools import combinations
        import sys

        if len(remaining_pool) < 2:
            raise ValueError(f"Need at least 2 champions in pool, got {len(remaining_pool)}")

        duo_rankings = []  # Store all viable duos with their scores
        evaluated_combinations = 0
        filtered_by_coverage = 0
        duos_tested = 0

        # Get all champions from database (dynamic, includes new champions like Zaahen)
        all_champions = list(self.db.get_all_champion_names().values())
        total_enemies = len(all_champions)

        total_combinations = len(list(combinations(remaining_pool, 2)))
        print(f"\n🔍 Evaluating {total_combinations} possible duos...\n")

        # Try all possible pairs from remaining pool
        for duo in combinations(remaining_pool, 2):
            duos_tested += 1

            try:
                total_score = 0
                trio = [blind_champion] + list(duo)
                valid_matchups_found = 0

                # For each enemy champion, find the best counter from our trio
                for enemy_champion in all_champions:
                    best_counter_score = -float("inf")

                    for our_champion in trio:
                        try:
                            matchups = self.db.get_champion_matchups_by_name(our_champion)
                            if not matchups:
                                continue

                            # Find the specific matchup against this enemy
                            for matchup in matchups:
                                if matchup[0].lower() == enemy_champion.lower():
                                    if matchup[3] > best_counter_score:  # delta2 is at index 3
                                        best_counter_score = matchup[3]
                                    break
                        except Exception as e:
                            continue  # Skip silently for cleaner output

                    # If we found a matchup, add it to total score
                    if best_counter_score != -float("inf"):
                        total_score += best_counter_score
                        valid_matchups_found += 1

                # Calculate coverage metrics
                coverage_ratio = valid_matchups_found / total_enemies
                avg_score_per_matchup = (
                    total_score / valid_matchups_found if valid_matchups_found > 0 else 0
                )

                # Only consider this duo if it has reasonable coverage
                if coverage_ratio < 0.10:  # Less than 10% coverage
                    filtered_by_coverage += 1
                    continue

                evaluated_combinations += 1

                # Store duo info for ranking
                duo_rankings.append(
                    {
                        "duo": duo,
                        "total_score": total_score,
                        "coverage": coverage_ratio,
                        "avg_score": avg_score_per_matchup,
                        "matchups_covered": valid_matchups_found,
                    }
                )

                # Sort to keep top 3 and display real-time podium
                duo_rankings.sort(key=lambda x: x["total_score"], reverse=True)

                # Display live podium every 50 duos (or if in top 3)
                if duos_tested % 50 == 0 or len(duo_rankings) <= 3:
                    self._display_live_podium(
                        duo_rankings[:3], duos_tested, total_combinations, evaluated_combinations
                    )

            except Exception as e:
                continue  # Skip silently for cleaner output

        # Final podium
        print("\n" + "=" * 80)
        print(
            f"✅ Evaluation complete: {duos_tested}/{total_combinations} tested, {evaluated_combinations} viable"
        )

        if evaluated_combinations == 0:
            raise ValueError(
                f"No valid duo combinations could be evaluated (filtered {filtered_by_coverage} duos with <10% coverage)"
            )

        # Sort by total score (descending)
        duo_rankings.sort(key=lambda x: x["total_score"], reverse=True)

        if not duo_rankings:
            raise ValueError("No viable duo found after evaluation")

        # Display rankings if requested
        if show_ranking and len(duo_rankings) > 1:
            safe_print(f"\n📊 TOP DUO RANKINGS:")
            safe_print("─" * 80)
            display_count = min(5, len(duo_rankings))  # Show top 5

            for i, info in enumerate(duo_rankings[:display_count]):
                duo = info["duo"]
                score = info["total_score"]
                coverage = info["coverage"]
                avg_score = info["avg_score"]

                rank_symbol = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."

                safe_print(f"{rank_symbol} {duo[0]} + {duo[1]}")
                print(
                    f"    Total Score: {score:.1f} | Coverage: {coverage:.1%} | Avg/Match: {avg_score:.2f}"
                )

        print(f"Evaluated {evaluated_combinations} valid combinations")

        best_info = duo_rankings[0]
        return best_info["duo"], best_info["total_score"]

    def optimal_trio_from_pool(self, champion_pool: List[str]) -> tuple:
        """
        Find optimal 3-champion composition from a given pool.

        Algorithm:
        1. Validate champion pool data availability
        2. Find champion with best average delta2 as blind pick
        3. From remaining champions, find duo that maximizes counterpick coverage

        Args:
            champion_pool: List of champion names to choose from

        Returns:
            Tuple of (blind_pick, counterpick1, counterpick2, total_score)

        Raises:
            ValueError: If insufficient champions with data available
        """
        if len(champion_pool) < 3:
            raise ValueError("Champion pool must contain at least 3 champions")

        print(f"Analyzing optimal trio from pool: {champion_pool}")

        # Step 0: Validate champion data availability
        viable_champions, validation_report = self._validate_champion_pool(champion_pool)

        if len(viable_champions) < 3:
            safe_print(f"\n❌ ERROR: Only {len(viable_champions)} champions have sufficient data.")
            print("Need at least 3 champions with data to form a trio.")
            print("\nChampions with insufficient data:")
            for champ, data in validation_report.items():
                if not data["has_data"]:
                    print(f"  - {champ}: {data['matchups']} matchups, {data['total_games']} games")
            raise ValueError(f"Insufficient data: only {len(viable_champions)}/3 champions viable")

        if len(viable_champions) < len(champion_pool):
            safe_print(
                f"\n⚠️  WARNING: Using {len(viable_champions)} viable champions out of {len(champion_pool)} requested"
            )

        # Step 1: Find best blind pick (highest average delta2) from viable champions
        blind_candidates = []

        print(f"\nAnalyzing blind pick candidates from viable champions...")
        for champion in viable_champions:
            score = validation_report[champion]["avg_delta2"]
            games = validation_report[champion]["total_games"]
            matchups = validation_report[champion]["matchups"]

            blind_candidates.append(
                {
                    "champion": champion,
                    "avg_delta2": score,
                    "total_games": games,
                    "matchups": matchups,
                }
            )

        # Sort by avg_delta2 (descending)
        blind_candidates.sort(key=lambda x: x["avg_delta2"], reverse=True)

        if not blind_candidates:
            raise ValueError("No viable blind pick champion found")

        # Display blind pick rankings
        safe_print(f"\n🎯 BLIND PICK RANKINGS:")
        safe_print("─" * 60)
        display_count = min(len(viable_champions), 5)  # Show all viable or max 5

        for i, candidate in enumerate(blind_candidates[:display_count]):
            champ = candidate["champion"]
            score = candidate["avg_delta2"]
            games = candidate["total_games"]
            matchups = candidate["matchups"]

            rank_symbol = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."

            safe_print(f"{rank_symbol} {champ}")
            print(f"    Avg Delta2: {score:.2f} | Games: {games:,} | Matchups: {matchups}")

        best_blind = blind_candidates[0]["champion"]
        best_blind_score = blind_candidates[0]["avg_delta2"]

        safe_print(f"\n✅ Selected blind pick: {best_blind} (avg delta2: {best_blind_score:.2f})")

        # Step 2: Find best counterpick duo from remaining viable champions
        remaining_pool = [champ for champ in viable_champions if champ != best_blind]

        if len(remaining_pool) < 2:
            raise ValueError(
                f"Insufficient remaining champions for duo: only {len(remaining_pool)} available"
            )

        try:
            best_duo, duo_score = self._find_optimal_counterpick_duo(
                remaining_pool, best_blind, show_ranking=True
            )
        except Exception as e:
            print(f"Error finding optimal duo: {e}")
            raise ValueError(f"Failed to find optimal counterpick duo: {e}")

        if best_duo is None:
            raise ValueError("No viable counterpick duo found")

        total_score = best_blind_score + duo_score

        print(f"Best counterpick duo: {best_duo}")
        print(f"Total coverage score: {total_score:.2f}")
        safe_print(
            f"\n✅ Optimal trio: {best_blind} (blind) + {best_duo[0]} + {best_duo[1]} (counterpicks)"
        )

        # Add tactical analysis
        result_trio = (best_blind, best_duo[0], best_duo[1], total_score)
        self._analyze_trio_tactics(result_trio)

        return result_trio

    def optimal_duo_for_champion(
        self, fixed_champion: str, champion_pool: List[str] = None
    ) -> tuple:
        """
        Find the best duo of champions to pair with a fixed champion.

        Algorithm:
        1. Validate fixed champion has data
        2. Validate companion pool has sufficient data
        3. Find the duo that maximizes total counterpick coverage alongside fixed champion

        Args:
            fixed_champion: The champion that must be in the trio
            champion_pool: Pool to choose companions from (default: CHAMPION_POOL)

        Returns:
            Tuple of (fixed_champion, companion1, companion2, total_score)

        Raises:
            ValueError: If fixed champion or insufficient companions have data
        """
        if champion_pool is None:
            champion_pool = CHAMPION_POOL.copy()

        print(f"Finding optimal duo to pair with: {fixed_champion}")

        # Step 0: Validate fixed champion has data
        has_data, matchups, games, delta2 = self._validate_champion_data(fixed_champion)

        if not has_data:
            safe_print(f"\n❌ ERROR: Fixed champion '{fixed_champion}' has insufficient data")
            print(f"  Matchups: {matchups}, Games: {games}")
            raise ValueError(f"Fixed champion '{fixed_champion}' has insufficient data in database")

        safe_print(
            f"✅ Fixed champion validated: {matchups} matchups, {games} total games, {delta2:.2f} avg delta2"
        )

        # Remove the fixed champion from the pool if it's there
        available_pool = [
            champ for champ in champion_pool if champ.lower() != fixed_champion.lower()
        ]

        if len(available_pool) < 2:
            raise ValueError(
                "Champion pool must contain at least 2 champions besides the fixed one"
            )

        # Step 1: Validate available companion pool
        viable_companions, validation_report = self._validate_champion_pool(available_pool)

        if len(viable_companions) < 2:
            safe_print(
                f"\n❌ ERROR: Only {len(viable_companions)} companions have sufficient data."
            )
            print("Need at least 2 viable companions to form a duo.")
            print("\nCompanions with insufficient data:")
            for champ, data in validation_report.items():
                if not data["has_data"]:
                    print(f"  - {champ}: {data['matchups']} matchups, {data['total_games']} games")
            raise ValueError(
                f"Insufficient companion data: only {len(viable_companions)}/2 champions viable"
            )

        if len(viable_companions) < len(available_pool):
            safe_print(
                f"\n⚠️  WARNING: Using {len(viable_companions)} viable companions out of {len(available_pool)} available"
            )

        # Step 2: Find best duo from viable companions
        try:
            best_duo, duo_score = self._find_optimal_counterpick_duo(
                viable_companions, fixed_champion, show_ranking=True
            )
        except Exception as e:
            print(f"Error finding optimal duo: {e}")
            raise ValueError(f"Failed to find optimal companion duo: {e}")

        if best_duo is None:
            raise ValueError("No viable companion duo found")

        total_score = delta2 + duo_score

        print(f"\nBest companions: {best_duo}")
        print(f"Total coverage score: {total_score:.2f}")
        safe_print(f"\n✅ Optimal trio: {fixed_champion} + {best_duo[0]} + {best_duo[1]}")

        # Add tactical analysis
        result_trio = (fixed_champion, best_duo[0], best_duo[1], total_score)
        self._analyze_trio_tactics(result_trio)

        return result_trio

    def _analyze_trio_tactics(self, trio: tuple) -> None:
        """
        Provide tactical analysis on how to use the optimal trio.

        Args:
            trio: (champion1, champion2, champion3) - the optimal trio
        """
        blind_pick, counter1, counter2 = trio[:3]

        safe_print(f"\n🎮 TACTICAL ANALYSIS:")
        safe_print("=" * 80)
        print(f"Your optimal trio: {blind_pick} (Blind) + {counter1} + {counter2} (Counterpicks)")

        # Analyze each champion's role and best matchups
        trio_champions = [blind_pick, counter1, counter2]

        for i, champion in enumerate(trio_champions):
            role = "BLIND PICK" if i == 0 else f"COUNTERPICK #{i}"

            try:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if not matchups:
                    continue

                # Find best and worst matchups
                valid_matchups = [
                    (m[0], m[3]) for m in matchups if m[5] >= 200
                ]  # enemy, delta2, min 200 games
                valid_matchups.sort(key=lambda x: x[1], reverse=True)  # Sort by delta2

                if not valid_matchups:
                    continue

                safe_print(f"\n🔸 {champion} ({role}):")

                # Best matchups (top 5)
                best_matchups = valid_matchups[:5]
                safe_print(f"  ✅ STRONG AGAINST:")
                for enemy, delta2 in best_matchups:
                    print(f"    • {enemy} ({delta2:+.2f} delta2)")

                # Worst matchups (bottom 5, but only show negatives)
                worst_matchups = [
                    m for m in valid_matchups[-10:] if m[1] < 0
                ]  # Only negative deltas
                worst_matchups = sorted(worst_matchups, key=lambda x: x[1])[:5]  # Worst 5

                if worst_matchups:
                    safe_print(f"  ⚠️  WEAK AGAINST:")
                    for enemy, delta2 in worst_matchups:
                        print(f"    • {enemy} ({delta2:+.2f} delta2)")

                # Neutral matchups count
                neutral_count = sum(1 for _, delta2 in valid_matchups if -1 <= delta2 <= 1)
                safe_print(f"  ➖ NEUTRAL MATCHUPS: {neutral_count} champions")

            except Exception as e:
                print(f"  Error analyzing {champion}: {e}")
                continue

        # Coverage analysis
        self._analyze_trio_coverage(trio_champions)

    def _analyze_trio_coverage(self, trio: List[str]) -> None:
        """Analyze what the trio covers and potential gaps."""

        safe_print(f"\n📊 COVERAGE ANALYSIS:")
        safe_print("─" * 50)

        # Get all champions from database (dynamic, includes new champions)
        all_champions = list(self.db.get_all_champion_names().values())

        coverage_map = {}  # enemy -> best_counter_info
        uncovered_enemies = []

        for enemy_champion in all_champions:
            best_counter = None
            best_delta2 = -float("inf")

            for our_champion in trio:
                try:
                    matchups = self.db.get_champion_matchups_by_name(our_champion)

                    for matchup in matchups:
                        if matchup[0].lower() == enemy_champion.lower():
                            if matchup[3] > best_delta2:  # delta2 better
                                best_delta2 = matchup[3]
                                best_counter = our_champion
                            break
                except:
                    continue

            if best_counter:
                coverage_map[enemy_champion] = (best_counter, best_delta2)
            else:
                uncovered_enemies.append(enemy_champion)

        # Statistics
        total_enemies = len(all_champions)
        covered_count = len(coverage_map)
        coverage_percent = (covered_count / total_enemies) * 100

        safe_print(f"📈 COVERAGE STATS:")
        print(f"  • Covered: {covered_count}/{total_enemies} champions ({coverage_percent:.1f}%)")

        # Categorize coverage quality
        excellent = [(e, c, d) for e, (c, d) in coverage_map.items() if d >= 2.0]
        good = [(e, c, d) for e, (c, d) in coverage_map.items() if 1.0 <= d < 2.0]
        decent = [(e, c, d) for e, (c, d) in coverage_map.items() if 0 <= d < 1.0]
        struggling = [(e, c, d) for e, (c, d) in coverage_map.items() if d < 0]

        if excellent:
            safe_print(
                f"  🟢 EXCELLENT counters: {len(excellent)} ({len(excellent)/covered_count*100:.1f}%)"
            )
        if good:
            safe_print(f"  🟡 GOOD counters: {len(good)} ({len(good)/covered_count*100:.1f}%)")
        if decent:
            safe_print(
                f"  🟠 DECENT counters: {len(decent)} ({len(decent)/covered_count*100:.1f}%)"
            )
        if struggling:
            safe_print(
                f"  🔴 STRUGGLING against: {len(struggling)} ({len(struggling)/covered_count*100:.1f}%)"
            )

        # Show problematic matchups
        if struggling:
            safe_print(f"\n⚠️  DIFFICULT MATCHUPS:")
            worst_struggling = sorted(struggling, key=lambda x: x[2])[:3]  # Worst 3
            for enemy, counter, delta2 in worst_struggling:
                print(f"    • {enemy}: Best answer is {counter} ({delta2:+.2f} delta2)")

        if uncovered_enemies:
            safe_print(f"\n❌ UNCOVERED CHAMPIONS ({len(uncovered_enemies)}):")
            if len(uncovered_enemies) <= 5:
                for enemy in uncovered_enemies:
                    print(f"    • {enemy}")
            else:
                for enemy in uncovered_enemies[:3]:
                    print(f"    • {enemy}")
                print(f"    ... and {len(uncovered_enemies)-3} more")

        # Draft recommendations
        safe_print(f"\n💡 DRAFT RECOMMENDATIONS:")
        if coverage_percent >= 85:
            safe_print("  🟢 Excellent pool! Very few gaps.")
        elif coverage_percent >= 70:
            safe_print("  🟡 Good pool with minor gaps.")
        elif coverage_percent >= 50:
            safe_print("  🟠 Decent pool but consider expanding.")
        else:
            safe_print("  🔴 Pool has significant gaps - consider more champions.")

        if len(excellent) > len(struggling):
            safe_print("  📈 Pool favors aggressive counterpicking.")
        else:
            safe_print("  🛡️ Pool requires careful champion selection.")

    # ==================== Ban Recommendations ====================

    def get_ban_recommendations(self, champion_pool: List[str], num_bans: int = 5) -> List[tuple]:
        """
        Get ban recommendations against a specific champion pool using reverse lookup.

        For each potential enemy pick, finds your BEST response from your pool.
        Prioritizes banning enemies where even your best response is insufficient.

        Args:
            champion_pool: List of champion names in your pool
            num_bans: Number of ban recommendations to return

        Returns:
            List of tuples (enemy_name, threat_score, best_response_delta2)
            Sorted by threat_score (descending)
        """
        from .config import config

        # Get all potential enemies from database
        all_potential_enemies = set()
        for our_champion in champion_pool:
            try:
                matchups = self.db.get_champion_matchups_by_name(our_champion)
                for enemy_name, winrate, delta1, delta2, pickrate, games in matchups:
                    if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                        all_potential_enemies.add(enemy_name)
            except Exception as e:
                if self.verbose:
                    print(f"Error getting enemies for {our_champion}: {e}")
                continue

        ban_candidates = []

        # For each potential enemy, find our best response
        for enemy_champion in all_potential_enemies:
            best_response_delta2 = -float("inf")
            best_response_champion = None
            enemy_pickrate = 0.0
            matchups_found = 0

            # Check all our champions against this enemy
            for our_champion in champion_pool:
                try:
                    delta2 = self.db.get_matchup_delta2(our_champion, enemy_champion)

                    if delta2 is not None:
                        matchups_found += 1

                        # Track the best response we have
                        if delta2 > best_response_delta2:
                            best_response_delta2 = delta2
                            best_response_champion = our_champion

                        # Also get pickrate data for this enemy (approximate from one of our matchups)
                        if enemy_pickrate == 0.0:
                            try:
                                matchups = self.db.get_champion_matchups_by_name(our_champion)
                                for enemy_name, winrate, delta1, d2, pickrate, games in matchups:
                                    if enemy_name == enemy_champion:
                                        enemy_pickrate = pickrate
                                        break
                            except Exception as e:
                                if self.verbose:
                                    print(
                                        f"[WARNING] Failed to get pickrate for {enemy_champion}: {e}"
                                    )
                                # enemy_pickrate remains 0.0 as fallback

                except (AttributeError, TypeError) as e:
                    # Specific errors we expect: bad champion names, DB not initialized
                    print(f"[ERROR] Invalid matchup check {our_champion} vs {enemy_champion}: {e}")
                    continue
                except Exception as e:
                    # Unexpected errors - always log for debugging
                    print(
                        f"[ERROR] Unexpected error checking {our_champion} vs {enemy_champion}: {e}"
                    )
                    continue

            # Skip if no valid matchups found
            if best_response_champion is None or matchups_found == 0:
                continue

            # Calculate threat score: Higher score = enemy should be banned
            # Key insight: If even our BEST response has negative delta2, this enemy is very threatening
            base_threat = -best_response_delta2  # Invert: negative delta2 = high threat

            # Weight by pickrate and coverage
            pickrate_weight = max(enemy_pickrate, 1.0)  # At least 1.0 to avoid zero weights
            coverage_bonus = min(
                matchups_found / len(champion_pool), 1.0
            )  # How much of our pool this affects

            # Combined threat score
            # - Main factor: How bad is our best response? (70%)
            # - Secondary: How popular is this enemy? (20%)
            # - Tertiary: How much of our pool does it affect? (10%)
            combined_threat = (
                base_threat * 0.7
                + pickrate_weight * 0.2
                + coverage_bonus * 10.0 * 0.1  # Scale coverage to reasonable range
            )

            ban_candidates.append(
                (
                    enemy_champion,
                    combined_threat,
                    best_response_delta2,
                    best_response_champion,
                    matchups_found,
                )
            )

        # Sort by combined threat (descending)
        ban_candidates.sort(key=lambda x: x[1], reverse=True)

        # Return in clean format: (enemy, threat_score, best_response_delta2)
        return [
            (name, threat, best_delta2)
            for name, threat, best_delta2, _, _ in ban_candidates[:num_bans]
        ]

    def precalculate_pool_bans(self, pool_name: str, champion_pool: List[str]) -> bool:
        """
        Pre-calculate and store ban recommendations for a champion pool in database.

        This method calculates ban recommendations once and stores them in the database
        for fast retrieval during draft. Should be called during data updates.

        Args:
            pool_name: Name of the champion pool
            champion_pool: List of champion names in the pool

        Returns:
            True if successful, False otherwise
        """
        from .config import config

        if not champion_pool:
            if self.verbose:
                print(f"[DEBUG] Empty champion pool: {pool_name}")
            return False

        try:
            # Get all potential enemies from database
            all_potential_enemies = set()
            for our_champion in champion_pool:
                try:
                    matchups = self.db.get_champion_matchups_by_name(our_champion)
                    for enemy_name, winrate, delta1, delta2, pickrate, games in matchups:
                        if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                            all_potential_enemies.add(enemy_name)
                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Error getting enemies for {our_champion}: {e}")
                    continue

            ban_candidates = []

            # For each potential enemy, find our best response
            for enemy_champion in all_potential_enemies:
                best_response_delta2 = -float("inf")
                best_response_champion = None
                enemy_pickrate = 0.0
                matchups_found = 0

                # Check all our champions against this enemy
                for our_champion in champion_pool:
                    try:
                        delta2 = self.db.get_matchup_delta2(our_champion, enemy_champion)

                        if delta2 is not None:
                            matchups_found += 1

                            # Track the best response we have
                            if delta2 > best_response_delta2:
                                best_response_delta2 = delta2
                                best_response_champion = our_champion

                            # Get pickrate data for this enemy
                            if enemy_pickrate == 0.0:
                                try:
                                    matchups = self.db.get_champion_matchups_by_name(our_champion)
                                    for (
                                        enemy_name,
                                        winrate,
                                        delta1,
                                        d2,
                                        pickrate,
                                        games,
                                    ) in matchups:
                                        if enemy_name == enemy_champion:
                                            enemy_pickrate = pickrate
                                            break
                                except:
                                    pass

                    except Exception as e:
                        if self.verbose:
                            print(f"[DEBUG] Error checking {our_champion} vs {enemy_champion}: {e}")
                        continue

                # Skip if no valid matchups found
                if best_response_champion is None or matchups_found == 0:
                    continue

                # Calculate threat score
                base_threat = -best_response_delta2
                pickrate_weight = max(enemy_pickrate, 1.0)
                coverage_bonus = min(matchups_found / len(champion_pool), 1.0)

                combined_threat = (
                    base_threat * 0.7 + pickrate_weight * 0.2 + coverage_bonus * 10.0 * 0.1
                )

                ban_candidates.append(
                    (
                        enemy_champion,
                        combined_threat,
                        best_response_delta2,
                        best_response_champion,
                        matchups_found,
                    )
                )

            # Save to database
            saved = self.db.save_pool_ban_recommendations(pool_name, ban_candidates)

            if self.verbose:
                print(f"[INFO] Pre-calculated {saved} ban recommendations for pool '{pool_name}'")

            return saved > 0

        except Exception as e:
            print(f"[ERROR] Failed to pre-calculate bans for {pool_name}: {e}")
            return False

    def precalculate_all_custom_pool_bans(self) -> Dict[str, int]:
        """
        Pre-calculate ban recommendations for all custom (user-created) pools.

        System pools are skipped because they're too large for meaningful ban calculations
        and aren't typically used for draft.

        Returns:
            Dictionary mapping pool names to number of bans calculated
        """
        from .pool_manager import PoolManager

        results = {}

        try:
            # Load pool manager
            pool_manager = PoolManager()

            # Get all pools
            all_pools = pool_manager.get_all_pools()

            if self.verbose:
                print(f"[INFO] Found {len(all_pools)} total pools")

            # Process only custom pools (skip system pools)
            custom_pools = {
                name: pool for name, pool in all_pools.items() if pool.created_by == "user"
            }

            if not custom_pools:
                print("[INFO] No custom pools found - nothing to pre-calculate")
                return results

            print(
                f"[INFO] Pre-calculating ban recommendations for {len(custom_pools)} custom pools..."
            )

            for pool_name, pool in custom_pools.items():
                if self.verbose:
                    print(f"[INFO] Processing pool: {pool_name} ({len(pool.champions)} champions)")

                success = self.precalculate_pool_bans(pool_name, pool.champions)

                if success:
                    # Get count of saved bans
                    saved_count = len(self.db.get_pool_ban_recommendations(pool_name, limit=999))
                    results[pool_name] = saved_count
                    print(f"  [OK] {pool_name}: {saved_count} bans calculated")
                else:
                    results[pool_name] = 0
                    print(f"  [FAIL] {pool_name}: Failed")

            print(f"[SUCCESS] Pre-calculated bans for {len(results)} custom pools")
            return results

        except Exception as e:
            print(f"[ERROR] Failed to pre-calculate custom pool bans: {e}")
            import traceback

            traceback.print_exc()
            return results

    def precalculate_pool_bans(self, pool_name: str, champion_pool: List[str]) -> bool:
        """
        Pre-calculate and store ban recommendations for a champion pool in database.

        This method calculates ban recommendations once and stores them in the database
        for fast retrieval during draft. Should be called during data updates.

        Args:
            pool_name: Name of the champion pool
            champion_pool: List of champion names in the pool

        Returns:
            True if successful, False otherwise
        """
        from .config import config

        if not champion_pool:
            if self.verbose:
                print(f"[DEBUG] Empty champion pool: {pool_name}")
            return False

        try:
            # Get all potential enemies from database
            all_potential_enemies = set()
            for our_champion in champion_pool:
                try:
                    matchups = self.db.get_champion_matchups_by_name(our_champion)
                    for enemy_name, winrate, delta1, delta2, pickrate, games in matchups:
                        if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                            all_potential_enemies.add(enemy_name)
                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Error getting enemies for {our_champion}: {e}")
                    continue

            ban_candidates = []

            # For each potential enemy, find our best response
            for enemy_champion in all_potential_enemies:
                best_response_delta2 = -float('inf')
                best_response_champion = None
                enemy_pickrate = 0.0
                matchups_found = 0

                # Check all our champions against this enemy
                for our_champion in champion_pool:
                    try:
                        delta2 = self.db.get_matchup_delta2(our_champion, enemy_champion)

                        if delta2 is not None:
                            matchups_found += 1

                            # Track the best response we have
                            if delta2 > best_response_delta2:
                                best_response_delta2 = delta2
                                best_response_champion = our_champion

                            # Get pickrate data for this enemy
                            if enemy_pickrate == 0.0:
                                try:
                                    matchups = self.db.get_champion_matchups_by_name(our_champion)
                                    for enemy_name, winrate, delta1, d2, pickrate, games in matchups:
                                        if enemy_name == enemy_champion:
                                            enemy_pickrate = pickrate
                                            break
                                except:
                                    pass

                    except Exception as e:
                        if self.verbose:
                            print(f"[DEBUG] Error checking {our_champion} vs {enemy_champion}: {e}")
                        continue

                # Skip if no valid matchups found
                if best_response_champion is None or matchups_found == 0:
                    continue

                # Calculate threat score
                base_threat = -best_response_delta2
                pickrate_weight = max(enemy_pickrate, 1.0)
                coverage_bonus = min(matchups_found / len(champion_pool), 1.0)

                combined_threat = (
                    base_threat * 0.7 +
                    pickrate_weight * 0.2 +
                    coverage_bonus * 10.0 * 0.1
                )

                ban_candidates.append((
                    enemy_champion,
                    combined_threat,
                    best_response_delta2,
                    best_response_champion,
                    matchups_found
                ))

            # Save to database
            saved = self.db.save_pool_ban_recommendations(pool_name, ban_candidates)

            if self.verbose:
                print(f"[INFO] Pre-calculated {saved} ban recommendations for pool '{pool_name}'")

            return saved > 0

        except Exception as e:
            print(f"[ERROR] Failed to pre-calculate bans for {pool_name}: {e}")
            return False

    def precalculate_all_custom_pool_bans(self) -> Dict[str, int]:
        """
        Pre-calculate ban recommendations for all custom (user-created) pools.

        System pools are skipped because they're too large for meaningful ban calculations
        and aren't typically used for draft.

        Returns:
            Dictionary mapping pool names to number of bans calculated
        """
        from .pool_manager import PoolManager

        results = {}

        try:
            # Load pool manager
            pool_manager = PoolManager()

            # Get all pools
            all_pools = pool_manager.get_all_pools()

            if self.verbose:
                print(f"[INFO] Found {len(all_pools)} total pools")

            # Process only custom pools (skip system pools)
            custom_pools = {
                name: pool for name, pool in all_pools.items()
                if pool.created_by == "user"
            }

            if not custom_pools:
                print("[INFO] No custom pools found - nothing to pre-calculate")
                return results

            print(f"[INFO] Pre-calculating ban recommendations for {len(custom_pools)} custom pools...")

            for pool_name, pool in custom_pools.items():
                if self.verbose:
                    print(f"[INFO] Processing pool: {pool_name} ({len(pool.champions)} champions)")

                success = self.precalculate_pool_bans(pool_name, pool.champions)

                if success:
                    # Get count of saved bans
                    saved_count = len(self.db.get_pool_ban_recommendations(pool_name, limit=999))
                    results[pool_name] = saved_count
                    print(f"  [OK] {pool_name}: {saved_count} bans calculated")
                else:
                    results[pool_name] = 0
                    print(f"  [FAIL] {pool_name}: Failed")

            print(f"[SUCCESS] Pre-calculated bans for {len(results)} custom pools")
            return results

        except Exception as e:
            print(f"[ERROR] Failed to pre-calculate custom pool bans: {e}")
            import traceback
            traceback.print_exc()
            return results

    # ==================== Draft & Competitive Methods ====================

    def draft(self, nb_results: int) -> None:
        """
        Simple draft simulation with recommendations.

        Args:
            nb_results: Number of champion recommendations to display
        """
        enemy_team = []
        ally_team = []

        for i in range(5):
            enemy_champion = input(f"Enemy Champion {i+1}: ")
            enemy_team.append(enemy_champion)

            # Show recommendations after each enemy pick
            self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)

            if i < 4:  # Don't ask for ally pick after last enemy pick
                ally_champion = input(f"Your Champion {i+1}: ")
                ally_team.append(ally_champion)

        # Final team score
        self.score_teams(enemy_team, ally_team)

    def _get_champion_input(self, team_name: str, champion_number: int) -> str:
        """Get champion input from user with consistent formatting."""
        return input(f"{team_name} - Champion {champion_number}: ")

    def _calculate_and_display_recommendations(
        self,
        enemy_team: List[str],
        ally_team: List[str],
        nb_results: int,
        champion_pool: List[str] = None,
    ) -> None:
        """Calculate champion recommendations and display top results."""
        from .constants import SOLOQ_POOL

        if champion_pool is None:
            champion_pool = SOLOQ_POOL

        scores = []

        for champion in champion_pool:
            if champion not in enemy_team and champion not in ally_team:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if sum(m[5] for m in matchups) < config.MIN_GAMES_COMPETITIVE:
                    continue
                score = self.score_against_team(matchups, enemy_team)
                scores.append((str(champion), score))

        scores.sort(key=lambda x: -x[1])

        for index in range(min(nb_results, len(scores))):
            print(scores[index])

    def _draft_red_side(self, enemy_team: List[str], ally_team: List[str], nb_results: int) -> None:
        """Handle red side draft sequence."""
        # Pick 1
        enemy_team.append(self._get_champion_input("Equipe 1", 1))

        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 2", 1))
        ally_team.append(self._get_champion_input("Equipe 2", 2))

        # Pick 2-3
        enemy_team.append(self._get_champion_input("Equipe 1", 2))
        enemy_team.append(self._get_champion_input("Equipe 1", 3))

        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 2", 3))
        ally_team.append(self._get_champion_input("Equipe 2", 4))

        # Pick 4-5
        enemy_team.append(self._get_champion_input("Equipe 1", 4))
        enemy_team.append(self._get_champion_input("Equipe 1", 5))

        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 2", 5))

    def _draft_blue_side(
        self, enemy_team: List[str], ally_team: List[str], nb_results: int
    ) -> None:
        """Handle blue side draft sequence."""
        # Initial recommendations
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)

        # Pick 1
        ally_team.append(self._get_champion_input("Equipe 1", 1))

        enemy_team.append(self._get_champion_input("Equipe 2", 1))
        enemy_team.append(self._get_champion_input("Equipe 2", 2))

        # Pick 2
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 1", 2))
        ally_team.append(self._get_champion_input("Equipe 1", 3))

        # Pick 3-4
        enemy_team.append(self._get_champion_input("Equipe 2", 3))
        enemy_team.append(self._get_champion_input("Equipe 2", 4))

        # Pick 4
        self._calculate_and_display_recommendations(enemy_team, ally_team, nb_results)
        ally_team.append(self._get_champion_input("Equipe 1", 4))
        ally_team.append(self._get_champion_input("Equipe 1", 5))

        enemy_team.append(self._get_champion_input("Equipe 2", 5))

    def competitive_draft(self, nb_results: int) -> None:
        """Simulate a competitive draft with pick recommendations."""
        enemy_team = []
        ally_team = []
        side = input("Side (b/r): ")

        if side.lower() == "r":
            self._draft_red_side(enemy_team, ally_team, nb_results)
            self.score_teams(enemy_team, ally_team)
        elif side.lower() == "b":
            self._draft_blue_side(enemy_team, ally_team, nb_results)
            self.score_teams(ally_team, enemy_team)
        else:
            print("Couldn't parse side")

    def blind_pick(self) -> None:
        """Display tier list for blind pick scenarios."""
        lst = self.tierlist_delta2(list(self.db.get_all_champion_names().values()))
        _results = 10

        if len(lst) < _results:
            for index in range(len(lst)):
                print(lst[index])
        else:
            for index in range(_results):
                print(lst[index])

    # ==================== Holistic Trio Analysis ====================

    def find_optimal_trios_holistic(
        self, champion_pool: List[str], num_results: int = 5, profile: str = "balanced"
    ) -> List[dict]:
        """
        Find optimal 3-champion combinations using holistic evaluation.

        Unlike the blind-pick approach, this evaluates all possible trios as complete units.

        Args:
            champion_pool: List of champion names to choose from
            num_results: Number of top trios to return
            profile: Scoring profile ("safe", "meta", "aggressive", "balanced")

        Returns:
            List of dictionaries with trio information and scores

        Algorithm:
        1. Generate all combinations of 3 champions
        2. For each trio, calculate holistic score based on:
           - Coverage: How well they handle all potential enemies
           - Balance: Diversity of matchup profiles (avoid same weaknesses)
           - Consistency: Reliable performance across situations
           - Meta relevance: Performance against popular picks
        """
        import itertools

        if len(champion_pool) < 3:
            raise ValueError("Champion pool must contain at least 3 champions")

        print(f"Analyzing all trio combinations from pool: {champion_pool}")

        # Step 1: Validate champion data availability
        viable_champions, validation_report = self._validate_champion_pool(champion_pool)

        if len(viable_champions) < 3:
            raise ValueError(f"Insufficient data: only {len(viable_champions)}/3 champions viable")

        # Step 2: Generate all combinations of 3 champions
        trio_combinations = list(itertools.combinations(viable_champions, 3))
        print(f"Evaluating {len(trio_combinations)} trio combinations...")

        trio_rankings = []

        # Set the scoring profile for this analysis
        self.scoring_profile = profile
        if self.verbose:
            print(f"[INFO] Using scoring profile: {profile}")

        # Step 3: Evaluate each trio holistically
        for trio in trio_combinations:
            try:
                trio_score = self._evaluate_trio_holistic(trio)
                trio_rankings.append(
                    {
                        "trio": trio,
                        "total_score": trio_score["total_score"],
                        "coverage_score": trio_score["coverage_score"],
                        "balance_score": trio_score["balance_score"],
                        "consistency_score": trio_score["consistency_score"],
                        "meta_score": trio_score["meta_score"],
                        "enemy_coverage": trio_score["enemy_coverage"],
                    }
                )
            except Exception as e:
                if self.verbose:
                    print(f"Error evaluating trio {trio}: {e}")
                continue

        if not trio_rankings:
            raise ValueError("No viable trios found after evaluation")

        # Step 4: Sort by total score
        trio_rankings.sort(key=lambda x: x["total_score"], reverse=True)

        return trio_rankings[:num_results]

    def _evaluate_trio_holistic(self, trio: tuple) -> dict:
        """
        Evaluate a trio of champions using holistic scoring with reverse lookup.

        Uses efficient reverse lookup to avoid duplicate matchups and improve performance.

        Returns dict with individual scores and total score.
        """
        champion1, champion2, champion3 = trio
        trio_list = [champion1, champion2, champion3]

        # Use reverse lookup to build enemy coverage efficiently
        enemy_coverage = {}  # enemy_name -> (best_delta2, champion_handling_it)

        # Get all champions from database (dynamic, includes new champions)
        all_champions = list(self.db.get_all_champion_names().values())
        for enemy_champion in all_champions:
            best_delta2 = -float("inf")
            best_counter = None

            # For this enemy, check which champion in our trio counters it best
            for our_champion in trio_list:
                try:
                    delta2 = self.db.get_matchup_delta2(our_champion, enemy_champion)

                    if delta2 is not None and delta2 > best_delta2:
                        best_delta2 = delta2
                        best_counter = our_champion

                except Exception as e:
                    if self.verbose:
                        print(f"Error getting matchup {our_champion} vs {enemy_champion}: {e}")
                    continue

            # If we found a valid matchup, record it
            if best_counter is not None and best_delta2 != -float("inf"):
                enemy_coverage[enemy_champion] = (best_delta2, best_counter)

        all_enemies = set(enemy_coverage.keys())

        # Calculate individual scores using the reverse-lookup data
        coverage_score = self._calculate_coverage_score(enemy_coverage, all_enemies)
        balance_score = self._calculate_balance_score_reverse(trio_list, enemy_coverage)
        consistency_score = self._calculate_consistency_score_reverse(trio_list, enemy_coverage)
        meta_score = self._calculate_meta_score(enemy_coverage)

        # Calculate contextual total score using adaptive weights
        total_score, used_weights = self._calculate_contextual_total_score(
            {
                "coverage_score": coverage_score,
                "balance_score": balance_score,
                "consistency_score": consistency_score,
                "meta_score": meta_score,
            },
            profile=getattr(self, "scoring_profile", "balanced"),
        )

        return {
            "total_score": total_score,
            "coverage_score": coverage_score,
            "balance_score": balance_score,
            "consistency_score": consistency_score,
            "meta_score": meta_score,
            "enemy_coverage": enemy_coverage,
        }

    def _calculate_coverage_score(self, enemy_coverage: dict, all_enemies: set) -> float:
        """Calculate how well the trio covers all potential enemies."""
        if not all_enemies:
            return 0.0

        # Sum of best delta2 scores against all enemies
        total_coverage = sum(max(0, delta2) for delta2, _ in enemy_coverage.values())
        max_possible = len(all_enemies) * 10  # Theoretical max delta2 is around 10

        return min(100.0, (total_coverage / max_possible) * 100)

    def _calculate_balance_score_reverse(self, trio_list: List[str], enemy_coverage: dict) -> float:
        """
        Calculate diversity of matchup profiles using reverse lookup data.

        Args:
            trio_list: List of champion names in the trio
            enemy_coverage: Dict mapping enemy -> (delta2, best_counter)

        Returns:
            Balance score 0-100 (higher = more balanced, fewer shared weaknesses)
        """
        try:
            # For each champion, identify their weaknesses from enemy_coverage
            champion_weaknesses = {champ: set() for champ in trio_list}

            for enemy, (best_delta2, best_counter) in enemy_coverage.items():
                # Check each champion individually against this enemy
                for our_champion in trio_list:
                    try:
                        delta2 = self.db.get_matchup_delta2(our_champion, enemy)

                        # If this champion struggles against this enemy (negative delta2)
                        if delta2 is not None and delta2 < -2.0:
                            champion_weaknesses[our_champion].add(enemy)

                    except Exception:
                        continue

            # Calculate overlap in weaknesses
            weakness_sets = list(champion_weaknesses.values())
            if len(weakness_sets) < 2:
                return 50.0

            # Get union and intersection of all weaknesses
            all_weaknesses = set.union(*weakness_sets) if weakness_sets else set()
            shared_weaknesses = set.intersection(*weakness_sets) if weakness_sets else set()

            if len(all_weaknesses) == 0:
                return 100.0  # No weaknesses found

            # Calculate balance: fewer shared weaknesses = better balance
            balance_ratio = 1 - (len(shared_weaknesses) / len(all_weaknesses))
            return balance_ratio * 100

        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Balance score calculation failed: {e}")
            return 50.0  # Neutral score on error

    def _calculate_consistency_score_reverse(
        self, trio_list: List[str], enemy_coverage: dict
    ) -> float:
        """
        Calculate consistency using reverse lookup data.

        Args:
            trio_list: List of champion names in the trio
            enemy_coverage: Dict mapping enemy -> (delta2, best_counter)

        Returns:
            Consistency score 0-100 (higher = more consistent performance)
        """
        try:
            all_delta2_scores = []

            # Collect all delta2 scores from the coverage data
            for enemy, (delta2, counter) in enemy_coverage.items():
                all_delta2_scores.append(delta2)

            if not all_delta2_scores:
                return 0.0

            # Calculate consistency metrics
            import statistics

            mean_score = statistics.mean(all_delta2_scores)

            if len(all_delta2_scores) > 1:
                variance = statistics.variance(all_delta2_scores)
                # Convert variance to consistency score (lower variance = higher consistency)
                consistency = max(0, 100 - (variance * 5))  # Scale appropriately
            else:
                consistency = 50  # Neutral if only one score

            # Factor in average performance
            avg_performance = max(0, mean_score + 5) * 10  # Shift and scale (-5 to +5 -> 0 to 100)

            # Weighted combination: 60% consistency, 40% performance
            return consistency * 0.6 + avg_performance * 0.4

        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Consistency score calculation failed: {e}")
            return 50.0

    def _calculate_balance_score(self, trio: tuple, all_matchups: List[List]) -> float:
        """Calculate diversity of matchup profiles to avoid same weaknesses."""
        try:
            # For each champion, get their worst matchups (big threats)
            champion_weaknesses = []

            for i, matchups in enumerate(all_matchups):
                weaknesses = []
                for enemy, winrate, delta1, delta2, pickrate, games in matchups:
                    if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                        if delta2 < -2.0:  # Significantly negative matchup
                            weaknesses.append(enemy)
                champion_weaknesses.append(set(weaknesses))

            # Calculate overlap in weaknesses (lower overlap = better balance)
            if len(champion_weaknesses) < 2:
                return 50.0

            total_weaknesses = len(
                champion_weaknesses[0] | champion_weaknesses[1] | champion_weaknesses[2]
            )
            shared_weaknesses = len(
                champion_weaknesses[0] & champion_weaknesses[1] & champion_weaknesses[2]
            )

            if total_weaknesses == 0:
                return 100.0

            balance_ratio = 1 - (shared_weaknesses / total_weaknesses)
            return balance_ratio * 100

        except:
            return 50.0  # Neutral score on error

    def _calculate_consistency_score(self, trio: tuple, all_matchups: List[List]) -> float:
        """Calculate how consistently the trio performs across matchups."""
        try:
            all_scores = []

            for matchups in all_matchups:
                for enemy, winrate, delta1, delta2, pickrate, games in matchups:
                    if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                        all_scores.append(delta2)

            if not all_scores:
                return 0.0

            # Lower variance = more consistent
            import statistics

            mean_score = statistics.mean(all_scores)
            if len(all_scores) > 1:
                variance = statistics.variance(all_scores)
                # Convert variance to consistency score (0-100)
                consistency = max(0, 100 - (variance * 5))  # Scale variance appropriately
            else:
                consistency = 50

            # Also factor in average performance
            avg_performance = max(0, mean_score + 5) * 10  # Shift and scale

            return consistency * 0.6 + avg_performance * 0.4

        except:
            return 50.0

    def _calculate_meta_score(self, enemy_coverage: dict) -> float:
        """
        Calculate performance against popular/meta champions.

        Uses actual pickrate data to determine meta relevance:
        - Gets pickrate for each enemy champion from database
        - Calculates weighted average of delta2 scores by pickrate
        - Higher pickrate champions have more influence on the score

        Returns:
            Score 0-100 representing performance vs meta champions
        """
        try:
            if not enemy_coverage:
                return 50.0  # Neutral if no coverage data

            # Get pickrate data for all enemies and calculate weighted score
            weighted_sum = 0.0
            total_weight = 0.0

            for enemy, (delta2, _) in enemy_coverage.items():
                try:
                    # Get pickrate for this enemy champion
                    enemy_matchups = self.db.get_champion_matchups_by_name(enemy)
                    if not enemy_matchups:
                        continue

                    # Calculate average pickrate for this champion
                    # Each matchup has: (enemy_id, winrate, delta1, delta2, pickrate, games)
                    pickrates = [
                        matchup[4]
                        for matchup in enemy_matchups
                        if len(matchup) > 4 and matchup[4] > 0
                    ]

                    if not pickrates:
                        continue

                    avg_pickrate = sum(pickrates) / len(pickrates)

                    # Weight the delta2 score by pickrate
                    # Higher pickrate = more meta relevant = higher weight
                    weight = avg_pickrate
                    weighted_sum += max(0, delta2) * weight
                    total_weight += weight

                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Error processing {enemy} pickrate: {e}")
                    continue

            if total_weight == 0:
                return 50.0  # No valid pickrate data

            # Calculate weighted average
            weighted_avg = weighted_sum / total_weight

            # Scale to 0-100 range
            # delta2 typically ranges from -5 to +5, so we shift and scale
            score = min(100.0, max(0.0, (weighted_avg + 5) * 10))

            return score

        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Meta score calculation failed: {e}")
            return 50.0

    def _calculate_enemy_coverage(self, matchups_list: List[List]) -> Dict[str, tuple]:
        """
        Calculate enemy coverage for a set of champions.

        Args:
            matchups_list: List of matchup lists for each champion

        Returns:
            Dictionary mapping enemy_name -> (best_delta2, champion_handling_it)
        """
        enemy_coverage = {}
        all_enemies = set()

        for i, matchups in enumerate(matchups_list):
            champion_name = f"Champion{i+1}"  # Fallback name, should be passed properly

            for enemy, winrate, delta1, delta2, pickrate, games in matchups:
                if pickrate >= config.MIN_PICKRATE and games >= config.MIN_MATCHUP_GAMES:
                    all_enemies.add(enemy)
                    if enemy not in enemy_coverage or delta2 > enemy_coverage[enemy][0]:
                        enemy_coverage[enemy] = (delta2, champion_name)

        return enemy_coverage

    def _calculate_adaptive_base_weights(self, sample_trios: List[tuple]) -> Dict[str, float]:
        """
        Calculate base weights using variance analysis.

        Metrics with higher variance discriminate better between trios,
        so they receive higher weights in the final scoring.

        Args:
            sample_trios: List of trio tuples to analyze for variance

        Returns:
            Dictionary of normalized base weights
        """
        try:
            if len(sample_trios) < 3:
                # Fallback to equal weights if insufficient data
                return {"coverage": 0.25, "balance": 0.25, "consistency": 0.25, "meta": 0.25}

            # Collect scores for all metrics
            metric_scores = {"coverage": [], "balance": [], "consistency": [], "meta": []}

            if self.verbose:
                print(f"[DEBUG] Calculating adaptive weights from {len(sample_trios)} trios...")

            for trio in sample_trios:
                try:
                    # Get individual matchups for the trio
                    matchups = []
                    for champion in trio:
                        champ_matchups = self.db.get_champion_matchups_by_name(champion)
                        if champ_matchups:
                            matchups.append(champ_matchups)

                    if len(matchups) != 3:
                        continue

                    # Calculate individual metric scores
                    enemy_coverage = self._calculate_enemy_coverage(matchups)

                    # Get all enemies for coverage calculation
                    all_enemies = set()
                    for matchup_list in matchups:
                        for enemy, winrate, delta1, delta2, pickrate, games in matchup_list:
                            if (
                                pickrate >= config.MIN_PICKRATE
                                and games >= config.MIN_MATCHUP_GAMES
                            ):
                                all_enemies.add(enemy)

                    metric_scores["coverage"].append(
                        self._calculate_coverage_score(enemy_coverage, all_enemies)
                    )
                    metric_scores["balance"].append(self._calculate_balance_score(trio, matchups))
                    metric_scores["consistency"].append(
                        self._calculate_consistency_score(trio, matchups)
                    )
                    metric_scores["meta"].append(self._calculate_meta_score(enemy_coverage))

                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Error processing trio {trio}: {e}")
                    continue

            # Calculate variances
            variances = {}
            for metric, scores in metric_scores.items():
                if len(scores) >= 2:
                    # Use numpy for variance calculation if available, otherwise manual
                    try:
                        import numpy as np

                        variances[metric] = float(np.var(scores))
                    except ImportError:
                        mean_score = sum(scores) / len(scores)
                        variance = sum((x - mean_score) ** 2 for x in scores) / len(scores)
                        variances[metric] = variance
                else:
                    variances[metric] = 1.0  # Fallback

            # Normalize variances to weights (higher variance = higher weight)
            total_variance = sum(variances.values())
            if total_variance == 0:
                # All metrics have zero variance - use equal weights
                base_weights = {
                    "coverage": 0.25,
                    "balance": 0.25,
                    "consistency": 0.25,
                    "meta": 0.25,
                }
            else:
                base_weights = {metric: var / total_variance for metric, var in variances.items()}

            if self.verbose:
                print(f"[DEBUG] Variance analysis:")
                for metric, variance in variances.items():
                    print(f"  {metric}: variance={variance:.3f}, weight={base_weights[metric]:.3f}")

            return base_weights

        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Adaptive weight calculation failed: {e}")
            # Fallback to equal weights
            return {"coverage": 0.25, "balance": 0.25, "consistency": 0.25, "meta": 0.25}

    def _get_profile_modifiers(self, profile: str = "balanced") -> Dict[str, float]:
        """
        Get profile-specific modifiers for weight adjustment.

        Args:
            profile: Scoring profile ("safe", "meta", "aggressive", "balanced")

        Returns:
            Dictionary of multipliers for each metric
        """
        profiles = {
            "safe": {
                "consistency": 1.8,  # ++ Fiabilité avant tout
                "balance": 1.2,  # + Diversité pour éviter risques
                "coverage": 0.7,  # - Moins important si on joue safe
                "meta": 0.3,  # -- Peu important, on évite les risques
            },
            "meta": {
                "meta": 2.0,  # ++ Performance vs picks populaires
                "consistency": 1.3,  # + Fiabilité dans le meta actuel
                "coverage": 0.8,  # - Couverture moins critique
                "balance": 0.6,  # -- Diversité moins importante
            },
            "aggressive": {
                "coverage": 1.5,  # + Maximum de coverage pour dominer
                "balance": 1.3,  # + Diversité pour surprendre
                "consistency": 0.8,  # - Moins critique si on cherche à dominer
                "meta": 0.7,  # - Meta moins important
            },
            "balanced": {
                "coverage": 1.0,  # = Garde les poids de variance pure
                "balance": 1.0,
                "consistency": 1.0,
                "meta": 1.0,
            },
        }

        return profiles.get(profile, profiles["balanced"])

    def _calculate_contextual_total_score(
        self, scores: Dict[str, float], profile: str = "balanced"
    ) -> tuple:
        """
        Calculate total score using adaptive weights + profile modifiers.

        Args:
            scores: Dictionary with individual metric scores
            profile: Scoring profile to apply

        Returns:
            Tuple of (total_score, final_weights_used)
        """
        try:
            # 1. Get base weights (calculated once and cached)
            if not hasattr(self, "_cached_base_weights"):
                # Generate sample trios for weight calculation
                sample_trios = self._generate_sample_trios_for_weights()
                self._cached_base_weights = self._calculate_adaptive_base_weights(sample_trios)
                if self.verbose:
                    print(f"[DEBUG] Cached adaptive base weights: {self._cached_base_weights}")

            base_weights = self._cached_base_weights

            # 2. Get profile modifiers
            modifiers = self._get_profile_modifiers(profile)

            # 3. Calculate final weights = base × modifier
            final_weights = {}
            for metric in ["coverage", "balance", "consistency", "meta"]:
                final_weights[metric] = base_weights[metric] * modifiers[metric]

            # 4. Renormalize so sum = 1.0
            total = sum(final_weights.values())
            if total > 0:
                final_weights = {k: v / total for k, v in final_weights.items()}
            else:
                # Fallback
                final_weights = {
                    "coverage": 0.25,
                    "balance": 0.25,
                    "consistency": 0.25,
                    "meta": 0.25,
                }

            # 5. Calculate weighted total score
            total_score = (
                scores["coverage_score"] * final_weights["coverage"]
                + scores["balance_score"] * final_weights["balance"]
                + scores["consistency_score"] * final_weights["consistency"]
                + scores["meta_score"] * final_weights["meta"]
            )

            return total_score, final_weights

        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Contextual scoring failed: {e}")
            # Fallback to simple average
            total_score = sum(scores.values()) / len(scores)
            fallback_weights = {
                "coverage": 0.25,
                "balance": 0.25,
                "consistency": 0.25,
                "meta": 0.25,
            }
            return total_score, fallback_weights

    def _generate_sample_trios_for_weights(self, sample_size: int = 15) -> List[tuple]:
        """
        Generate a sample of trios for adaptive weight calculation.

        Uses a subset of available champions to avoid expensive computation.

        Args:
            sample_size: Number of sample trios to generate

        Returns:
            List of trio tuples
        """
        try:
            from itertools import combinations
            from .constants import (
                TOP_CHAMPIONS,
                JUNGLE_CHAMPIONS,
                MID_CHAMPIONS,
                ADC_CHAMPIONS,
                SUPPORT_CHAMPIONS,
            )

            # Get a balanced sample of champions from different roles
            sample_champions = []

            # Take some champions from each role for diversity
            sample_champions.extend(TOP_CHAMPIONS[:3])
            sample_champions.extend(JUNGLE_CHAMPIONS[:3])
            sample_champions.extend(MID_CHAMPIONS[:3])
            sample_champions.extend(ADC_CHAMPIONS[:2])
            sample_champions.extend(SUPPORT_CHAMPIONS[:2])

            # Filter champions that have data in database
            valid_champions = []
            for champion in sample_champions:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if matchups and len(matchups) > 10:  # Ensure sufficient data
                    valid_champions.append(champion)

            if len(valid_champions) < 3:
                if self.verbose:
                    print(f"[WARNING] Insufficient champions with data for weight calculation")
                return []

            # Generate combinations and take a sample
            all_trios = list(combinations(valid_champions, 3))

            # Take a reasonable sample
            import random

            actual_sample_size = min(sample_size, len(all_trios))
            sample_trios = random.sample(all_trios, actual_sample_size)

            if self.verbose:
                print(
                    f"[DEBUG] Generated {len(sample_trios)} sample trios from {len(valid_champions)} champions"
                )

            return sample_trios

        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Sample trio generation failed: {e}")
            return []

    def set_scoring_profile(self, profile: str):
        """
        Set the scoring profile for trio evaluation.

        Args:
            profile: One of "safe", "meta", "aggressive", "balanced"
        """
        valid_profiles = ["safe", "meta", "aggressive", "balanced"]
        if profile in valid_profiles:
            self.scoring_profile = profile
            # Clear cached weights to recalculate with new profile
            if hasattr(self, "_cached_base_weights"):
                delattr(self, "_cached_base_weights")
            if self.verbose:
                print(f"[INFO] Scoring profile set to: {profile}")
        else:
            if self.verbose:
                print(f"[WARNING] Invalid profile '{profile}'. Valid options: {valid_profiles}")
