"""Menu 6 -- champion pool CRUD (create/edit/delete/duplicate).

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9). The top-level pool
menu and listing/statistics live in src/ui/pools_menu_ui.py.
"""

from src.ui.pool_selection_ui import _select_pool_interactive


def create_new_pool(pool_manager, available_champions):
    """Create a new champion pool."""
    from src.pool_manager import validate_champion_name, suggest_champions

    print("\n" + "=" * 50)
    print("CREATE NEW POOL")
    print("=" * 50)

    name = input("Pool name: ").strip()
    if not name:
        print("[ERROR] Pool name cannot be empty.")
        return

    if pool_manager.get_pool(name):
        print(f"[ERROR] Pool '{name}' already exists.")
        return

    description = input("Description (optional): ").strip()
    role = input("Role (top/jungle/mid/adc/support/custom): ").strip().lower()
    if role not in ["top", "jungle", "mid", "adc", "support", "custom"]:
        role = "custom"

    # Tags
    tags_input = input("Tags (comma-separated, optional): ").strip()
    tags = [tag.strip() for tag in tags_input.split(",") if tag.strip()] if tags_input else []

    print("\nAdd champions to the pool:")
    print("  - Enter champion names one by one")
    print("  - Type 'done' when finished")
    print("  - Type 'list' to see suggestions")

    champions = []
    while True:
        champ_input = input(f"Champion {len(champions)+1} (or 'done'/'list'): ").strip()

        if champ_input.lower() == "done":
            break
        elif champ_input.lower() == "list":
            print("Available champions:", ", ".join(sorted(list(available_champions)[:20])) + "...")
            continue

        # Auto-suggest if partial match
        if champ_input and not validate_champion_name(champ_input, available_champions):
            suggestions = suggest_champions(champ_input, available_champions)
            if suggestions:
                print(f"Did you mean: {', '.join(suggestions)}")
                continue
            else:
                print(f"[WARNING] Champion '{champ_input}' not found.")
                continue

        if champ_input and champ_input not in champions:
            champions.append(champ_input)
            print(f"  Added: {champ_input}")
        elif champ_input in champions:
            print(f"  Already in pool: {champ_input}")

    if not champions:
        print("[ERROR] Cannot create empty pool.")
        return

    if pool_manager.create_pool(name, champions, description, role, tags):
        print(f"[SUCCESS] Created pool '{name}' with {len(champions)} champions!")
    else:
        print(f"[ERROR] Failed to create pool '{name}'.")


def edit_pool(pool_manager, available_champions):
    """Edit an existing pool."""
    from src.pool_manager import validate_champion_name, suggest_champions

    # Select pool interactively
    pool = _select_pool_interactive(pool_manager, "Edit pool")
    if not pool:
        return

    if pool.created_by == "system":
        print(f"[ERROR] Cannot edit system pool '{pool.name}'.")
        return

    while True:
        # Display current pool state
        print(f"\n" + "=" * 60)
        print(f"EDITING POOL: {pool.name}")
        print("=" * 60)
        print(f"Role: {pool.role} | Description: {pool.description}")
        print(f"Tags: {', '.join(pool.tags) if pool.tags else 'None'}")
        print(f"Current champions ({pool.size()}):")

        # Display champions in a compact format
        champions = pool.champions
        if champions:
            cols = 4
            for i in range(0, len(champions), cols):
                row = champions[i : i + cols]
                print(f"  {' | '.join(f'{champ:<12}' for champ in row)}")
        else:
            print("  [No champions in pool]")

        menu = """
Edit Options:
  1. Add champion
  2. Remove champion
  3. Edit description
  4. Edit role
  5. Edit tags
  6. Back to pool menu

Choose option (1-6): """

        choice = input(menu).strip()

        if choice == "1":
            print(f"\nAdding champion to '{pool.name}'")
            champ = input("Champion to add: ").strip()
            if champ:
                if validate_champion_name(champ, available_champions):
                    if pool.add_champion(champ):
                        print(f"[SUCCESS] Added {champ} to {pool.name}")
                    else:
                        print(f"[INFO] {champ} already in pool")
                else:
                    suggestions = suggest_champions(champ, available_champions)
                    if suggestions:
                        print(f"[ERROR] Champion not found. Suggestions: {', '.join(suggestions)}")
                    else:
                        print(f"[ERROR] Champion '{champ}' not found.")

        elif choice == "2":
            if not pool.champions:
                print("[INFO] Pool is empty, no champions to remove.")
                continue

            print(f"\nRemoving champion from '{pool.name}'")
            print("Current champions:")
            for i, champ in enumerate(pool.champions, 1):
                print(f"  {i}. {champ}")

            try:
                remove_choice = input("\nRemove by number or name: ").strip()

                # Try as number first
                if remove_choice.isdigit():
                    idx = int(remove_choice) - 1
                    if 0 <= idx < len(pool.champions):
                        champ_to_remove = pool.champions[idx]
                        pool.remove_champion(champ_to_remove)
                        print(f"[SUCCESS] Removed {champ_to_remove} from {pool.name}")
                    else:
                        print("[ERROR] Invalid number.")
                else:
                    # Try as name
                    if pool.remove_champion(remove_choice):
                        print(f"[SUCCESS] Removed {remove_choice} from {pool.name}")
                    else:
                        print(f"[ERROR] {remove_choice} not found in pool")
            except ValueError:
                print("[ERROR] Invalid input.")

        elif choice == "3":
            print(f"\nEditing description for '{pool.name}'")
            print(f"Current: {pool.description}")
            new_desc = input("New description (or press Enter to keep current): ").strip()
            if new_desc:
                pool.description = new_desc
                print("[SUCCESS] Description updated")

        elif choice == "4":
            print(f"\nEditing role for '{pool.name}'")
            print(f"Current: {pool.role}")
            print("Available roles: top, jungle, mid, adc, support, custom")
            new_role = input("New role: ").strip().lower()
            if new_role in ["top", "jungle", "mid", "adc", "support", "custom"]:
                pool.role = new_role
                print("[SUCCESS] Role updated")
            elif new_role:
                print("[ERROR] Invalid role")

        elif choice == "5":
            print(f"\nEditing tags for '{pool.name}'")
            print(f"Current: {', '.join(pool.tags) if pool.tags else 'None'}")
            tags_input = input("New tags (comma-separated, or press Enter to clear): ").strip()
            pool.tags = (
                [tag.strip() for tag in tags_input.split(",") if tag.strip()] if tags_input else []
            )
            print("[SUCCESS] Tags updated")

        elif choice == "6":
            break

        else:
            print("[ERROR] Invalid option. Please choose 1-6.")


def delete_pool(pool_manager):
    """Delete a pool."""
    # Filter to show only custom pools for deletion
    custom_pools = {
        name: pool
        for name, pool in pool_manager.get_all_pools().items()
        if pool.created_by == "user"
    }

    if not custom_pools:
        print("[INFO] No custom pools available to delete.")
        return

    print(f"\n" + "=" * 50)
    print("DELETE POOL")
    print("=" * 50)
    print("Custom pools available for deletion:")

    pool_list = []
    idx = 1
    for name, pool in sorted(custom_pools.items()):
        pool_list.append((name, pool))
        print(
            f"  {idx:>2}. 👤 {name:<20} | {pool.role:<8} | {pool.size():>2} champs | {pool.description}"
        )
        idx += 1

    try:
        choice = input(f"\nChoose pool to delete (1-{len(pool_list)} or 'cancel'): ").strip()

        if choice.lower() == "cancel":
            return

        choice_num = int(choice)
        if 1 <= choice_num <= len(pool_list):
            selected_name, selected_pool = pool_list[choice_num - 1]

            # Show pool details before confirmation
            print(f"\nAbout to delete:")
            print(f"  Pool: {selected_name}")
            print(f"  Champions: {', '.join(selected_pool.champions)}")

            confirm = (
                input(f"\nAre you sure you want to delete '{selected_name}'? (y/N): ")
                .strip()
                .lower()
            )
            if confirm == "y":
                if pool_manager.delete_pool(selected_name):
                    print(f"[SUCCESS] Deleted pool '{selected_name}'")
                else:
                    print(f"[ERROR] Failed to delete pool '{selected_name}'")
        else:
            print(f"[ERROR] Invalid choice. Please choose 1-{len(pool_list)}.")

    except ValueError:
        print("[ERROR] Invalid input. Please enter a number.")


def duplicate_pool(pool_manager):
    """Duplicate an existing pool."""
    source_pool = _select_pool_interactive(pool_manager, "Duplicate pool")
    if not source_pool:
        return

    print(f"\nDuplicating pool '{source_pool.name}'")
    new_name = input("Enter new pool name: ").strip()

    if not new_name:
        print("[ERROR] New pool name cannot be empty.")
        return

    if pool_manager.duplicate_pool(source_pool.name, new_name):
        print(f"[SUCCESS] Duplicated '{source_pool.name}' as '{new_name}'")

        # Show the new pool info
        new_pool = pool_manager.get_pool(new_name)
        if new_pool:
            print(
                f"New pool created with {new_pool.size()} champions: {', '.join(new_pool.champions)}"
            )
    else:
        print("[ERROR] Failed to duplicate pool (name may already exist)")
