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

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

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
        from .constants import CHAMPIONS_LIST
        from .config import tierlist_config
        import statistics

        print("[INFO] Calculating global champion scores...")

        champions_scored = 0

        for champion in CHAMPIONS_LIST:
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
                decent_weight = sum(m[4] for m in matchups if m[3] > tierlist_config.DECENT_MATCHUP_THRESHOLD)
                total_weight = sum(m[4] for m in matchups)
                coverage = decent_weight / total_weight if total_weight > 0 else 0.0

                # Peak impact (counter pick metric)
                excellent_impact = sum(m[3] * m[4] for m in matchups
                                      if m[3] > tierlist_config.EXCELLENT_MATCHUP_THRESHOLD)
                good_impact = sum(m[3] * m[4] for m in matchups
                                  if tierlist_config.GOOD_MATCHUP_THRESHOLD < m[3] <= tierlist_config.EXCELLENT_MATCHUP_THRESHOLD)
                peak_impact = excellent_impact + good_impact * 0.5

                # Volatility (counter pick metric) - same as variance
                volatility = variance

                # Target ratio (counter pick metric)
                viable_weight = sum(m[4] for m in matchups if m[3] > tierlist_config.GOOD_MATCHUP_THRESHOLD)
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
                    target_ratio=target_ratio
                )

                champions_scored += 1
                if self.verbose:
                    print(f"  ✓ {champion}: avg_delta2={avg_delta2:.3f}, variance={variance:.3f}, coverage={coverage:.3f}")

            except Exception as e:
                print(f"  [ERROR] {champion}: {e}")
                continue

        print(f"[SUCCESS] Scored {champions_scored}/{len(CHAMPIONS_LIST)} champions")
        return champions_scored

    # ==================== Optimal Trio Analysis ====================
    # These methods find optimal champion compositions for draft phases

    def _find_optimal_counterpick_duo(self, remaining_pool: List[str], blind_champion: str, show_ranking: bool = False) -> tuple:
        """Find the best duo of counterpicks to maximize coverage against all champions."""
        from itertools import combinations
        
        if len(remaining_pool) < 2:
            raise ValueError(f"Need at least 2 champions in pool, got {len(remaining_pool)}")
        
        duo_rankings = []  # Store all viable duos with their scores
        evaluated_combinations = 0
        
        total_combinations = len(list(combinations(remaining_pool, 2)))
        print(f"Evaluating {total_combinations} possible duos...")
        
        # Try all possible pairs from remaining pool
        for duo in combinations(remaining_pool, 2):
            try:
                total_score = 0
                trio = [blind_champion] + list(duo)
                valid_matchups_found = 0
                
                # For each enemy champion, find the best counter from our trio
                for enemy_champion in CHAMPIONS_LIST:
                    best_counter_score = -float('inf')
                    
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
                    if best_counter_score != -float('inf'):
                        total_score += best_counter_score
                        valid_matchups_found += 1
                
                # Calculate coverage metrics
                coverage_ratio = valid_matchups_found / len(CHAMPIONS_LIST)
                avg_score_per_matchup = total_score / valid_matchups_found if valid_matchups_found > 0 else 0
                
                # Only consider this duo if it has reasonable coverage
                if coverage_ratio < 0.10:  # Less than 10% coverage
                    continue
                
                evaluated_combinations += 1
                
                # Store duo info for ranking
                duo_rankings.append({
                    'duo': duo,
                    'total_score': total_score,
                    'coverage': coverage_ratio,
                    'avg_score': avg_score_per_matchup,
                    'matchups_covered': valid_matchups_found
                })
                    
            except Exception as e:
                continue  # Skip silently for cleaner output
        
        if evaluated_combinations == 0:
            raise ValueError("No valid duo combinations could be evaluated")
        
        # Sort by total score (descending)
        duo_rankings.sort(key=lambda x: x['total_score'], reverse=True)
        
        if not duo_rankings:
            raise ValueError("No viable duo found after evaluation")
        
        # Display rankings if requested
        if show_ranking and len(duo_rankings) > 1:
            safe_print(f"\n📊 TOP DUO RANKINGS:")
            safe_print("─" * 80)
            display_count = min(5, len(duo_rankings))  # Show top 5
            
            for i, info in enumerate(duo_rankings[:display_count]):
                duo = info['duo']
                score = info['total_score']
                coverage = info['coverage']
                avg_score = info['avg_score']
                
                rank_symbol = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
                
                safe_print(f"{rank_symbol} {duo[0]} + {duo[1]}")
                print(f"    Total Score: {score:.1f} | Coverage: {coverage:.1%} | Avg/Match: {avg_score:.2f}")
        
        print(f"Evaluated {evaluated_combinations} valid combinations")
        
        best_info = duo_rankings[0]
        return best_info['duo'], best_info['total_score']

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
                if not data['has_data']:
                    print(f"  - {champ}: {data['matchups']} matchups, {data['total_games']} games")
            raise ValueError(f"Insufficient data: only {len(viable_champions)}/3 champions viable")
        
        if len(viable_champions) < len(champion_pool):
            safe_print(f"\n⚠️  WARNING: Using {len(viable_champions)} viable champions out of {len(champion_pool)} requested")
        
        # Step 1: Find best blind pick (highest average delta2) from viable champions
        blind_candidates = []
        
        print(f"\nAnalyzing blind pick candidates from viable champions...")
        for champion in viable_champions:
            score = validation_report[champion]['avg_delta2']
            games = validation_report[champion]['total_games']
            matchups = validation_report[champion]['matchups']
            
            blind_candidates.append({
                'champion': champion,
                'avg_delta2': score,
                'total_games': games,
                'matchups': matchups
            })
        
        # Sort by avg_delta2 (descending)
        blind_candidates.sort(key=lambda x: x['avg_delta2'], reverse=True)
        
        if not blind_candidates:
            raise ValueError("No viable blind pick champion found")
        
        # Display blind pick rankings
        safe_print(f"\n🎯 BLIND PICK RANKINGS:")
        safe_print("─" * 60)
        display_count = min(len(viable_champions), 5)  # Show all viable or max 5
        
        for i, candidate in enumerate(blind_candidates[:display_count]):
            champ = candidate['champion']
            score = candidate['avg_delta2']
            games = candidate['total_games']
            matchups = candidate['matchups']
            
            rank_symbol = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else f"{i+1}."
            
            safe_print(f"{rank_symbol} {champ}")
            print(f"    Avg Delta2: {score:.2f} | Games: {games:,} | Matchups: {matchups}")
        
        best_blind = blind_candidates[0]['champion']
        best_blind_score = blind_candidates[0]['avg_delta2']
        
        safe_print(f"\n✅ Selected blind pick: {best_blind} (avg delta2: {best_blind_score:.2f})")
        
        # Step 2: Find best counterpick duo from remaining viable champions
        remaining_pool = [champ for champ in viable_champions if champ != best_blind]
        
        if len(remaining_pool) < 2:
            raise ValueError(f"Insufficient remaining champions for duo: only {len(remaining_pool)} available")
        
        try:
            best_duo, duo_score = self._find_optimal_counterpick_duo(remaining_pool, best_blind, show_ranking=True)
        except Exception as e:
            print(f"Error finding optimal duo: {e}")
            raise ValueError(f"Failed to find optimal counterpick duo: {e}")
        
        if best_duo is None:
            raise ValueError("No viable counterpick duo found")
        
        total_score = best_blind_score + duo_score
        
        print(f"Best counterpick duo: {best_duo}")
        print(f"Total coverage score: {total_score:.2f}")
        safe_print(f"\n✅ Optimal trio: {best_blind} (blind) + {best_duo[0]} + {best_duo[1]} (counterpicks)")
        
        # Add tactical analysis
        result_trio = (best_blind, best_duo[0], best_duo[1], total_score)
        self._analyze_trio_tactics(result_trio)
        
        return result_trio

    def optimal_duo_for_champion(self, fixed_champion: str, champion_pool: List[str] = None) -> tuple:
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
        
        safe_print(f"✅ Fixed champion validated: {matchups} matchups, {games} total games, {delta2:.2f} avg delta2")
        
        # Remove the fixed champion from the pool if it's there
        available_pool = [champ for champ in champion_pool if champ.lower() != fixed_champion.lower()]
        
        if len(available_pool) < 2:
            raise ValueError("Champion pool must contain at least 2 champions besides the fixed one")
        
        # Step 1: Validate available companion pool
        viable_companions, validation_report = self._validate_champion_pool(available_pool)
        
        if len(viable_companions) < 2:
            safe_print(f"\n❌ ERROR: Only {len(viable_companions)} companions have sufficient data.")
            print("Need at least 2 viable companions to form a duo.")
            print("\nCompanions with insufficient data:")
            for champ, data in validation_report.items():
                if not data['has_data']:
                    print(f"  - {champ}: {data['matchups']} matchups, {data['total_games']} games")
            raise ValueError(f"Insufficient companion data: only {len(viable_companions)}/2 champions viable")
        
        if len(viable_companions) < len(available_pool):
            safe_print(f"\n⚠️  WARNING: Using {len(viable_companions)} viable companions out of {len(available_pool)} available")
        
        # Step 2: Find best duo from viable companions
        try:
            best_duo, duo_score = self._find_optimal_counterpick_duo(viable_companions, fixed_champion, show_ranking=True)
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
                valid_matchups = [(m[0], m[3]) for m in matchups if m[5] >= 200]  # enemy, delta2, min 200 games
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
                worst_matchups = [m for m in valid_matchups[-10:] if m[1] < 0]  # Only negative deltas
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
        
        coverage_map = {}  # enemy -> best_counter_info
        uncovered_enemies = []
        
        for enemy_champion in CHAMPIONS_LIST:
            best_counter = None
            best_delta2 = -float('inf')
            
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
        total_enemies = len(CHAMPIONS_LIST)
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
            safe_print(f"  🟢 EXCELLENT counters: {len(excellent)} ({len(excellent)/covered_count*100:.1f}%)")
        if good:
            safe_print(f"  🟡 GOOD counters: {len(good)} ({len(good)/covered_count*100:.1f}%)")
        if decent:
            safe_print(f"  🟠 DECENT counters: {len(decent)} ({len(decent)/covered_count*100:.1f}%)")
        if struggling:
            safe_print(f"  🔴 STRUGGLING against: {len(struggling)} ({len(struggling)/covered_count*100:.1f}%)")

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

