"""Ban recommendations against a champion pool (live + pre-calculated).

Extracted from src/assistant.py (SPEC-07 E10, lot 2). Menace revue par
SPEC-18 §4 : elle se lit sur la valeur de pool (``pool_value.PoolEvaluator``),
et non plus sur le meilleur ``delta2`` brut de la pool.
"""

from typing import Dict, Iterable, List, Optional

from ..db import Database
from .pool_value import PoolEvaluator


class BanRecommender:
    """Compute and persist ban recommendations for a champion pool."""

    def __init__(self, db: Database, verbose: bool = False) -> None:
        self.db = db
        self.verbose = verbose

    def _rank_threats(
        self,
        champion_pool: List[str],
        lane: Optional[str],
        exclude_champions: Optional[Iterable[str]] = None,
    ) -> List[tuple]:
        """Toutes les menaces de la lane contre ``champion_pool``, la pire d'abord.

        Face à un ennemi ``e``, la pool joue sa meilleure réponse. Le retard
        qu'elle garde est ``force(e) − max_c value(c, e)`` en points de
        winrate ; bannir ``e`` l'évite dans une partie sur ``popularité(e)``.
        Menace = popularité × retard × 100 : les points de winrate gagnés sur
        100 parties en bannissant ``e``. Négative quand la pool domine ``e``.

        L'ancienne menace (meilleur ``delta2`` brut, pickrate et couverture en
        pondérations fixes) favorisait les matchups à petit échantillon.
        """
        if not champion_pool:
            return []
        excluded = {name.lower() for name in exclude_champions or ()}
        excluded |= {name.lower() for name in champion_pool}

        evaluator = PoolEvaluator(self.db, lane)
        values = {champion: evaluator.values(champion) for champion in champion_pool}

        threats = []
        for i, (enemy, weight) in enumerate(zip(evaluator.enemies, evaluator.popularity)):
            if enemy.lower() in excluded:
                continue
            measured = sum(evaluator.measured(c, enemy) for c in champion_pool)
            if not measured:
                continue
            best_champion = max(champion_pool, key=lambda c: values[c][i])
            best = values[best_champion][i]
            margin = evaluator.strength.get(enemy.lower(), 0.0) - best
            threats.append((enemy, 100 * weight * margin, best, best_champion, measured))

        threats.sort(key=lambda row: row[1], reverse=True)
        return threats

    def get_ban_recommendations(
        self,
        champion_pool: List[str],
        num_bans: int = 5,
        lane: Optional[str] = None,
        exclude_champions: Optional[Iterable[str]] = None,
    ) -> List[tuple]:
        """
        Get ban recommendations against a specific champion pool.

        Args:
            champion_pool: List of champion names in your pool
            num_bans: Number of ban recommendations to return
            lane: Lane des matchups et de la popularité. None = toutes lanes.
                  Une pool mono-rôle (SPEC-04, pool_manager.pool_role_to_lane)
                  doit filtrer sur cette lane.
            exclude_champions: Champions déjà indisponibles (bannis ou pickés,
                  camp allié ou ennemi) à écarter des candidats — invariant de
                  draft porté ici plutôt que par l'appelant (dette signalée
                  SPEC-10). Comparaison insensible à la casse.

        Returns:
            List of tuples (enemy_name, threat_score, best_response_value,
                           best_response_champion, matchups_count), threat en
            points de winrate sur 100 parties, best_response_value en points au-dessus
            de la moyenne de la lane. Sorted by threat_score (descending).
        """
        return self._rank_threats(champion_pool, lane, exclude_champions)[:num_bans]

    def precalculate_pool_bans(
        self, pool_name: str, champion_pool: List[str], lane: Optional[str] = None
    ) -> bool:
        """
        Pre-calculate and store ban recommendations for a champion pool in database.

        Same ranking as ``get_ban_recommendations``, every threat kept, stored
        for fast retrieval during draft. Should be called during data updates.

        Returns:
            True if successful, False otherwise
        """
        if not champion_pool:
            if self.verbose:
                print(f"[DEBUG] Empty champion pool: {pool_name}")
            return False

        try:
            saved = self.db.save_pool_ban_recommendations(
                pool_name, self._rank_threats(champion_pool, lane)
            )
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
        from ..pool_manager import PoolManager, pool_role_to_lane

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

                # SPEC-04: une pool mono-rôle (top/jungle/mid/adc/support) a
                # une lane résoluble ; une pool "custom" multi-rôles n'en a
                # pas (None = agrégation toutes lanes, comportement inchangé).
                success = self.precalculate_pool_bans(
                    pool_name, pool.champions, lane=pool_role_to_lane(pool.role)
                )

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
