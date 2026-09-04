"""Tactical/coverage analysis printed after a classic trio search.

Extracted from src/assistant.py (SPEC-07 E10, lot 4) : déplacement verbatim,
aucun changement de comportement.

FROZEN BUG (analyze(), ~"WEAK AGAINST" section): ``worst_matchups = [m for m
in valid_matchups[-10:] if m.winrate < 0]`` iterates over ``valid_matchups``,
which holds ``(enemy_name, delta2)`` tuples, not ``Matchup`` objects.
``m.winrate`` therefore always raises ``AttributeError``, swallowed by the
enclosing ``except Exception`` — the "WEAK AGAINST" section (and the
"NEUTRAL MATCHUPS" line after it) never prints, for any champion, and an
"Error analyzing <champion>" line prints instead. Preserved as-is (pinned by
tests/test_assistant_trio_classic.py); fixing it is a separate decision.
"""

from typing import List, Optional

from ..db import Database
from ..utils.display import safe_print


class TrioTacticsReporter:
    """Print tactical and coverage analysis for a resolved trio."""

    def __init__(self, db: Database, verbose: bool = False) -> None:
        self.db = db
        self.verbose = verbose

    def analyze(self, trio: tuple, lane: Optional[str] = None) -> None:
        """
        Provide tactical analysis on how to use the optimal trio.

        Args:
            trio: (champion1, champion2, champion3) - the optimal trio
            lane: Lane optionnelle transmise aux requêtes matchups internes.
                  None = agrégation toutes lanes, comportement inchangé.
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
                matchups = self.db.get_champion_matchups_by_name(champion, lane=lane)
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
        self._analyze_coverage(trio_champions, lane=lane)

    def _analyze_coverage(self, trio: List[str], lane: Optional[str] = None) -> None:
        """Analyze what the trio covers and potential gaps.

        Args:
            lane: Lane optionnelle transmise aux requêtes matchups internes.
                  None = agrégation toutes lanes, comportement inchangé.
        """

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
                    matchups = self.db.get_champion_matchups_by_name(our_champion, lane=lane)

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
