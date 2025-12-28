"""Tier list generation for champion pools."""

from typing import List

from ..db import Database
from ..constants import TOP_LIST, JUNGLE_LIST, MID_LIST, ADC_LIST, SUPPORT_LIST
from ..config_constants import analysis_config
from .scoring import ChampionScorer


class TierListGenerator:
    """Generates tier lists based on champion performance metrics."""

    def __init__(self, db: Database, scorer: ChampionScorer, min_games: int = None):
        """
        Initialize TierListGenerator.

        Args:
            db: Database instance
            scorer: ChampionScorer instance for calculating metrics
            min_games: Minimum games threshold (defaults to config value)
        """
        self.db = db
        self.scorer = scorer
        self.min_games = min_games or analysis_config.MIN_GAMES_THRESHOLD

    def generate_by_delta1(self, champion_list: List[str]) -> List[tuple]:
        """
        Generate tier list ranked by average delta1 (gold difference at 15min).

        Args:
            champion_list: List of champion names to rank

        Returns:
            List of (champion, delta1_score) tuples, sorted by score descending
        """
        scores = []
        for champion in champion_list:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if sum(m[5] for m in matchups) < self.min_games:
                continue  # Skip this champion but continue processing others
            score = self.scorer.avg_delta1(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def generate_by_delta2(self, champion_list: List[str]) -> List[tuple]:
        """
        Generate tier list ranked by average delta2 (gold difference at end).

        Args:
            champion_list: List of champion names to rank

        Returns:
            List of (champion, delta2_score) tuples, sorted by score descending
        """
        scores = []
        for champion in champion_list:
            matchups = self.db.get_champion_matchups_by_name(champion)
            if sum(m[5] for m in matchups) < self.min_games:
                continue  # Skip this champion but continue processing others
            score = self.scorer.avg_delta2(matchups)
            scores.append((champion, score))
            scores.sort(key=lambda x: -x[1])
        return scores

    def generate_for_lane(self, lane: str) -> List[tuple]:
        """
        Generate tier list for a specific lane using delta2.

        Args:
            lane: Lane name ('top', 'jungle', 'mid', 'adc', 'support')

        Returns:
            List of (champion, delta2_score) tuples, sorted by score descending
        """
        champion_list = ""
        if lane == "top":
            champion_list = TOP_LIST
        elif lane == "jungle":
            champion_list = JUNGLE_LIST
        elif lane == "mid":
            champion_list = MID_LIST
        elif lane == "adc":
            champion_list = ADC_LIST
        elif lane == "support":
            champion_list = SUPPORT_LIST
        else:
            print("Invalid lane specified.")
            return []
        return self.generate_by_delta2(champion_list)

    def generate_tier_list(
        self, champion_pool: List[str], analysis_type: str = "blind_pick", verbose: bool = False
    ) -> List[dict]:
        """
        Generate a tier list for a champion pool using pre-computed global scores.

        Uses global normalization: normalizes metrics based on ALL champions in the
        database, making scores comparable across different pools.

        Args:
            champion_pool: List of champion names to include in tier list
            analysis_type: "blind_pick" or "counter_pick"
            verbose: Enable verbose logging

        Returns:
            List of dicts sorted by score (descending), each containing:
            {
                'champion': str,
                'tier': str ('S', 'A', 'B', or 'C'),
                'score': float (0-100),
                'metrics': dict (detailed metrics)
            }
        """
        from ..config import tierlist_config
        import statistics

        # Check if champion_scores table exists and has data
        if not self.db.champion_scores_table_exists():
            print("[WARNING] Champion scores not found in database.")
            print("[INFO] Please run 'Parse Match Statistics' to generate scores first.")
            return []

        # Step 1: Collect all scores from database for global normalization
        all_scores_data = self.db.get_all_champion_scores()

        if not all_scores_data:
            print("[ERROR] No champion scores found in database")
            return []

        # Extract global ranges for normalization
        all_metrics = {
            "avg_delta2": [],
            "variance": [],
            "coverage": [],
            "peak_impact": [],
            "volatility": [],
            "target_ratio": [],
        }

        for row in all_scores_data:
            # row = (name, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)
            all_metrics["avg_delta2"].append(row[1])
            all_metrics["variance"].append(row[2])
            all_metrics["coverage"].append(row[3])
            all_metrics["peak_impact"].append(row[4])
            all_metrics["volatility"].append(row[5])
            all_metrics["target_ratio"].append(row[6])

        # Calculate global ranges
        min_delta2_global = min(all_metrics["avg_delta2"])
        max_delta2_global = max(all_metrics["avg_delta2"])
        min_variance_global = min(all_metrics["variance"])
        max_variance_global = max(all_metrics["variance"])
        min_coverage_global = min(all_metrics["coverage"])
        max_coverage_global = max(all_metrics["coverage"])
        min_peak_impact_global = min(all_metrics["peak_impact"])
        max_peak_impact_global = max(all_metrics["peak_impact"])
        min_target_ratio_global = min(all_metrics["target_ratio"])
        max_target_ratio_global = max(all_metrics["target_ratio"])

        # Avoid division by zero
        if max_delta2_global == min_delta2_global:
            min_delta2_global -= 0.05
            max_delta2_global += 0.05
        if max_variance_global == min_variance_global:
            min_variance_global -= 0.05
            max_variance_global += 0.05
        if max_coverage_global == min_coverage_global:
            min_coverage_global -= 0.05
            max_coverage_global += 0.05
        if max_peak_impact_global == min_peak_impact_global:
            min_peak_impact_global -= 0.5
            max_peak_impact_global += 0.5
        if max_target_ratio_global == min_target_ratio_global:
            min_target_ratio_global -= 0.05
            max_target_ratio_global += 0.05

        if verbose:
            print(f"[INFO] Global normalization ranges:")
            print(f"  Delta2: {min_delta2_global:.2f} to {max_delta2_global:.2f}")
            print(f"  Variance: {min_variance_global:.2f} to {max_variance_global:.2f}")
            if analysis_type == "blind_pick":
                print(f"  Coverage: {min_coverage_global:.3f} to {max_coverage_global:.3f}")
            elif analysis_type == "counter_pick":
                print(
                    f"  Peak Impact: {min_peak_impact_global:.3f} to {max_peak_impact_global:.3f}"
                )
                print(
                    f"  Target Ratio: {min_target_ratio_global:.3f} to {max_target_ratio_global:.3f}"
                )

        # Step 2: Get scores from database and calculate normalized scores
        results = []

        for champion in champion_pool:
            # Get pre-computed scores from database
            scores = self.db.get_champion_scores_by_name(champion)

            if scores is None:
                if verbose:
                    print(f"  [SKIP] {champion}: No scores in database")
                continue

            # Calculate normalized score based on analysis type
            if analysis_type == "blind_pick":
                # Normalize components
                avg_perf_norm = (scores["avg_delta2"] - min_delta2_global) / (
                    max_delta2_global - min_delta2_global
                )
                avg_perf_norm = max(0.0, min(1.0, avg_perf_norm))

                variance_norm = (scores["variance"] - min_variance_global) / (
                    max_variance_global - min_variance_global
                )
                variance_norm = max(0.0, min(1.0, variance_norm))
                stability = 1.0 - variance_norm  # Invert: low variance = high stability

                coverage_norm = (scores["coverage"] - min_coverage_global) / (
                    max_coverage_global - min_coverage_global
                )
                coverage_norm = max(0.0, min(1.0, coverage_norm))

                # Calculate final score
                normalized_score = (
                    avg_perf_norm * tierlist_config.BLIND_AVG_WEIGHT
                    + stability * tierlist_config.BLIND_STABILITY_WEIGHT
                    + coverage_norm * tierlist_config.BLIND_COVERAGE_WEIGHT
                )
                final_score = normalized_score * 100

                # Build metrics dict for display
                metrics = {
                    "final_score": final_score,
                    "avg_performance_norm": avg_perf_norm,
                    "avg_delta2_raw": scores["avg_delta2"],
                    "stability": stability,
                    "variance": scores["variance"],
                    "coverage_norm": coverage_norm,
                    "coverage_raw": scores["coverage"],
                }

            elif analysis_type == "counter_pick":
                # Normalize components
                peak_impact_norm = (scores["peak_impact"] - min_peak_impact_global) / (
                    max_peak_impact_global - min_peak_impact_global
                )
                peak_impact_norm = max(0.0, min(1.0, peak_impact_norm))

                volatility_norm = (scores["volatility"] - min_variance_global) / (
                    max_variance_global - min_variance_global
                )
                volatility_norm = max(0.0, min(1.0, volatility_norm))

                target_ratio_norm = (scores["target_ratio"] - min_target_ratio_global) / (
                    max_target_ratio_global - min_target_ratio_global
                )
                target_ratio_norm = max(0.0, min(1.0, target_ratio_norm))

                # Calculate final score
                normalized_score = (
                    peak_impact_norm * tierlist_config.COUNTER_PEAK_WEIGHT
                    + volatility_norm * tierlist_config.COUNTER_VOLATILITY_WEIGHT
                    + target_ratio_norm * tierlist_config.COUNTER_TARGETS_WEIGHT
                )
                final_score = normalized_score * 100

                # Build metrics dict for display
                metrics = {
                    "final_score": final_score,
                    "peak_impact_norm": peak_impact_norm,
                    "peak_impact_raw": scores["peak_impact"],
                    "volatility_norm": volatility_norm,
                    "variance": scores["volatility"],
                    "target_ratio_norm": target_ratio_norm,
                    "target_ratio_raw": scores["target_ratio"],
                }

            else:
                raise ValueError(f"Unknown analysis type: {analysis_type}")

            # Determine tier
            if final_score >= tierlist_config.S_TIER_THRESHOLD:
                tier = "S"
            elif final_score >= tierlist_config.A_TIER_THRESHOLD:
                tier = "A"
            elif final_score >= tierlist_config.B_TIER_THRESHOLD:
                tier = "B"
            else:
                tier = "C"

            results.append(
                {"champion": champion, "tier": tier, "score": final_score, "metrics": metrics}
            )

        # Sort by score (descending)
        results.sort(key=lambda x: x["score"], reverse=True)

        return results
