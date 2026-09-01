"""Global champion score calculation (persisted to champion_scores table).

Extracted from src/assistant.py (SPEC-07 E10, lot 1) : déplacement verbatim,
aucun changement de comportement.
"""

import statistics
from typing import List

from ..config_constants import analysis_config
from ..db import Database
from .scoring import ChampionScorer, confidence


class GlobalScoreCalculator:
    """Compute and persist per-champion scores from raw matchup data."""

    def __init__(self, db: Database, scorer: ChampionScorer, verbose: bool = False) -> None:
        self.db = db
        self.scorer = scorer
        self.verbose = verbose

    def calculate_all(self) -> int:
        """
        Calculate and save scores for all champions in the database.

        This function computes raw metrics (avg_delta2, variance, coverage,
        peak_impact, volatility, target_ratio) for all champions and stores
        them in the champion_scores table.

        Should be called after parsing/updating matchup data.

        Returns:
            Number of champions scored and saved
        """
        print("[INFO] Calculating global champion scores...")

        champions_scored = 0
        all_champions: List[str] = list(self.db.get_all_champion_names().values())

        for champion in all_champions:
            try:
                matchups = self.db.get_champion_matchups_by_name(champion)
                if not matchups:
                    if self.verbose:
                        print(f"  [SKIP] {champion}: No matchups found")
                    continue

                valid_matchups = self.scorer.filter_valid_matchups(matchups)
                if not valid_matchups:
                    if self.verbose:
                        print(f"  [SKIP] {champion}: No valid matchups after filtering")
                    continue

                # Calculate raw metrics
                avg_delta2 = self.scorer.avg_delta2(matchups)

                delta2_values = [m.delta2 for m in valid_matchups]
                variance = statistics.variance(delta2_values) if len(delta2_values) > 1 else 0.0

                # Coverage (blind pick metric)
                # Poids = pickrate * confidence(games) (SPEC-05 B6) : un matchup
                # à peine au-dessus du seuil MIN_MATCHUP_GAMES ne doit pas peser
                # autant qu'un matchup mesuré sur des dizaines de milliers de parties.
                decent_weight = sum(
                    m.pickrate * confidence(m.games)
                    for m in matchups
                    if m.delta2 > analysis_config.DECENT_MATCHUP_THRESHOLD
                )
                total_weight = sum(m.pickrate * confidence(m.games) for m in matchups)
                coverage = decent_weight / total_weight if total_weight > 0 else 0.0

                # Peak impact (counter pick metric)
                excellent_impact = sum(
                    m.delta2 * m.pickrate * confidence(m.games)
                    for m in matchups
                    if m.delta2 > analysis_config.EXCELLENT_MATCHUP_THRESHOLD
                )
                good_impact = sum(
                    m.delta2 * m.pickrate * confidence(m.games)
                    for m in matchups
                    if analysis_config.GOOD_MATCHUP_THRESHOLD
                    < m.delta2
                    <= analysis_config.EXCELLENT_MATCHUP_THRESHOLD
                )
                peak_impact = excellent_impact + good_impact * 0.5

                # Volatility (counter pick metric) - same as variance
                volatility = variance

                # Target ratio (counter pick metric)
                viable_weight = sum(
                    m.pickrate * confidence(m.games)
                    for m in matchups
                    if m.delta2 > analysis_config.GOOD_MATCHUP_THRESHOLD
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
