import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.db import Database
from src.parser import Parser
from src.parallel_parser import ParallelParser
from src.assistant import Assistant
from src.constants import CHAMPIONS_LIST, TOP_LIST, JUNGLE_LIST, MID_LIST, ADC_LIST, SUPPORT_LIST, CHAMPION_POOL, normalize_champion_name_for_url

def parse_all_champions_data(db: Database, parser: Parser) -> None:
    """DEPRECATED: Use parse_all_champions_parallel() instead for 80% faster scraping."""
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

def parse_all_champions_parallel(db: Database, max_workers: int = 10, patch_version: str = None) -> dict:
    """Parse all champions using parallel scraping (87% faster).

    Args:
        db: Database instance
        max_workers: Number of concurrent threads (default: 10)
        patch_version: Optional patch version (e.g. "15.24"). If None, uses config.CURRENT_PATCH

    Returns:
        dict: Statistics with 'success', 'failed', 'total', 'duration' keys
    """
    db.connect()
    parallel_parser = ParallelParser(max_workers=max_workers, patch_version=patch_version)

    try:
        stats = parallel_parser.parse_all_champions(
            db,
            CHAMPIONS_LIST,
            normalize_champion_name_for_url
        )
        return stats
    finally:
        parallel_parser.close()
        db.close()

def _parse_champions_for_role(db: Database, parser: Parser, champion_list: list, lane: str) -> None:
    """Parse champion data for a specific role/lane."""
    for champion in champion_list:
        normalized_champion = normalize_champion_name_for_url(champion)
        for matchup in parser.get_champion_data(normalized_champion, lane):
            enemy, winrate, d1, d2, pick, games = matchup
            db.add_matchup(champion, enemy, winrate, d1, d2, pick, games)

def parse_restricted_champions_by_role(db: Database, parser: Parser) -> None:
    """DEPRECATED: Use parse_champions_by_role_parallel() instead for 80% faster scraping."""
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

def parse_champions_by_role_parallel(db: Database, max_workers: int = 10, patch_version: str = None) -> dict:
    """Parse champions by role using parallel scraping (87% faster).

    Args:
        db: Database instance
        max_workers: Number of concurrent threads (default: 10)
        patch_version: Optional patch version (e.g. "15.24"). If None, uses config.CURRENT_PATCH

    Returns:
        dict: Combined statistics from all roles
    """
    db.connect()
    parallel_parser = ParallelParser(max_workers=max_workers, patch_version=patch_version)

    # Define role mappings
    role_mappings = [
        # (TOP_LIST, "top"),
        (CHAMPION_POOL, "top")
        # (JUNGLE_LIST, "jungle"),
        # (MID_LIST, "middle"),
        # (ADC_LIST, "bottom"),
        # (SUPPORT_LIST, "support")
    ]

    try:
        all_stats = []
        for champion_list, lane in role_mappings:
            stats = parallel_parser.parse_champions_by_role(
                db,
                champion_list,
                lane,
                normalize_champion_name_for_url
            )
            all_stats.append(stats)

        # Combine statistics
        combined_stats = {
            'success': sum(s['success'] for s in all_stats),
            'failed': sum(s['failed'] for s in all_stats),
            'total': sum(s['total'] for s in all_stats),
            'duration': sum(s['duration'] for s in all_stats),
            'roles': all_stats
        }

        return combined_stats
    finally:
        parallel_parser.close()
        db.close()

def load_data() -> None:
    """Load data using parallel scraping for better performance."""
    from src.config import config
    from src.config_constants import scraping_config
    db = Database(config.DATABASE_PATH)

    # Use parallel scraping (80% faster)
    print("Starting parallel scraping...")
    stats = parse_champions_by_role_parallel(db, max_workers=scraping_config.DEFAULT_MAX_WORKERS)

    # Display statistics
    print("\n" + "="*60)
    print("PARALLEL SCRAPING COMPLETED")
    print("="*60)
    print(f"Total champions: {stats['total']}")
    print(f"Successful: {stats['success']}")
    print(f"Failed: {stats['failed']}")
    print(f"Duration: {stats['duration']:.1f}s ({stats['duration']/60:.1f}min)")
    print("="*60)

def load_data_legacy() -> None:
    """DEPRECATED: Use load_data() instead (sequential scraping - much slower)."""
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
