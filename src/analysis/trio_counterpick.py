"""Classic (blind-pick + counterpick-duo) trio/duo search.

Extracted from src/assistant.py (SPEC-07 E10, lot 4). Scoring revu par
SPEC-18 §4 (``pool_value.PoolEvaluator``) : blind au winrate de lane rétréci,
duo à la valeur de contre-pick du trio. Distinct de trio_holistic.py, qui évalue
les trios comme des unités plutôt que blind pick + duo de contre-picks.
"""

from itertools import combinations
from typing import Callable, List, Optional, Tuple

from ..constants import CHAMPION_POOL
from ..db import Database
from ..utils.display import safe_print
from .pool_value import PoolEvaluator
from .trio_tactics import TrioTacticsReporter


class CounterpickTrioFinder:
    """Find a blind pick + best counterpick duo from a champion pool."""

    def __init__(self, db: Database, tactics: TrioTacticsReporter, verbose: bool = False) -> None:
        self.db = db
        self.tactics = tactics
        self.verbose = verbose

    def _find_optimal_counterpick_duo(
        self,
        remaining_pool: List[str],
        blind_champion: str,
        show_ranking: bool = False,
        lane: Optional[str] = None,
        evaluator: Optional[PoolEvaluator] = None,
    ) -> tuple:
        """Duo qui maximise la valeur de contre-pick du trio (SPEC-18 §4).

        Score : gain moyen en points de winrate quand, face à chaque ennemi
        pondéré par sa popularité sur la lane, on joue le meilleur du trio
        (``PoolEvaluator.counter_value``).

        Args:
            lane: Lane des matchups et de la popularité. None = toutes lanes.
            evaluator: Évaluateur déjà construit pour ``lane`` (évite de
                recharger les tables quand l'appelant en a un).
        """
        if len(remaining_pool) < 2:
            raise ValueError(f"Need at least 2 champions in pool, got {len(remaining_pool)}")
        evaluator = evaluator or PoolEvaluator(self.db, lane)

        rankings = sorted(
            (
                {
                    "duo": duo,
                    "total_score": evaluator.counter_value([blind_champion, *duo]),
                    "coverage": evaluator.coverage([blind_champion, *duo]),
                }
                for duo in combinations(remaining_pool, 2)
            ),
            key=lambda info: info["total_score"],
            reverse=True,
        )

        if show_ranking:
            safe_print("\nTOP DUO RANKINGS:")
            safe_print("─" * 80)
            for i, info in enumerate(rankings[:5], 1):
                safe_print(f"{i}. {info['duo'][0]} + {info['duo'][1]}")
                print(
                    f"    Gain en contre-pick : {info['total_score']:+.2f} pts | "
                    f"Couverture : {info['coverage']:.0%} des games"
                )
        print(f"Evaluated {len(rankings)} duos")

        best = rankings[0]
        return best["duo"], best["total_score"]

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
        2. Blind pick = best shrunk lane winrate (SPEC-18)
        3. From remaining champions, find duo that maximizes counterpick value

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

        # Step 1: blind pick = meilleur winrate de lane rétréci (SPEC-18).
        # avg_delta2 est nul par construction, trier dessus revenait au hasard.
        evaluator = PoolEvaluator(self.db, lane)
        blind_candidates = sorted(
            viable_champions,
            key=lambda champ: evaluator.strength.get(champ.lower(), 0.0),
            reverse=True,
        )

        safe_print("\nBLIND PICK RANKINGS:")
        safe_print("─" * 60)
        for i, champ in enumerate(blind_candidates[:5], 1):
            games = validation_report[champ]["total_games"]
            force = evaluator.strength.get(champ.lower(), 0.0)
            safe_print(f"{i}. {champ}")
            print(f"    Winrate vs moyenne de la lane : {force:+.2f} pts | Games: {games:,}")

        best_blind = blind_candidates[0]
        safe_print(f"\n[OK] Selected blind pick: {best_blind}")

        # Step 2: Find best counterpick duo from remaining viable champions
        remaining_pool = [champ for champ in viable_champions if champ != best_blind]

        if len(remaining_pool) < 2:
            raise ValueError(
                f"Insufficient remaining champions for duo: only {len(remaining_pool)} available"
            )

        try:
            best_duo, total_score = self._find_optimal_counterpick_duo(
                remaining_pool, best_blind, show_ranking=True, lane=lane, evaluator=evaluator
            )
        except Exception as e:
            print(f"Error finding optimal duo: {e}")
            raise ValueError(f"Failed to find optimal counterpick duo: {e}")

        if best_duo is None:
            raise ValueError("No viable counterpick duo found")

        print(f"Best counterpick duo: {best_duo}")
        print(f"Gain en contre-pick du trio : {total_score:+.2f} pts")
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
        has_data, matchups, games, _ = validate_champion(fixed_champion)

        if not has_data:
            safe_print(f"\n[ERREUR] Fixed champion '{fixed_champion}' has insufficient data")
            print(f"  Matchups: {matchups}, Games: {games}")
            raise ValueError(f"Fixed champion '{fixed_champion}' has insufficient data in database")

        safe_print(f"[OK] Fixed champion validated: {matchups} matchups, {games} total games")

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
            best_duo, total_score = self._find_optimal_counterpick_duo(
                viable_companions, fixed_champion, show_ranking=True, lane=lane
            )
        except Exception as e:
            print(f"Error finding optimal duo: {e}")
            raise ValueError(f"Failed to find optimal companion duo: {e}")

        if best_duo is None:
            raise ValueError("No viable companion duo found")

        print(f"\nBest companions: {best_duo}")
        print(f"Gain en contre-pick du trio : {total_score:+.2f} pts")
        safe_print(f"\n[OK] Optimal trio: {fixed_champion} + {best_duo[0]} + {best_duo[1]}")

        # Add tactical analysis
        result_trio = (fixed_champion, best_duo[0], best_duo[1], total_score)
        self.tactics.analyze(result_trio, lane=lane)

        return result_trio
