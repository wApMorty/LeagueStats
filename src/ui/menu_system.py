"""Main menu system and application banner."""


def print_banner() -> None:
    """Print application banner."""
    banner = """
==================================================================
                      LEAGUE OF LEGENDS COACH

  Complete toolkit for champion analysis and draft assistance
  - Real-time draft monitoring
  - Champion data management
  - Statistical analysis and tier lists
==================================================================
"""
    print(banner)


def print_main_menu() -> str:
    """
    Print the main menu options and get user choice.

    Returns:
        User's menu choice as string
    """
    menu = """
MAIN MENU:
  1. Real-time Draft Coach     - Monitor champion select and get live recommendations
  2. Update Champion Data      - Fetch latest champions from Riot API
  3. Parse Match Statistics    - Scrape matchup data (SoloQ Pool or All Champions)
  4. Analysis & Tournament     - Statistical analysis and manual tournament coaching
  5. Optimal Team Builder      - Find best champion combinations
  6. Manage Champion Pools     - Create, edit, and manage custom champion pools
  7. Exit

Choose an option (1-7): """
    return input(menu).strip()


def print_requirements() -> None:
    """Print system requirements for real-time draft coach."""
    print("\nREQUIREMENTS:")
    print("- League Client must be running")
    print("- You must be in champion select")
    print()
