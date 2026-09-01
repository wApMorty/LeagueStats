"""Startup checks (dependencies, database presence).

Extracted from src/ui/lol_coach_legacy.py (SPEC-07 E9).
"""

import os

from src.config import config


def check_dependencies():
    """Check if required dependencies are available."""
    missing_deps = []

    try:
        import requests
    except ImportError:
        missing_deps.append("requests")

    try:
        import psutil
    except ImportError:
        missing_deps.append("psutil")

    if missing_deps:
        print("[ERROR] MISSING DEPENDENCIES:")
        for dep in missing_deps:
            print(f"  - {dep}")
        print(f"\nInstall with: pip install {' '.join(missing_deps)}")
        return False

    return True


def check_database():
    """Check if database file exists."""
    db_path = config.DATABASE_PATH
    if not os.path.exists(db_path):
        print("[ERROR] DATABASE NOT FOUND:")
        print(f"  - Missing: {db_path}")
        print("  - Run data parsing first: python main.py")
        return False

    return True
