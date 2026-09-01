"""Menu 3 -- scraping / statistics parsing.

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

from src.config import config
from src.constants import TOP_SOLOQ_POOL
from src.utils.console import clear_console
from src.ui.pool_selection_ui import _select_pool_for_parsing


def _get_patch_version():
    """Ask user for patch version to analyze."""
    from src.config import config

    print(f"\nCurrent patch in config: {config.CURRENT_PATCH}")
    print("Options:")
    print("1. Use current patch from config")
    print("2. Specify different patch")
    print("3. Back to main menu")

    choice = input("\nChoose option (1-3): ").strip()

    if choice == "1":
        return config.CURRENT_PATCH
    elif choice == "2":
        patch_input = input(f"Enter patch version (e.g., {config.CURRENT_PATCH}): ").strip()
        if patch_input:
            # Validate patch format (basic validation)
            parts = patch_input.split(".")
            if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
                return patch_input
            else:
                print(f"[ERROR] Invalid patch format. Use format like {config.CURRENT_PATCH}")
                return None
        else:
            print("[ERROR] Patch version cannot be empty")
            return None
    elif choice == "3":
        return None
    else:
        print("[ERROR] Invalid option")
        return None


def parse_match_statistics():
    """Parse match statistics from web sources with submenu."""
    clear_console()  # Clear console at start
    print("[INFO] Match Statistics Parser")

    # Ask for patch version first
    patch_version = _get_patch_version()
    if not patch_version:
        return

    print(f"\n✅ Patch selected: {patch_version}")
    print("\nParsing options:")
    print("MATCHUPS:")
    print("1. Parse Matchups (SoloQ Pool)           - Fast (~1 min)")
    print("2. Parse Matchups (All Champions)        - Comprehensive (~6-8 min)")
    print("\nSYNERGIES:")
    print("3. Parse Synergies (SoloQ Pool)          - Fast (~1 min)")
    print("4. Parse Synergies (All Champions)       - Comprehensive (~6-8 min)")
    print("\nCOMPLETE:")
    print("5. Parse All Data (SoloQ Pool)           - Matchups + Synergies (~2 min)")
    print("6. Parse All Data (All Champions)        - Matchups + Synergies (~12-16 min)")
    print("\n7. Back to main menu")

    choice = input("\nChoose option (1-7): ").strip()

    if choice == "1":
        parse_champion_pool(patch_version)
    elif choice == "2":
        parse_all_champions(patch_version)
    elif choice == "3":
        parse_synergies_pool(patch_version)
    elif choice == "4":
        parse_synergies_all(patch_version)
    elif choice == "5":
        parse_all_data_pool(patch_version)
    elif choice == "6":
        parse_all_data_all(patch_version)
    elif choice == "7":
        return
    else:
        print("[ERROR] Invalid option")


def _run_pool_pipeline(
    pool_name, pool_champions, patch_version, include_matchups, include_synergies
):
    """Shared body for the four pool-scoped parse_* menu options.

    Delegates to src.pipeline.run_pipeline() (SPEC-01 A2) so the menu gets
    the same completeness gate, db_meta writes, file log and notifications
    as scripts/update_all.py, instead of a hand-rolled scrape.
    """
    from src.pipeline import run_pipeline

    result = run_pipeline(
        champions=pool_champions,
        include_matchups=include_matchups,
        include_synergies=include_synergies,
        patch=patch_version,
    )

    if result.status != "ok":
        print(f"[ERROR] Parsing error: {result.error}")
        return

    stats = result.scrape_stats
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETED")
    print("=" * 60)
    print(f"Pool: {pool_name}")
    print(f"Pages: {stats['success']}/{stats['total']} ok ({stats['failed']} échecs)")
    print(f"Duration: {result.duration_min:.1f} min")
    print("=" * 60)
    print(
        f"[SUCCESS] {pool_name} data updated! "
        f"({stats['success']} pages scraped, {result.scores_count} champions scored)"
    )


def _run_full_pipeline(label, patch_version, include_matchups, include_synergies):
    """Shared body for the two all-champions parse_* menu options."""
    from src.pipeline import run_pipeline

    result = run_pipeline(
        include_matchups=include_matchups,
        include_synergies=include_synergies,
        patch=patch_version,
    )

    if result.status != "ok":
        print(f"[ERROR] Parsing error: {result.error}")
        return

    stats = result.scrape_stats
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETED")
    print("=" * 60)
    print(f"Pages: {stats['success']}/{stats['total']} ok ({stats['failed']} échecs)")
    print(f"Duration: {result.duration_min:.1f} min")
    print("=" * 60)
    print(
        f"[SUCCESS] {label} updated! "
        f"({stats['success']} pages scraped, {result.scores_count} champions scored)"
    )


def _select_pool_or_default():
    """Pool selection shared by the pool-scoped parse_* options."""
    selected_pool_info = _select_pool_for_parsing()
    if not selected_pool_info:
        print("[WARNING] No pool selected, using default Top SoloQ pool")
        return "Top SoloQ (Default)", TOP_SOLOQ_POOL
    return selected_pool_info


def parse_champion_pool(patch_version=None):
    """Parse match statistics for selected champion pool via the shared pipeline."""
    print("[INFO] Champion Pool Statistics Parser")

    pool_name, pool_champions = _select_pool_or_default()
    print(f"\n✅ Parsing statistics for: {pool_name}")
    print(f"🔧 Patch version: {patch_version or 'default'}")
    print(f"Champions to process: {', '.join(pool_champions)}")

    confirm = (
        input(f"\nProceed with parsing {len(pool_champions)} champions? (y/N): ").strip().lower()
    )
    if confirm != "y":
        print("[INFO] Parsing cancelled.")
        return

    _run_pool_pipeline(
        pool_name, pool_champions, patch_version, include_matchups=True, include_synergies=False
    )


def parse_all_champions(patch_version=None):
    """Parse match statistics for all champions via the shared pipeline."""
    print("[INFO] Parsing ALL champions via the shared pipeline")

    confirm = input("\nAre you sure you want to continue? (y/N): ").strip().lower()
    if confirm != "y":
        print("[INFO] Cancelled by user")
        return

    _run_full_pipeline(
        "All champion statistics", patch_version, include_matchups=True, include_synergies=False
    )


def parse_synergies_pool(patch_version=None):
    """Parse synergies for selected champion pool via the shared pipeline."""
    print("[INFO] Champion Pool Synergies Parser")

    pool_name, pool_champions = _select_pool_or_default()
    print(f"\n✅ Parsing synergies for: {pool_name}")
    print(f"🔧 Patch version: {patch_version or 'default'}")
    print(f"Champions to process: {', '.join(pool_champions)}")

    confirm = (
        input(f"\nProceed with parsing synergies for {len(pool_champions)} champions? (y/N): ")
        .strip()
        .lower()
    )
    if confirm != "y":
        print("[INFO] Parsing cancelled.")
        return

    _run_pool_pipeline(
        pool_name, pool_champions, patch_version, include_matchups=False, include_synergies=True
    )


def parse_synergies_all(patch_version=None):
    """Parse synergies for all champions via the shared pipeline."""
    print("[INFO] Parsing synergies for ALL champions")

    confirm = input("\nAre you sure you want to continue? (y/N): ").strip().lower()
    if confirm != "y":
        print("[INFO] Cancelled by user")
        return

    _run_full_pipeline(
        "Synergy statistics", patch_version, include_matchups=False, include_synergies=True
    )


def parse_all_data_pool(patch_version=None):
    """Parse both matchups and synergies for selected champion pool via the shared pipeline."""
    print("[INFO] Parsing ALL data (matchups + synergies) for Champion Pool")

    pool_name, pool_champions = _select_pool_or_default()
    print(f"\n✅ Parsing complete data for: {pool_name}")
    print(f"🔧 Patch version: {patch_version or 'default'}")
    print(f"Champions to process: {', '.join(pool_champions)}")

    confirm = (
        input(
            f"\nProceed with parsing matchups + synergies for {len(pool_champions)} champions? (y/N): "
        )
        .strip()
        .lower()
    )
    if confirm != "y":
        print("[INFO] Parsing cancelled.")
        return

    _run_pool_pipeline(
        pool_name, pool_champions, patch_version, include_matchups=True, include_synergies=True
    )


def parse_all_data_all(patch_version=None):
    """Parse both matchups and synergies for all champions via the shared pipeline."""
    print("[INFO] Parsing ALL data (matchups + synergies) for ALL champions")

    confirm = input("\nAre you sure you want to continue? (y/N): ").strip().lower()
    if confirm != "y":
        print("[INFO] Cancelled by user")
        return

    _run_full_pipeline(
        "All data (matchups + synergies)",
        patch_version,
        include_matchups=True,
        include_synergies=True,
    )
