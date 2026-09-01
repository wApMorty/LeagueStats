"""Ban recommendations against a champion pool (live + pre-calculated).

Extracted from src/assistant.py (SPEC-07 E10, lot 2) : déplacement verbatim,
aucun changement de comportement.
"""

from typing import Dict, List

from ..config_constants import analysis_config
from ..db import Database


class BanRecommender:
    """Compute and persist ban recommendations for a champion pool."""

    def __init__(self, db: Database, verbose: bool = False) -> None:
        self.db = db
        self.verbose = verbose

    def get_ban_recommendations(self, champion_pool: List[str], num_bans: int = 5) -> List[tuple]:
        """
        Get ban recommendations against a specific champion pool using reverse lookup.

        For each potential enemy pick, finds your BEST response from your pool.
        Prioritizes banning enemies where even your best response is insufficient.

        Args:
            champion_pool: List of champion names in your pool
            num_bans: Number of ban recommendations to return

        Returns:
            List of tuples (enemy_name, threat_score, best_response_delta2,
                           best_response_champion, matchups_count)
            Sorted by threat_score (descending)
        """
        # Get all potential enemies from database
        all_potential_enemies = set()
        for our_champion in champion_pool:
            try:
                matchups = self.db.get_champion_matchups_by_name(our_champion)
                for m in matchups:
                    if (
                        m.pickrate >= analysis_config.MIN_PICKRATE
                        and m.games >= analysis_config.MIN_MATCHUP_GAMES
                    ):
                        all_potential_enemies.add(m.enemy_name)
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
                                for m in matchups:
                                    if m.enemy_name == enemy_champion:
                                        enemy_pickrate = m.pickrate
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

        # Return in complete format matching database: (enemy, threat_score, best_response_delta2, best_response_champion, matchups_count)
        return [
            (name, threat, best_delta2, best_response, matchups_found)
            for name, threat, best_delta2, best_response, matchups_found in ban_candidates[
                :num_bans
            ]
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
                    for m in matchups:
                        if (
                            m.pickrate >= analysis_config.MIN_PICKRATE
                            and m.games >= analysis_config.MIN_MATCHUP_GAMES
                        ):
                            all_potential_enemies.add(m.enemy_name)
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
                                    for m in matchups:
                                        if m.enemy_name == enemy_champion:
                                            enemy_pickrate = m.pickrate
                                            break
                                except Exception as e:
                                    # Failed to get pickrate - use 0.0 (already set)
                                    if self.verbose:
                                        print(
                                            f"[DEBUG] Failed to get pickrate for {enemy_champion}: {e}"
                                        )
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
        from ..pool_manager import PoolManager

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
