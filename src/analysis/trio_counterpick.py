"""Classic (blind-pick + counterpick-duo) trio/duo search.

Extracted from src/assistant.py (SPEC-07 E10, lot 4) : déplacement verbatim,
aucun changement de comportement. Distinct de trio_holistic.py, qui évalue
les trios comme des unités plutôt que blind pick + duo de contre-picks.
"""

from typing import Callable, List, Optional, Tuple

from ..constants import CHAMPION_POOL
from ..db import Database
from ..utils.display import safe_print
from .trio_tactics import TrioTacticsReporter


class CounterpickTrioFinder:
    """Find a blind pick + best counterpick duo from a champion pool."""

    def __init__(self, db: Database, tactics: TrioTacticsReporter, verbose: bool = False) -> None:
        self.db = db
        self.tactics = tactics
        self.verbose = verbose

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
        self,
        remaining_pool: List[str],
        blind_champion: str,
        show_ranking: bool = False,
        lane: Optional[str] = None,
    ) -> tuple:
        """Find the best duo of counterpicks to maximize coverage against all champions.

        Args:
            lane: Lane optionnelle transmise aux requêtes matchups internes.
                  None = agrégation toutes lanes, comportement inchangé.
        """
        from itertools import combinations

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
                            matchups = self.db.get_champion_matchups_by_name(
                                our_champion, lane=lane
                            )
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

    def optimal_trio_from_pool(
        self,
        champion_pool: List[str],
        validate_pool: Callable[[List[str]], Tuple[List[str], dict]],
        lane: Optional[str] = None,
    ) -> tuple:
        """
        Find optimal 3-champion composition from a given pool.

        Algorithm:
        1. Validate champion pool data availability
        2. Find champion with best average delta2 as blind pick
        3. From remaining champions, find duo that maximizes counterpick coverage

        Args:
            champion_pool: List of champion names to choose from
            lane: Lane optionnelle transmise aux requêtes matchups internes
                  (SPEC-04, pool_manager.pool_role_to_lane). None = agrégation
                  toutes lanes, comportement inchangé.

        Returns:
            Tuple of (blind_pick, counterpick1, counterpick2, total_score)

        Raises:
            ValueError: If insufficient champions with data available
        """
        if len(champion_pool) < 3:
            raise ValueError("Champion pool must contain at least 3 champions")

        print(f"Analyzing optimal trio from pool: {champion_pool}")

        # Step 0: Validate champion data availability
        viable_champions, validation_report = validate_pool(champion_pool)

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
                remaining_pool, best_blind, show_ranking=True, lane=lane
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
        self.tactics.analyze(result_trio, lane=lane)

        return result_trio

    def optimal_duo_for_champion(
        self,
        fixed_champion: str,
        champion_pool: Optional[List[str]],
        validate_pool: Callable[[List[str]], Tuple[List[str], dict]],
        validate_champion: Callable[[str], Tuple[bool, int, int, float]],
        lane: Optional[str] = None,
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
            lane: Lane optionnelle transmise aux requêtes matchups internes.
                  None = agrégation toutes lanes, comportement inchangé.

        Returns:
            Tuple of (fixed_champion, companion1, companion2, total_score)

        Raises:
            ValueError: If fixed champion or insufficient companions have data
        """
        if champion_pool is None:
            champion_pool = CHAMPION_POOL.copy()

        print(f"Finding optimal duo to pair with: {fixed_champion}")

        # Step 0: Validate fixed champion has data
        has_data, matchups, games, delta2 = validate_champion(fixed_champion)

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
        viable_companions, validation_report = validate_pool(available_pool)

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
                viable_companions, fixed_champion, show_ranking=True, lane=lane
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
        self.tactics.analyze(result_trio, lane=lane)

        return result_trio
