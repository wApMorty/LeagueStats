"""Interactive pool-selection helpers shared across menu modules.

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9): these three
functions were defined in the legacy file but already consumed from
several different menu domains (data update, tier list, tournament coach,
team builder, pools management), so they live here instead of inside any
single menu module.
"""


def _select_pool_for_analysis():
    """Select a pool for team building analysis with enhanced interface."""
    try:
        from src.pool_manager import PoolManager

        pool_manager = PoolManager()

        pools = pool_manager.get_all_pools()
        if not pools:
            print("[ERROR] No pools found.")
            return None

        print(f"\n" + "=" * 50)
        print("SELECT ANALYSIS POOL")
        print("=" * 50)
        print("Available pools for analysis:")

        # Create numbered list
        pool_list = []
        idx = 1
        for name, pool in sorted(pools.items()):
            pool_list.append((name, pool))
            status = "🔧" if pool.created_by == "system" else "👤"
            suitable = "⭐" if pool.size() >= 5 else "⚠️"  # Indicator for analysis suitability
            print(
                f"  {idx:>2}. {status}{suitable} {name:<18} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
            )
            idx += 1

        print(f"\n  {idx}. Use Assistant's extended pool selector (legacy)")
        print("\n⭐ = Recommended for analysis (5+ champions)")
        print("⚠️ = Small pool (may have limited analysis)")

        try:
            choice = input(f"\nChoose pool (1-{idx} or 'cancel'): ").strip()

            if choice.lower() == "cancel":
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(pool_list):
                selected_name, selected_pool = pool_list[choice_num - 1]
                return (selected_name, selected_pool.champions)
            elif choice_num == idx:
                # Legacy fallback
                return None
            else:
                print(f"[ERROR] Invalid choice. Please choose 1-{idx}.")
                return None

        except ValueError:
            print("[ERROR] Invalid input. Please enter a number.")
            return None

    except Exception as e:
        print(f"[WARNING] Pool selection error: {e}")
        return None


def _select_pool_for_parsing():
    """Select a pool for statistics parsing with enhanced interface."""
    try:
        from src.pool_manager import PoolManager

        pool_manager = PoolManager()

        pools = pool_manager.get_all_pools()
        if not pools:
            print("[ERROR] No pools found.")
            return None

        print(f"\n" + "=" * 50)
        print("SELECT POOL FOR PARSING")
        print("=" * 50)
        print("Available pools for statistics parsing:")

        # Create numbered list
        pool_list = []
        idx = 1
        for name, pool in sorted(pools.items()):
            pool_list.append((name, pool))
            status = "🔧" if pool.created_by == "system" else "👤"
            time_est = f"~{pool.size()*0.5:.2f}-{pool.size()*1:.2f}min"
            print(
                f"  {idx:>2}. {status} {name:<18} | {pool.role:<8} | {pool.size():>2} champs | {time_est:>8} | {pool.description}"
            )
            idx += 1

        print(f"\n  {idx}. Parse ALL Champions (extended analysis - ~60-90 min)")
        print(f"  {idx+1}. Use Top SoloQ Pool (default - ~2-3 min)")

        try:
            choice = input(f"\nChoose pool (1-{idx+1} or 'cancel'): ").strip()

            if choice.lower() == "cancel":
                return None

            choice_num = int(choice)
            if 1 <= choice_num <= len(pool_list):
                selected_name, selected_pool = pool_list[choice_num - 1]
                return (selected_name, selected_pool.champions)
            elif choice_num == idx:
                # All champions option
                from src.constants import CHAMPIONS_LIST

                return ("ALL CHAMPIONS", list(CHAMPIONS_LIST))
            elif choice_num == idx + 1:
                # Default Top SoloQ
                return None
            else:
                print(f"[ERROR] Invalid choice. Please choose 1-{idx+1}.")
                return None

        except ValueError:
            print("[ERROR] Invalid input. Please enter a number.")
            return None

    except Exception as e:
        print(f"[WARNING] Pool selection error: {e}")
        return None


def _select_pool_interactive(pool_manager, action_name="Select pool"):
    """Interactive pool selection with numbered choices."""
    from src.utils.display import safe_print

    pools = pool_manager.get_all_pools()
    if not pools:
        print("[ERROR] No pools found.")
        return None

    print(f"\n" + "=" * 50)
    print(f"{action_name.upper()}")
    print("=" * 50)
    print("Available pools:")

    # Create numbered list
    pool_list = []
    idx = 1
    for name, pool in sorted(pools.items()):
        pool_list.append((name, pool))
        status = "🔧" if pool.created_by == "system" else "👤"
        safe_print(
            f"  {idx:>2}. {status} {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
        )
        idx += 1

    try:
        choice = input(f"\nChoose pool (1-{len(pool_list)} or 'cancel'): ").strip()

        if choice.lower() == "cancel":
            return None

        choice_num = int(choice)
        if 1 <= choice_num <= len(pool_list):
            selected_name, selected_pool = pool_list[choice_num - 1]
            return selected_pool
        else:
            print(f"[ERROR] Invalid choice. Please choose 1-{len(pool_list)}.")
            return None

    except ValueError:
        print("[ERROR] Invalid input. Please enter a number.")
        return None
