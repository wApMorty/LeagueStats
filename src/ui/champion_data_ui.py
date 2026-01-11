"""UI for champion data management (update from Riot API, recalculate scores)."""

from ..db import Database
from ..config import config
from ..assistant import Assistant
from ..utils.console import clear_console


def update_champion_data() -> None:
    """Update champion data with submenu."""
    clear_console()  # Clear console at start
    print("\n" + "=" * 60)
    print("CHAMPION DATA MANAGEMENT")
    print("=" * 60)
    print("\nOptions:")
    print("1. Update Champion List        - Fetch latest champions from Riot API")
    print("2. Recalculate Champion Scores - Rebuild tier list scores from existing data")
    print("3. Back to main menu")

    choice = input("\nChoose option (1-3): ").strip()

    if choice == "1":
        update_champion_list_from_riot()
    elif choice == "2":
        recalculate_champion_scores()
    elif choice == "3":
        return
    else:
        print("[ERROR] Invalid option")


def update_champion_list_from_riot() -> None:
    """Update champion list from Riot API."""
    print("[INFO] Updating champion data from Riot API...")

    try:
        db = Database(config.DATABASE_PATH)
        db.connect()

        # Ensure table structure is correct
        if not db.create_riot_champions_table():
            print("[ERROR] Failed to create/update champions table")
            return

        # Update from Riot API
        if db.update_champions_from_riot_api():
            # Show some stats
            champion_names = db.get_all_champion_names()
            print(f"[SUCCESS] Updated {len(champion_names)} champions in database")
        else:
            print("[ERROR] Failed to update champion data")

        db.close()
    except Exception as e:
        print(f"[ERROR] Update error: {e}")


def recalculate_champion_scores() -> None:
    """Recalculate champion scores for tier lists from existing matchup data."""
    print("\n[INFO] Recalculating Champion Scores for Tier Lists")
    print("=" * 60)
    print("\nThis will recalculate all champion scores from existing matchup data.")
    print("Useful after modifying tier list configuration or thresholds.")
    print("\nNote: This does NOT fetch new data from the web.")
    print("      Use 'Parse Match Statistics' to update matchup data first.")

    confirm = input("\nProceed with score calculation? (y/n): ").strip().lower()
    if confirm != "y":
        print("[INFO] Cancelled")
        return

    try:
        db = Database(config.DATABASE_PATH)
        db.connect()

        # Check if matchup data exists
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM matchups")
        matchup_count = cursor.fetchone()[0]

        if matchup_count == 0:
            print("\n[ERROR] No matchup data found in database")
            print("[INFO] Please run 'Parse Match Statistics' first to populate matchup data")
            db.close()
            return

        print(f"\n[INFO] Found {matchup_count:,} matchups in database")

        # Initialize champion_scores table
        print("[INFO] Initializing champion_scores table...")
        db.init_champion_scores_table()

        # Calculate scores
        print("[INFO] Calculating global champion scores...")
        assistant = Assistant()
        champions_scored = assistant.calculate_global_scores()

        print(f"\n[SUCCESS] Successfully scored {champions_scored} champions")
        print("[INFO] Tier lists are now ready to use")

        assistant.close()
        db.close()

    except Exception as e:
        print(f"[ERROR] Calculation error: {e}")
        import traceback

        traceback.print_exc()
