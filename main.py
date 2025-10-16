import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.db import Database
from src.parser import Parser
from src.assistant import Assistant
from src.constants import CHAMPIONS_LIST, TOP_LIST, JUNGLE_LIST, MID_LIST, ADC_LIST, SUPPORT_LIST, CHAMPION_POOL, normalize_champion_name_for_url

def parse_all_champions_data(db: Database, parser: Parser) -> None:
    db.connect()
    db.init_champion_table()
    db.init_matchups_table()
    for champion in CHAMPIONS_LIST:
        normalized_champion = normalize_champion_name_for_url(champion)
        for matchup in parser.get_champion_data(normalized_champion):
            enemy, winrate, d1, d2, pick, games = matchup
            db.add_matchup(champion, enemy, winrate, d1, d2, pick, games)
    parser.close()
    db.close()

def _parse_champions_for_role(db: Database, parser: Parser, champion_list: list, lane: str) -> None:
    """Parse champion data for a specific role/lane."""
    for champion in champion_list:
        normalized_champion = normalize_champion_name_for_url(champion)
        for matchup in parser.get_champion_data(normalized_champion, lane):
            enemy, winrate, d1, d2, pick, games = matchup
            db.add_matchup(champion, enemy, winrate, d1, d2, pick, games)

def parse_restricted_champions_by_role(db: Database, parser: Parser) -> None:
    """Parse champions organized by role with their specific lane data."""
    db.connect()
    db.init_champion_table()
    db.init_matchups_table()
    
    # Define role mappings
    role_mappings = [
        # (TOP_LIST, "top"),
        (CHAMPION_POOL, "top")
        # (JUNGLE_LIST, "jungle"), 
        # (MID_LIST, "middle"),
        # (ADC_LIST, "bottom"),
        # (SUPPORT_LIST, "support")
    ]
    
    # Parse each role
    for champion_list, lane in role_mappings:
        _parse_champions_for_role(db, parser, champion_list, lane)
    
    parser.close()
    db.close()

def load_data() -> None:
    from src.config import config
    db = Database(config.DATABASE_PATH)
    parser = Parser()
    
    # parse_all_champions_data(db, parser)
    parse_restricted_champions_by_role(db, parser)

def display_tier_lists() -> None:
    """Display tier lists for all lanes."""
    ast = Assistant()
    
    # ast.optimal_trio_from_pool(CHAMPION_POOL)
    # ast.optimal_duo_for_champion("Ambessa", CHAMPION_POOL)

    # lanes = ["top", "jungle", "mid", "adc", "support"]
    # for lane in lanes:
    #     ast.print_champion_list(ast.tierlist_lane(lane))
    
    # Uncomment these for additional functionality:
    # ast.blind_pick()
    # ast.draft(10)
    # ast.score_teams_no_input()
    ast.competitive_draft(3)
    
    ast.close()

def test_optimal_trio() -> None:
    """Test the new optimal trio function with a sample pool."""
    ast = Assistant()
    
    # Test with the current CHAMPION_POOL
    print("\n" + "="*50)
    print("TESTING OPTIMAL TRIO FUNCTION")
    print("="*50)
    
    from src.constants import CHAMPION_POOL
    sample_pool = CHAMPION_POOL[:5]  # Take first 5 champions for testing
    
    try:
        result = ast.optimal_trio_from_pool(sample_pool)
        blind, counter1, counter2, score = result
        print(f"\nFINAL RESULT:")
        print(f"Blind Pick: {blind}")
        print(f"Counterpicks: {counter1}, {counter2}")
        print(f"Total Score: {score:.2f}")
    except Exception as e:
        print(f"Error during trio optimization: {e}")
    
    ast.close()

if __name__ == "__main__":
    print("=" * 60)
    print("DEPRECATED: main.py is deprecated!")
    print("Please use the new unified interface:")
    print("  python lol_coach.py")
    print("=" * 60)
    print()
    
    # Redirect to new system
    import subprocess
    import sys
    subprocess.call([sys.executable, "lol_coach.py"] + sys.argv[1:])
