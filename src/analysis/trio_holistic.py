"""Holistic trio finder: evaluate all 3-champion combinations as a unit.

Extracted from src/assistant.py (SPEC-07 E10, lot 3) : déplacement verbatim,
aucun changement de comportement.
"""

import itertools
from typing import Callable, List, Optional, Tuple

from tqdm import tqdm

from ..db import Database
from . import trio_metrics
from .trio_weights import AdaptiveWeightCalculator


class HolisticTrioFinder:
    """Find optimal 3-champion combinations using holistic evaluation.

    Shares its ``weights`` (an ``AdaptiveWeightCalculator``) with the caller
    so that ``scoring_profile``/``_cached_base_weights`` stay a single source
    of truth across the module, matching pre-extraction behavior where both
    lived directly on ``Assistant``.
    """

    def __init__(
        self, db: Database, weights: AdaptiveWeightCalculator, verbose: bool = False
    ) -> None:
        self.db = db
        self.weights = weights
        self.verbose = verbose

    def find(
        self,
        champion_pool: List[str],
        num_results: int = 5,
        profile: str = "balanced",
        validate_pool: Optional[Callable[[List[str]], Tuple[List[str], dict]]] = None,
        lane: Optional[str] = None,
    ) -> List[dict]:
        """
        Find optimal 3-champion combinations using holistic evaluation.

        Unlike the blind-pick approach, this evaluates all possible trios as complete units.

        Args:
            champion_pool: List of champion names to choose from
            num_results: Number of top trios to return
            profile: Scoring profile ("safe", "meta", "aggressive", "balanced")
            validate_pool: Callable validating/filtering the pool (injected by the
                caller so it stays patchable on the Assistant facade instance)
            lane: Lane optionnelle transmise aux requêtes matchups internes
                  (SPEC-04, pool_manager.pool_role_to_lane). None = agrégation
                  toutes lanes, comportement inchangé.

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
        if len(champion_pool) < 3:
            raise ValueError("Champion pool must contain at least 3 champions")

        print(f"Analyzing all trio combinations from pool: {champion_pool}")

        # Step 1: Validate champion data availability
        viable_champions, validation_report = validate_pool(champion_pool)

        if len(viable_champions) < 3:
            raise ValueError(f"Insufficient data: only {len(viable_champions)}/3 champions viable")

        # Step 2: Generate all combinations of 3 champions
        trio_combinations = list(itertools.combinations(viable_champions, 3))
        print(f"Evaluating {len(trio_combinations)} trio combinations...")

        # Step 2.5: Preload ALL matchups for performance (single DB query instead of 147K+)
        print("Loading matchup data... ", end="", flush=True)
        matchup_cache = self.db.get_all_matchups_bulk(lane=lane)
        all_champions = list(self.db.get_all_champion_names().values())
        print(f"[OK] Loaded {len(matchup_cache):,} matchups")

        trio_rankings = []

        # Set the scoring profile for this analysis
        self.weights.scoring_profile = profile
        if self.verbose:
            print(f"[INFO] Using scoring profile: {profile}")

        # Step 3: Evaluate each trio holistically
        failed_trios = 0
        successful_trios = 0

        # Add progress bar with ETA to show execution isn't frozen
        for trio in tqdm(
            trio_combinations,
            desc="Evaluating trios",
            unit="trio",
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
        ):
            try:
                trio_score = self._evaluate_trio_holistic(
                    trio, matchup_cache, all_champions, lane=lane
                )
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
                successful_trios += 1
            except Exception as e:
                # ALWAYS log trio evaluation failures - not just in verbose mode
                print(f"\n[ERROR] Failed to evaluate trio {trio}: {e}")
                if self.verbose:
                    import traceback

                    traceback.print_exc()
                failed_trios += 1
                continue

        # Summary after completion
        print(f"\n[OK] Analysis complete: {successful_trios} successful, {failed_trios} failed")

        if failed_trios > 0:
            failure_rate = (failed_trios / len(trio_combinations)) * 100
            print(
                f"[ALERTE] {failure_rate:.1f}% failure rate ({failed_trios}/{len(trio_combinations)} trios)"
            )

        if not trio_rankings:
            raise ValueError(
                f"No viable trios found after evaluation. "
                f"{failed_trios} trios failed, {successful_trios} succeeded. "
                f"Check database health and error messages above."
            )

        # Step 4: Sort by total score
        trio_rankings.sort(key=lambda x: x["total_score"], reverse=True)

        return trio_rankings[:num_results]

    def _evaluate_trio_holistic(
        self,
        trio: tuple,
        matchup_cache: dict,
        all_champions: List[str],
        lane: Optional[str] = None,
    ) -> dict:
        """
        Evaluate a trio of champions using holistic scoring with reverse lookup.

        Uses efficient reverse lookup with preloaded matchup cache for performance.

        Args:
            trio: Tuple of 3 champion names
            matchup_cache: Dict mapping (champion, enemy) -> delta2 (preloaded)
            all_champions: List of all champion names (preloaded once by the caller)
            lane: Lane optionnelle transmise à trio_metrics.meta_score (seul
                  appel de ce module à requêter la DB au lieu du cache déjà
                  filtré). None = agrégation toutes lanes, comportement
                  inchangé.

        Returns:
            dict with individual scores and total score
        """
        champion1, champion2, champion3 = trio
        trio_list = [champion1, champion2, champion3]

        # Use reverse lookup to build enemy coverage efficiently
        enemy_coverage = {}  # enemy_name -> (best_delta2, champion_handling_it)

        for enemy_champion in all_champions:
            best_delta2 = -float("inf")
            best_counter = None

            # For this enemy, check which champion in our trio counters it best
            for our_champion in trio_list:
                try:
                    # Use cache instead of DB query (99%+ speedup)
                    cache_key = (our_champion.lower(), enemy_champion.lower())
                    delta2 = matchup_cache.get(cache_key)

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
        coverage_score = trio_metrics.coverage_score(enemy_coverage, all_enemies)
        balance_score = trio_metrics.balance_score_reverse(
            trio_list, enemy_coverage, matchup_cache, verbose=self.verbose
        )
        consistency_score = trio_metrics.consistency_score_reverse(
            trio_list, enemy_coverage, verbose=self.verbose
        )
        meta_score = trio_metrics.meta_score(
            self.db, enemy_coverage, verbose=self.verbose, lane=lane
        )

        # Calculate contextual total score using adaptive weights
        total_score, used_weights = self.weights.calculate_contextual_total_score(
            {
                "coverage_score": coverage_score,
                "balance_score": balance_score,
                "consistency_score": consistency_score,
                "meta_score": meta_score,
            },
            profile=getattr(self.weights, "scoring_profile", "balanced"),
        )

        return {
            "total_score": total_score,
            "coverage_score": coverage_score,
            "balance_score": balance_score,
            "consistency_score": consistency_score,
            "meta_score": meta_score,
            "enemy_coverage": enemy_coverage,
        }
