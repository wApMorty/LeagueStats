#!/usr/bin/env python3
"""
League of Legends Coach - Unified Application Entry Point
Multi-purpose tool for champion analysis, draft coaching, and data management

This is the refactored entry point that delegates to modular UI components.
"""

import sys
import os
import argparse

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# Import refactored UI modules
from src.ui.menu_system import print_banner, print_main_menu, print_requirements
from src.ui.draft_coach_ui import run_draft_coach
from src.ui.champion_data_ui import update_champion_data

# Import legacy functions not yet refactored
from src.ui.lol_coach_legacy import (
    check_dependencies,
    check_database,
    parse_match_statistics,
    run_champion_analysis,
    run_optimal_team_builder,
    manage_champion_pools
)


def main():
    """Main application entry point with unified menu."""
    parser = argparse.ArgumentParser(
        description="League of Legends Coach - Complete toolkit for champion analysis and draft assistance"
    )
    parser.add_argument(
        "--no-banner",
        action="store_true",
        help="Skip banner display"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )
    parser.add_argument(
        "--direct-coach",
        action="store_true",
        help="Skip menu and go directly to draft coach (legacy mode)"
    )
    parser.add_argument(
        "--auto-hover",
        action="store_true",
        help="Enable automatic champion hovering in draft coach"
    )
    parser.add_argument(
        "--auto-accept-queue",
        action="store_true",
        help="Enable automatic queue acceptance when matchmaking finds a game"
    )
    parser.add_argument(
        "--auto-ban-hover",
        action="store_true",
        help="Enable automatic ban hovering during ban phases"
    )
    parser.add_argument(
        "--open-onetricks",
        action="store_true",
        help="Open champion page on Onetricks.gg when draft completes"
    )
    parser.add_argument(
        "--no-onetricks",
        action="store_true",
        help="Disable opening champion page on Onetricks.gg (overrides config default)"
    )

    args = parser.parse_args()

    # Legacy direct coach mode
    if args.direct_coach:
        if not args.no_banner:
            print_banner()
            print_requirements()

        # Check dependencies and database
        if not check_dependencies() or not check_database():
            sys.exit(1)

        # Determine open_onetricks setting from command line args
        if args.no_onetricks:
            open_onetricks = False
        elif args.open_onetricks:
            open_onetricks = True
        else:
            open_onetricks = None  # Use config default

        run_draft_coach(
            args.verbose,
            auto_hover=args.auto_hover,
            auto_accept_queue=args.auto_accept_queue,
            auto_ban_hover=args.auto_ban_hover,
            open_onetricks=open_onetricks
        )
        return

    # Main menu mode
    while True:
        if not args.no_banner:
            print_banner()
            args.no_banner = True  # Only show banner once

        try:
            choice = print_main_menu()

            if choice == "1":
                # Real-time Draft Coach
                if not check_dependencies() or not check_database():
                    input("\nPress Enter to return to menu...")
                    continue

                # Ask about auto-features
                hover_choice = input("\nEnable automatic champion hovering? (y/N): ").strip().lower()
                auto_hover = hover_choice == 'y'

                accept_choice = input("Enable automatic queue acceptance? (y/N): ").strip().lower()
                auto_accept_queue = accept_choice == 'y'

                ban_hover_choice = input("Enable automatic ban hovering? (y/N): ").strip().lower()
                auto_ban_hover = ban_hover_choice == 'y'

                onetricks_choice = input("Open champion page on Onetricks.gg when draft completes? (Y/n): ").strip().lower()
                open_onetricks = onetricks_choice != 'n'  # Default to True unless explicitly 'n'

                run_draft_coach(
                    args.verbose,
                    auto_hover=auto_hover,
                    auto_accept_queue=auto_accept_queue,
                    auto_ban_hover=auto_ban_hover,
                    open_onetricks=open_onetricks
                )

            elif choice == "2":
                # Update Champion Data
                update_champion_data()
                input("\nPress Enter to return to menu...")

            elif choice == "3":
                # Parse Match Statistics
                parse_match_statistics()
                input("\nPress Enter to return to menu...")

            elif choice == "4":
                # Analysis & Tournament
                if not check_database():
                    input("\nPress Enter to return to menu...")
                    continue
                run_champion_analysis()
                input("\nPress Enter to return to menu...")

            elif choice == "5":
                # Optimal Team Builder
                if not check_database():
                    input("\nPress Enter to return to menu...")
                    continue
                run_optimal_team_builder()
                input("\nPress Enter to return to menu...")

            elif choice == "6":
                # Manage Champion Pools
                manage_champion_pools()
                input("\nPress Enter to return to menu...")

            elif choice == "7":
                # Exit
                print("\nGoodbye!")
                break

            else:
                print("\n[ERROR] Invalid option. Please choose 1-7.")
                input("Press Enter to continue...")

        except KeyboardInterrupt:
            print("\n\nGoodbye!")
            break
        except Exception as e:
            print(f"\n[ERROR] Unexpected error: {e}")
            if args.verbose:
                import traceback
                traceback.print_exc()
            input("Press Enter to return to menu...")


if __name__ == "__main__":
    main()
