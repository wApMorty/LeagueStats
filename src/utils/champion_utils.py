"""Champion validation and pool selection utilities."""

from typing import List, Dict, Optional, Tuple
from src.constants import CHAMPIONS_LIST, ROLE_POOLS, EXTENDED_POOLS
from ..db import Database
from ..config_constants import analysis_config
from .display import safe_print


def validate_champion_name(name: str) -> Optional[str]:
    """
    Validate and normalize champion name with fuzzy matching.

    Args:
        name: Champion name to validate

    Returns:
        Normalized champion name if valid, None otherwise
    """
    if not name:
        return None

    # Normalize input
    normalized = name.strip()

    # Try exact match (case-insensitive)
    for champion in CHAMPIONS_LIST:
        if champion.lower() == normalized.lower():
            return champion

    # Try fuzzy match (starts with)
    suggestions = [c for c in CHAMPIONS_LIST if c.lower().startswith(normalized.lower())]

    if len(suggestions) == 1:
        # Single match - auto-complete
        return suggestions[0]
    elif len(suggestions) > 1:
        # Multiple matches - show suggestions
        print(f"  ⚠️ Ambiguous name. Did you mean: {', '.join(suggestions[:5])}?")
        return None
    else:
        # No matches - try contains
        contains_matches = [c for c in CHAMPIONS_LIST if normalized.lower() in c.lower()]
        if contains_matches:
            print(f"  ⚠️ Champion not found. Similar: {', '.join(contains_matches[:5])}")
        else:
            print(f"  ❌ Champion '{name}' not found")
        return None


def validate_champion_data(db: Database, champion: str, min_games: int = None) -> Tuple[bool, int, int, float]:
    """
    Validate if a champion has sufficient data in database.

    Args:
        db: Database instance
        champion: Champion name to validate
        min_games: Minimum games threshold (defaults to config value)

    Returns:
        Tuple of (has_data, matchup_count, total_games, avg_delta2)
    """
    if min_games is None:
        min_games = analysis_config.MIN_GAMES_THRESHOLD

    try:
        matchups = db.get_champion_matchups_by_name(champion)
        if not matchups:
            return (False, 0, 0, 0.0)

        matchup_count = len(matchups)
        total_games = sum(m[5] for m in matchups)  # games are at index 5

        # Calculate avg_delta2
        valid_matchups = [m for m in matchups if m[5] >= analysis_config.MIN_MATCHUP_GAMES]
        if valid_matchups:
            avg_delta2 = sum(m[3] for m in valid_matchups) / len(valid_matchups)
        else:
            avg_delta2 = 0.0

        # Consider champion viable if has enough data
        has_sufficient_data = (
            matchup_count >= 5 and  # At least 5 matchups
            total_games >= min_games  # At least MIN_GAMES total games
        )

        return (has_sufficient_data, matchup_count, total_games, avg_delta2)

    except Exception as e:
        print(f"Error validating {champion}: {e}")
        return (False, 0, 0, 0.0)


def validate_champion_pool(db: Database, champion_pool: List[str], min_games: int = None) -> Tuple[List[str], Dict]:
    """
    Validate entire champion pool and return viable champions.

    Args:
        db: Database instance
        champion_pool: List of champion names to validate
        min_games: Minimum games threshold (defaults to config value)

    Returns:
        Tuple of (viable_champions, validation_report)
    """
    viable_champions = []
    validation_report = {}

    print("Validating champion pool data...")

    for champion in champion_pool:
        has_data, matchups, games, delta2 = validate_champion_data(db, champion, min_games)

        validation_report[champion] = {
            'has_data': has_data,
            'matchups': matchups,
            'total_games': games,
            'avg_delta2': delta2
        }

        if has_data:
            viable_champions.append(champion)
            safe_print(f"  ✅ {champion}: {matchups} matchups, {games} total games, {delta2:.2f} avg delta2")
        else:
            safe_print(f"  ❌ {champion}: Insufficient data ({matchups} matchups, {games} games)")

    return viable_champions, validation_report


def select_champion_pool() -> List[str]:
    """
    Interactive pool selection for the user.

    Returns:
        Selected champion pool (list of champion names)
    """
    safe_print("🎯 SELECT YOUR CHAMPION POOL:")
    print("Available pools:")
    print("  1. top     - Top lane champions")
    print("  2. support - Support champions")
    print("  3. all     - Combined pool (top + support)")
    print()

    while True:
        try:
            choice = input("Which pool do you want to use? (top/support/all): ").lower().strip()

            if choice in ROLE_POOLS:
                selected_pool = ROLE_POOLS[choice]
                safe_print(f"✅ Selected pool: {choice.upper()}")
                print(f"Champions: {', '.join(selected_pool)}")
                print()
                return selected_pool
            else:
                print("❌ Invalid choice. Please enter: top, support, or all")

        except (EOFError, KeyboardInterrupt):
            print("\nUsing default pool (top)")
            return ROLE_POOLS["top"]


def select_extended_champion_pool() -> List[str]:
    """
    Interactive extended pool selection for Team Builder analysis.

    Returns:
        Selected extended champion pool (list of champion names)
    """
    safe_print("🎯 SELECT CHAMPION POOL FOR ANALYSIS:")
    print("Extended pools for comprehensive analysis:")
    print("  1. top        - Extended top lane pool (~24 champions)")
    print("  2. support    - Extended support pool (~26 champions)")
    print("  3. jungle     - Extended jungle pool (~22 champions)")
    print("  4. mid        - Extended mid lane pool (~29 champions)")
    print("  5. adc        - Extended ADC pool (~21 champions)")
    print("  6. multi-role - Top + Support combined (~50 champions)")
    print("  7. all-roles  - All roles combined (~120+ champions)")
    print()

    pool_options = {
        "1": "top", "top": "top",
        "2": "support", "support": "support", "supp": "support",
        "3": "jungle", "jungle": "jungle", "jgl": "jungle",
        "4": "mid", "mid": "mid", "middle": "mid",
        "5": "adc", "adc": "adc", "bot": "adc",
        "6": "multi-role", "multi": "multi-role", "multi-role": "multi-role",
        "7": "all-roles", "all": "all-roles", "all-roles": "all-roles"
    }

    while True:
        try:
            choice = input("Which extended pool? (1-7 or role name): ").lower().strip()

            if choice in pool_options:
                pool_key = pool_options[choice]
                selected_pool = EXTENDED_POOLS[pool_key]
                safe_print(f"✅ Selected extended pool: {pool_key.upper()}")
                print(f"Pool size: {len(selected_pool)} champions")
                print(f"First few: {', '.join(selected_pool[:5])}, ...")
                print()
                return selected_pool
            else:
                print("❌ Invalid choice. Use 1-7 or role names (top, support, jungle, mid, adc, multi-role, all-roles)")

        except (EOFError, KeyboardInterrupt):
            print("\nUsing default extended pool (top)")
            return EXTENDED_POOLS["top"]


def print_champion_list(champion_list: List[Tuple]) -> None:
    """
    Print formatted champion list.

    Args:
        champion_list: List of tuples containing champion data
    """
    print("=========================")
    for champion in champion_list:
        print(f"{champion[0]} - {champion[1]}")
    print("=========================")
