"""Menu 6 -- champion pool management: top-level menu, listing, statistics.

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9). CRUD operations
(create/edit/delete/duplicate) live in src/ui/pools_crud_ui.py.
"""

from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_interactive
from src.ui.pools_crud_ui import create_new_pool, edit_pool, delete_pool, duplicate_pool


def manage_champion_pools():
    """Manage champion pools with interactive interface."""
    clear_console()  # Clear console at start
    from src.pool_manager import PoolManager
    from src.assistant import Assistant

    print("[INFO] Champion Pool Manager")

    try:
        pool_manager = PoolManager()
        assistant = Assistant()
        available_champions = set(assistant.db.get_all_champion_names().values())

        while True:
            print("\n" + "=" * 60)
            print("CHAMPION POOL MANAGEMENT")
            print("=" * 60)

            menu = """
Pool Management Options:
  1. List all pools
  2. View pool details
  3. Create new pool
  4. Edit existing pool
  5. Delete pool
  6. Duplicate pool
  7. Search pools
  8. Pool statistics
  9. Back to main menu

Choose an option (1-9): """

            choice = input(menu).strip()

            if choice == "1":
                list_pools(pool_manager)
            elif choice == "2":
                view_pool_details(pool_manager)
            elif choice == "3":
                create_new_pool(pool_manager, available_champions)
            elif choice == "4":
                edit_pool(pool_manager, available_champions)
            elif choice == "5":
                delete_pool(pool_manager)
            elif choice == "6":
                duplicate_pool(pool_manager)
            elif choice == "7":
                search_pools(pool_manager)
            elif choice == "8":
                show_pool_statistics(pool_manager)
            elif choice == "9":
                pool_manager.save_custom_pools()
                print("[INFO] Custom pools saved!")
                break
            else:
                print("[ERROR] Invalid option. Please choose 1-9.")

        assistant.close()

    except Exception as e:
        print(f"[ERROR] Pool manager error: {e}")
        if hasattr(e, "__traceback__"):
            import traceback

            traceback.print_exc()


def list_pools(pool_manager):
    """List all available pools."""
    print("\n" + "=" * 50)
    print("ALL CHAMPION POOLS")
    print("=" * 50)

    pools = pool_manager.get_all_pools()
    if not pools:
        print("No pools found.")
        return

    # Group by type
    system_pools = []
    custom_pools = []

    for name, pool in pools.items():
        if pool.created_by == "system":
            system_pools.append((name, pool))
        else:
            custom_pools.append((name, pool))

    if system_pools:
        print("\n🔧 SYSTEM POOLS:")
        for name, pool in sorted(system_pools):
            print(
                f"  {name:<20} | {pool.role:<8} | {pool.size():>2} champions | {pool.description}"
            )

    if custom_pools:
        print("\n👤 CUSTOM POOLS:")
        for name, pool in sorted(custom_pools):
            print(
                f"  {name:<20} | {pool.role:<8} | {pool.size():>2} champions | {pool.description}"
            )

    if not custom_pools:
        print("\n👤 CUSTOM POOLS: None created yet")


def view_pool_details(pool_manager):
    """View details of a specific pool."""
    pool = _select_pool_interactive(pool_manager, "View pool details")
    if not pool:
        return

    print(f"\n" + "=" * 50)
    print(f"POOL DETAILS: {pool.name}")
    print("=" * 50)
    print(f"Role: {pool.role}")
    print(f"Description: {pool.description}")
    print(f"Created by: {pool.created_by}")
    print(f"Tags: {', '.join(pool.tags) if pool.tags else 'None'}")
    print(f"Champions ({pool.size()}):")

    # Display champions in columns
    champions = pool.champions
    cols = 3
    for i in range(0, len(champions), cols):
        row = champions[i : i + cols]
        print(f"  {' | '.join(f'{champ:<15}' for champ in row)}")


def search_pools(pool_manager):
    """Search for pools."""
    query = input("\nEnter search query: ").strip()
    matches = pool_manager.search_pools(query)

    if matches:
        print(f"\nFound {len(matches)} pools:")
        for name in matches:
            pool = pool_manager.get_pool(name)
            print(f"  {name} | {pool.role} | {pool.size()} champions")
    else:
        print("No pools found.")


def show_pool_statistics(pool_manager):
    """Show pool statistics - global or individual pool analysis."""
    print("\n" + "=" * 50)
    print("POOL STATISTICS")
    print("=" * 50)

    menu = """
Statistics Options:
  1. Global pool statistics (counts by type/role)
  2. Individual pool performance analysis
  3. Back to pool management

Choose an option (1-3): """

    choice = input(menu).strip()

    if choice == "1":
        # Global statistics (original functionality)
        stats = pool_manager.get_pool_stats()

        print("\n" + "=" * 40)
        print("GLOBAL POOL STATISTICS")
        print("=" * 40)
        print(f"Total pools: {stats['total_pools']}")
        print(f"Custom pools: {stats['custom_pools']}")
        print(f"System pools: {stats['system_pools']}")

        print("\nBy role:")
        for key, value in stats.items():
            if key.endswith("_pools") and not key.startswith(("total", "custom", "system")):
                role = key.replace("_pools", "")
                print(f"  {role.capitalize()}: {value}")

    elif choice == "2":
        # Individual pool performance analysis (NEW)
        show_individual_pool_statistics(pool_manager)

    elif choice == "3":
        return

    else:
        print("[ERROR] Invalid option. Please choose 1-3.")


def show_individual_pool_statistics(pool_manager):
    """Show detailed performance statistics for a specific champion pool."""
    from src.analysis.pool_statistics import PoolStatisticsCalculator, format_pool_statistics
    from src.assistant import Assistant
    from src.utils.display import safe_print

    # Select pool
    pool = _select_pool_interactive(pool_manager, "Select pool for statistics")
    if not pool:
        return

    safe_print(f"\n[INFO] Calculating statistics for pool: {pool.name}")
    print("[INFO] This may take a moment...")

    try:
        # Initialize calculator
        assistant = Assistant()
        calculator = PoolStatisticsCalculator(assistant.db)

        # Performance optimization: Warm cache before analysis (99% faster)
        print("[INFO] Warming cache for performance...")
        assistant.warm_cache(pool.champions)

        # Calculate statistics
        stats = calculator.calculate_pool_statistics(pool.name, pool.champions)

        # Clear cache to free memory
        assistant.clear_cache()

        # Display formatted output
        output = format_pool_statistics(stats)
        print("\n" + output)

        # Prompt to continue
        input("\nPress Enter to continue...")

        assistant.close()

    except Exception as e:
        print(f"[ERROR] Failed to calculate pool statistics: {e}")
        import traceback

        traceback.print_exc()
