"""Pure per-metric calculators shared by trio_weights.py and trio_holistic.py.

Extracted from src/assistant.py (SPEC-07 E10, lot 3) : déplacement verbatim,
aucun changement de comportement. Module de fonctions (pas de classe) pour
casser le cycle d'import entre le calcul des poids adaptatifs (métriques
"classiques") et l'évaluation holistique de trio (métriques "reverse") : les
deux composants importent ces fonctions plutôt que de s'importer l'un l'autre.
"""

from typing import Dict, List

from ..config_constants import analysis_config
from ..db import Database


def coverage_score(enemy_coverage: dict, all_enemies: set) -> float:
    """Calculate how well the trio covers all potential enemies."""
    if not all_enemies:
        return 0.0

    # Sum of best delta2 scores against all enemies
    total_coverage = sum(max(0, delta2) for delta2, _ in enemy_coverage.values())
    max_possible = len(all_enemies) * 10  # Theoretical max delta2 is around 10

    return min(100.0, (total_coverage / max_possible) * 100)


def balance_score_reverse(
    trio_list: List[str], enemy_coverage: dict, matchup_cache: dict, verbose: bool = False
) -> float:
    """
    Calculate diversity of matchup profiles using reverse lookup data.

    Args:
        trio_list: List of champion names in the trio
        enemy_coverage: Dict mapping enemy -> (delta2, best_counter)
        matchup_cache: Preloaded matchup cache for performance

    Returns:
        Balance score 0-100 (higher = more balanced, fewer shared weaknesses)
    """
    try:
        # For each champion, identify their weaknesses from enemy_coverage
        champion_weaknesses = {champ: set() for champ in trio_list}

        for enemy, (best_delta2, best_counter) in enemy_coverage.items():
            # Check each champion individually against this enemy
            for our_champion in trio_list:
                try:
                    # Use cache instead of DB query
                    cache_key = (our_champion.lower(), enemy.lower())
                    delta2 = matchup_cache.get(cache_key)

                    # If this champion struggles against this enemy (negative delta2)
                    if delta2 is not None and delta2 < -2.0:
                        champion_weaknesses[our_champion].add(enemy)

                except Exception:
                    continue

        # Calculate overlap in weaknesses
        weakness_sets = list(champion_weaknesses.values())
        if len(weakness_sets) < 2:
            return 50.0

        # Get union and intersection of all weaknesses
        all_weaknesses = set.union(*weakness_sets) if weakness_sets else set()
        shared_weaknesses = set.intersection(*weakness_sets) if weakness_sets else set()

        if len(all_weaknesses) == 0:
            return 100.0  # No weaknesses found

        # Calculate balance: fewer shared weaknesses = better balance
        balance_ratio = 1 - (len(shared_weaknesses) / len(all_weaknesses))
        return balance_ratio * 100

    except Exception as e:
        if verbose:
            print(f"[ERROR] Balance score calculation failed: {e}")
        return 50.0  # Neutral score on error


def consistency_score_reverse(
    trio_list: List[str], enemy_coverage: dict, verbose: bool = False
) -> float:
    """
    Calculate consistency using reverse lookup data.

    Args:
        trio_list: List of champion names in the trio
        enemy_coverage: Dict mapping enemy -> (delta2, best_counter)

    Returns:
        Consistency score 0-100 (higher = more consistent performance)
    """
    try:
        all_delta2_scores = []

        # Collect all delta2 scores from the coverage data
        for enemy, (delta2, counter) in enemy_coverage.items():
            all_delta2_scores.append(delta2)

        if not all_delta2_scores:
            return 0.0

        # Calculate consistency metrics
        import statistics

        mean_score = statistics.mean(all_delta2_scores)

        if len(all_delta2_scores) > 1:
            variance = statistics.variance(all_delta2_scores)
            # Convert variance to consistency score (lower variance = higher consistency)
            consistency = max(0, 100 - (variance * 5))  # Scale appropriately
        else:
            consistency = 50  # Neutral if only one score

        # Factor in average performance
        avg_performance = max(0, mean_score + 5) * 10  # Shift and scale (-5 to +5 -> 0 to 100)

        # Weighted combination: 60% consistency, 40% performance
        return consistency * 0.6 + avg_performance * 0.4

    except Exception as e:
        if verbose:
            print(f"[ERROR] Consistency score calculation failed: {e}")
        return 50.0


def balance_score(trio: tuple, all_matchups: List[List], verbose: bool = False) -> float:
    """Calculate diversity of matchup profiles to avoid same weaknesses."""
    try:
        # For each champion, get their worst matchups (big threats)
        champion_weaknesses = []

        for i, matchups in enumerate(all_matchups):
            weaknesses = []
            for m in matchups:
                if (
                    m.pickrate >= analysis_config.MIN_PICKRATE
                    and m.games >= analysis_config.MIN_MATCHUP_GAMES
                ):
                    if m.delta2 < -2.0:  # Significantly negative matchup
                        weaknesses.append(m.enemy_name)
            champion_weaknesses.append(set(weaknesses))

        # Calculate overlap in weaknesses (lower overlap = better balance)
        if len(champion_weaknesses) < 2:
            return 50.0

        total_weaknesses = len(
            champion_weaknesses[0] | champion_weaknesses[1] | champion_weaknesses[2]
        )
        shared_weaknesses = len(
            champion_weaknesses[0] & champion_weaknesses[1] & champion_weaknesses[2]
        )

        if total_weaknesses == 0:
            return 100.0

        balance_ratio = 1 - (shared_weaknesses / total_weaknesses)
        return balance_ratio * 100

    except Exception as e:
        # ALWAYS log calculation failures - these indicate bugs or data issues
        print(f"[ERROR] Balance score calculation failed for trio {trio}: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        return 50.0  # Neutral score on error


def consistency_score(trio: tuple, all_matchups: List[List], verbose: bool = False) -> float:
    """Calculate how consistently the trio performs across matchups."""
    try:
        all_scores = []

        for matchups in all_matchups:
            for m in matchups:
                if (
                    m.pickrate >= analysis_config.MIN_PICKRATE
                    and m.games >= analysis_config.MIN_MATCHUP_GAMES
                ):
                    all_scores.append(m.delta2)

        if not all_scores:
            return 0.0

        # Lower variance = more consistent
        import statistics

        mean_score = statistics.mean(all_scores)
        if len(all_scores) > 1:
            variance = statistics.variance(all_scores)
            # Convert variance to consistency score (0-100)
            consistency = max(0, 100 - (variance * 5))  # Scale variance appropriately
        else:
            consistency = 50

        # Also factor in average performance
        avg_performance = max(0, mean_score + 5) * 10  # Shift and scale

        return consistency * 0.6 + avg_performance * 0.4

    except Exception as e:
        # ALWAYS log calculation failures - these indicate bugs or data issues
        print(f"[ERROR] Consistency score calculation failed for trio {trio}: {e}")
        if verbose:
            import traceback

            traceback.print_exc()
        return 50.0


def meta_score(db: Database, enemy_coverage: dict, verbose: bool = False) -> float:
    """
    Calculate performance against popular/meta champions.

    Uses actual pickrate data to determine meta relevance:
    - Gets pickrate for each enemy champion from database
    - Calculates weighted average of delta2 scores by pickrate
    - Higher pickrate champions have more influence on the score

    Returns:
        Score 0-100 representing performance vs meta champions
    """
    try:
        if not enemy_coverage:
            return 50.0  # Neutral if no coverage data

        # Get pickrate data for all enemies and calculate weighted score
        weighted_sum = 0.0
        total_weight = 0.0

        for enemy, (delta2, _) in enemy_coverage.items():
            try:
                # Get pickrate for this enemy champion
                enemy_matchups = db.get_champion_matchups_by_name(enemy)
                if not enemy_matchups:
                    continue

                # Calculate average pickrate for this champion
                # Each matchup is a Matchup object with: enemy_name, winrate, delta1, delta2, pickrate, games
                pickrates = [matchup.pickrate for matchup in enemy_matchups if matchup.pickrate > 0]

                if not pickrates:
                    continue

                avg_pickrate = sum(pickrates) / len(pickrates)

                # Weight the delta2 score by pickrate
                # Higher pickrate = more meta relevant = higher weight
                weight = avg_pickrate
                weighted_sum += max(0, delta2) * weight
                total_weight += weight

            except Exception as e:
                if verbose:
                    print(f"[DEBUG] Error processing {enemy} pickrate: {e}")
                continue

        if total_weight == 0:
            return 50.0  # No valid pickrate data

        # Calculate weighted average
        weighted_avg = weighted_sum / total_weight

        # Scale to 0-100 range
        # delta2 typically ranges from -5 to +5, so we shift and scale
        score = min(100.0, max(0.0, (weighted_avg + 5) * 10))

        return score

    except Exception as e:
        if verbose:
            print(f"[ERROR] Meta score calculation failed: {e}")
        return 50.0


def enemy_coverage_from_matchups(matchups_list: List[List]) -> Dict[str, tuple]:
    """
    Calculate enemy coverage for a set of champions.

    Args:
        matchups_list: List of matchup lists for each champion

    Returns:
        Dictionary mapping enemy_name -> (best_delta2, champion_handling_it)
    """
    enemy_coverage = {}
    all_enemies = set()

    for i, matchups in enumerate(matchups_list):
        champion_name = f"Champion{i+1}"  # Fallback name, should be passed properly

        for m in matchups:
            if (
                m.pickrate >= analysis_config.MIN_PICKRATE
                and m.games >= analysis_config.MIN_MATCHUP_GAMES
            ):
                all_enemies.add(m.enemy_name)
                if m.enemy_name not in enemy_coverage or m.delta2 > enemy_coverage[m.enemy_name][0]:
                    enemy_coverage[m.enemy_name] = (m.delta2, champion_name)

    return enemy_coverage
