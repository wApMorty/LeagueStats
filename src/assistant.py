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
            print("Searching for optimal duos...")
            print()
            return

        medals = ["1.", "2.", "3."]
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
        print(f"\nEvaluating {total_combinations} possible duos...\n")

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
                                if matchup.enemy_name.lower() == enemy_champion.lower():
                                    if matchup.delta2 > best_counter_score:
                                        best_counter_score = matchup.delta2
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
            f"[OK] Evaluation complete: {duos_tested}/{total_combinations} tested, {evaluated_combinations} viable"
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
            safe_print(f"\nTOP DUO RANKINGS:")
            safe_print("─" * 80)
            display_count = min(5, len(duo_rankings))  # Show top 5

            for i, info in enumerate(duo_rankings[:display_count]):
                duo = info["duo"]
                score = info["total_score"]
                coverage = info["coverage"]
                avg_score = info["avg_score"]

                rank_symbol = "1." if i == 0 else "2." if i == 1 else "3." if i == 2 else f"{i+1}."

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
            safe_print(f"\n[ERREUR] Only {len(viable_champions)} champions have sufficient data.")
            print("Need at least 3 champions with data to form a trio.")
            print("\nChampions with insufficient data:")
            for champ, data in validation_report.items():
                if not data["has_data"]:
                    print(f"  - {champ}: {data['matchups']} matchups, {data['total_games']} games")
            raise ValueError(f"Insufficient data: only {len(viable_champions)}/3 champions viable")

        if len(viable_champions) < len(champion_pool):
            safe_print(
                f"\n[ALERTE] Using {len(viable_champions)} viable champions out of {len(champion_pool)} requested"
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
        safe_print(f"\nBLIND PICK RANKINGS:")
        safe_print("─" * 60)
        display_count = min(len(viable_champions), 5)  # Show all viable or max 5

        for i, candidate in enumerate(blind_candidates[:display_count]):
            champ = candidate["champion"]
            score = candidate["avg_delta2"]
            games = candidate["total_games"]
            matchups = candidate["matchups"]

            rank_symbol = "1." if i == 0 else "2." if i == 1 else "3." if i == 2 else f"{i+1}."

            safe_print(f"{rank_symbol} {champ}")
            print(f"    Avg Delta2: {score:.2f} | Games: {games:,} | Matchups: {matchups}")

        best_blind = blind_candidates[0]["champion"]
        best_blind_score = blind_candidates[0]["avg_delta2"]

        safe_print(f"\n[OK] Selected blind pick: {best_blind} (avg delta2: {best_blind_score:.2f})")

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
            f"\n[OK] Optimal trio: {best_blind} (blind) + {best_duo[0]} + {best_duo[1]} (counterpicks)"
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
            safe_print(f"\n[ERREUR] Fixed champion '{fixed_champion}' has insufficient data")
            print(f"  Matchups: {matchups}, Games: {games}")
            raise ValueError(f"Fixed champion '{fixed_champion}' has insufficient data in database")

        safe_print(
            f"[OK] Fixed champion validated: {matchups} matchups, {games} total games, {delta2:.2f} avg delta2"
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
            safe_print(f"\n[ERREUR] Only {len(viable_companions)} companions have sufficient data.")  # fmt: skip
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
                f"\n[ALERTE] Using {len(viable_companions)} viable companions out of {len(available_pool)} available"
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
        safe_print(f"\n[OK] Optimal trio: {fixed_champion} + {best_duo[0]} + {best_duo[1]}")

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

        safe_print(f"\nTACTICAL ANALYSIS:")
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
                    (m.enemy_name, m.delta2) for m in matchups if m.games >= 200
                ]  # enemy, delta2, min 200 games
                valid_matchups.sort(key=lambda x: x[1], reverse=True)  # Sort by delta2

                if not valid_matchups:
                    continue

                safe_print(f"\n{champion} ({role}):")

                # Best matchups (top 5)
                best_matchups = valid_matchups[:5]
                safe_print(f"  STRONG AGAINST:")
                for enemy, delta2 in best_matchups:
                    print(f"    - {enemy} ({delta2:+.2f} delta2)")

                # Worst matchups (bottom 5, but only show negatives)
                worst_matchups = [
                    m for m in valid_matchups[-10:] if m.winrate < 0
                ]  # Only negative deltas
                worst_matchups = sorted(worst_matchups, key=lambda x: x[1])[:5]  # Worst 5

                if worst_matchups:
                    safe_print(f"  WEAK AGAINST:")
                    for enemy, delta2 in worst_matchups:
                        print(f"    - {enemy} ({delta2:+.2f} delta2)")

                # Neutral matchups count
                neutral_count = sum(1 for _, delta2 in valid_matchups if -1 <= delta2 <= 1)
                safe_print(f"  NEUTRAL MATCHUPS: {neutral_count} champions")

            except Exception as e:
                print(f"  Error analyzing {champion}: {e}")
                continue

        # Coverage analysis
        self._analyze_trio_coverage(trio_champions)

    def _analyze_trio_coverage(self, trio: List[str]) -> None:
        """Analyze what the trio covers and potential gaps."""

        safe_print(f"\nCOVERAGE ANALYSIS:")
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
                        if matchup.enemy_name.lower() == enemy_champion.lower():
                            if matchup.delta2 > best_delta2:  # delta2 better
                                best_delta2 = matchup.delta2
                                best_counter = our_champion
                            break
                except Exception as e:
                    # Log database errors - these indicate data quality issues
                    if self.verbose:
                        print(
                            f"[ERROR] Failed to get matchup for {our_champion} vs {enemy_champion}: {e}"
                        )
                    continue

            if best_counter:
                coverage_map[enemy_champion] = (best_counter, best_delta2)
            else:
                uncovered_enemies.append(enemy_champion)

        # Statistics
        total_enemies = len(all_champions)
        covered_count = len(coverage_map)
        coverage_percent = (covered_count / total_enemies) * 100

        safe_print(f"COVERAGE STATS:")
        print(f"  - Covered: {covered_count}/{total_enemies} champions ({coverage_percent:.1f}%)")

        # Categorize coverage quality
        excellent = [(e, c, d) for e, (c, d) in coverage_map.items() if d >= 2.0]
        good = [(e, c, d) for e, (c, d) in coverage_map.items() if 1.0 <= d < 2.0]
        decent = [(e, c, d) for e, (c, d) in coverage_map.items() if 0 <= d < 1.0]
        struggling = [(e, c, d) for e, (c, d) in coverage_map.items() if d < 0]

        if excellent:
            safe_print(
                f"  EXCELLENT counters: {len(excellent)} ({len(excellent)/covered_count*100:.1f}%)"
            )
        if good:
            safe_print(f"  GOOD counters: {len(good)} ({len(good)/covered_count*100:.1f}%)")
        if decent:
            safe_print(f"  DECENT counters: {len(decent)} ({len(decent)/covered_count*100:.1f}%)")  # fmt: skip
        if struggling:
            safe_print(
                f"  STRUGGLING against: {len(struggling)} ({len(struggling)/covered_count*100:.1f}%)"
            )

        # Show problematic matchups
        if struggling:
            safe_print(f"\nDIFFICULT MATCHUPS:")
            worst_struggling = sorted(struggling, key=lambda x: x[2])[:3]  # Worst 3
            for enemy, counter, delta2 in worst_struggling:
                print(f"    - {enemy}: Best answer is {counter} ({delta2:+.2f} delta2)")

        if uncovered_enemies:
            safe_print(f"\n[ALERTE] UNCOVERED CHAMPIONS ({len(uncovered_enemies)}):")
            if len(uncovered_enemies) <= 5:
                for enemy in uncovered_enemies:
                    print(f"    - {enemy}")
            else:
                for enemy in uncovered_enemies[:3]:
                    print(f"    - {enemy}")
                print(f"    ... and {len(uncovered_enemies)-3} more")

        # Draft recommendations
        safe_print(f"\nDRAFT RECOMMENDATIONS:")
        if coverage_percent >= 85:
            safe_print("  Excellent pool! Very few gaps.")
        elif coverage_percent >= 70:
            safe_print("  Good pool with minor gaps.")
        elif coverage_percent >= 50:
            safe_print("  Decent pool but consider expanding.")
        else:
            safe_print("  Pool has significant gaps - consider more champions.")

        if len(excellent) > len(struggling):
            safe_print("  Pool favors aggressive counterpicking.")
        else:
            safe_print("  Pool requires careful champion selection.")

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
