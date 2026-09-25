"""Tier list generation for champion pools."""

from typing import List

from ..db import Database
from ..config_constants import analysis_config
from .scoring import ChampionScorer
from .pool_value import PoolEvaluator
from .shrink import shrunk_lane_winrates


class TierListGenerator:
    """Generates tier lists based on champion performance metrics."""

    def __init__(self, db: Database, scorer: ChampionScorer):
        self.db = db
        self.scorer = scorer

    def generate_tier_list(
        self,
        champion_pool: List[str],
        analysis_type: str = "blind_pick",
        lane: str = None,
        verbose: bool = False,
    ) -> List[dict]:
        """
        Generate a tier list for a champion pool using pre-computed global scores.

        Uses global normalization: normalizes metrics based on ALL champions in the
        database (scoped to the same lane), making scores comparable across
        different pools.

        Args:
            champion_pool: List of champion names to include in tier list
            analysis_type: "blind_pick" or "counter_pick"
            lane: Optional lane filter (one of scraping_config.LANES, e.g.
                  "middle"). None = toutes lanes agrégées (comportement
                  historique ; utilisé pour les pools multi-lane/custom).
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
        lane_key = lane or analysis_config.ALL_LANES_KEY

        # Check if champion_scores table exists and has data
        if not self.db.champion_scores_table_exists():
            print("[WARNING] Champion scores not found in database.")
            print("[INFO] Please run 'Parse Match Statistics' to generate scores first.")
            return []

        # Step 1: the lane's champions, for global normalization
        all_scores_data = self.db.get_all_champion_scores(lane=lane_key)

        if not all_scores_data:
            print(f"[ERROR] No champion scores found in database for lane={lane_key}")
            return []
        lane_champions = [row[0] for row in all_scores_data]

        # SPEC-18 : un seul critère mesuré par type de tier list. Blind : le
        # winrate de lane rétréci. Contre-pick : le gain moyen quand on ne joue
        # le champion que contre les ennemis où il bat la moyenne, pondérés par
        # leur popularité. Les anciennes composantes (avg_delta2, stabilité,
        # couverture, pic d'impact, volatilité, cibles) avaient la dispersion
        # du bruit pur.
        if analysis_type == "blind_pick":
            winrates = shrunk_lane_winrates(self.db, lane)
            raw = {name: winrates[name] for name in lane_champions if name in winrates}
            metric = "lane_winrate"
        elif analysis_type == "counter_pick":
            evaluator = PoolEvaluator(self.db, lane)
            raw = {name: evaluator.counter_value([name], floor=0.0) for name in lane_champions}
            metric = "counter_gain"
        else:
            raise ValueError(f"Unknown analysis type: {analysis_type}")

        if not raw:
            return []
        low, high = min(raw.values()), max(raw.values())
        if high == low:
            low, high = low - 0.05, high + 0.05
        if verbose:
            print(f"[INFO] {metric}: {low:.2f} to {high:.2f}")

        # Step 2: score the pool
        results = []
        for champion in champion_pool:
            value = raw.get(champion)
            if value is None:
                if verbose:
                    print(f"  [SKIP] {champion}: No data in database for lane={lane_key}")
                continue

            normalized = max(0.0, min(1.0, (value - low) / (high - low)))
            final_score = normalized * 100
            metrics = {
                "final_score": final_score,
                "avg_performance_norm": normalized,
                metric: value,
            }

            if final_score >= analysis_config.TIER_THRESHOLDS["S"]:
                tier = "S"
            elif final_score >= analysis_config.TIER_THRESHOLDS["A"]:
                tier = "A"
            elif final_score >= analysis_config.TIER_THRESHOLDS["B"]:
                tier = "B"
            else:
                tier = "C"

            results.append(
                {"champion": champion, "tier": tier, "score": final_score, "metrics": metrics}
            )

        results.sort(key=lambda x: x["score"], reverse=True)
        return results
