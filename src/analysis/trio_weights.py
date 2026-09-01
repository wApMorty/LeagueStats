"""Adaptive base weights + scoring profile for holistic trio evaluation.

Extracted from src/assistant.py (SPEC-07 E10, lot 3) : déplacement verbatim,
aucun changement de comportement.
"""

from typing import Dict, List

from statistics import pvariance

from ..config_constants import analysis_config
from ..db import Database
from . import trio_metrics


class AdaptiveWeightCalculator:
    """Compute variance-based metric weights and apply per-profile modifiers.

    ``_cached_base_weights`` is intentionally absent until first computed
    (checked via ``hasattr``/cleared via ``delattr``) rather than set to
    ``None`` — this is load-bearing: see ``set_scoring_profile`` and the
    frozen asymmetry documented on ``calculate_contextual_total_score``.
    """

    def __init__(self, db: Database, verbose: bool = False) -> None:
        self.db = db
        self.verbose = verbose

    def calculate_adaptive_base_weights(self, sample_trios: List[tuple]) -> Dict[str, float]:
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
                    enemy_coverage = trio_metrics.enemy_coverage_from_matchups(matchups)

                    # Get all enemies for coverage calculation
                    all_enemies = set()
                    for matchup_list in matchups:
                        for m in matchup_list:
                            if (
                                m.pickrate >= analysis_config.MIN_PICKRATE
                                and m.games >= analysis_config.MIN_MATCHUP_GAMES
                            ):
                                all_enemies.add(m.enemy_name)

                    metric_scores["coverage"].append(
                        trio_metrics.coverage_score(enemy_coverage, all_enemies)
                    )
                    metric_scores["balance"].append(
                        trio_metrics.balance_score(trio, matchups, verbose=self.verbose)
                    )
                    metric_scores["consistency"].append(
                        trio_metrics.consistency_score(trio, matchups, verbose=self.verbose)
                    )
                    metric_scores["meta"].append(
                        trio_metrics.meta_score(self.db, enemy_coverage, verbose=self.verbose)
                    )

                except Exception as e:
                    if self.verbose:
                        print(f"[DEBUG] Error processing trio {trio}: {e}")
                    continue

            # Calculate variances
            variances = {}
            for metric, scores in metric_scores.items():
                if len(scores) >= 2:
                    # Population variance, same as the former numpy np.var(scores)
                    variances[metric] = pvariance(scores)
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

    def get_profile_modifiers(self, profile: str = "balanced") -> Dict[str, float]:
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

    def calculate_contextual_total_score(
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
                sample_trios = self.generate_sample_trios_for_weights()
                self._cached_base_weights = self.calculate_adaptive_base_weights(sample_trios)
                if self.verbose:
                    print(f"[DEBUG] Cached adaptive base weights: {self._cached_base_weights}")

            base_weights = self._cached_base_weights

            # 2. Get profile modifiers
            modifiers = self.get_profile_modifiers(profile)

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

    def generate_sample_trios_for_weights(self, sample_size: int = 15) -> List[tuple]:
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
            from ..constants import (
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

    def set_scoring_profile(self, profile: str) -> None:
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
