"""Test script for synchronous Database wrapper class.

This script verifies that the Database class in server/src/db.py
works correctly with the async PostgreSQL database.
"""

import sys
from pathlib import Path

# Add server directory to path
server_dir = Path(__file__).parent
sys.path.insert(0, str(server_dir))

from src.db import Database


def test_database_wrapper():
    """Test all Database wrapper methods."""
    print("=" * 60)
    print("Testing Database Wrapper Class")
    print("=" * 60)

    # Initialize database
    db = Database()
    print("[OK] Database wrapper initialized\n")

    # Test 1: Get all champions
    print("Test 1: get_all_champions()")
    print("-" * 60)
    try:
        champions = db.get_all_champions()
        print(f"[OK] Found {len(champions)} champions")
        if champions:
            print(f"     First champion: {champions[0]}")
            print(f"     Last champion: {champions[-1]}")
    except Exception as e:
        print(f"[ERROR] {e}")
    print()

    # Test 2: Get champion ID by name
    print("Test 2: get_champion_id('Aatrox')")
    print("-" * 60)
    try:
        champ_id = db.get_champion_id("Aatrox")
        if champ_id:
            print(f"[OK] Aatrox ID: {champ_id}")
        else:
            print("[ERROR] Aatrox not found")
    except Exception as e:
        print(f"[ERROR] {e}")
    print()

    # Test 3: Get champion name by ID
    print("Test 3: get_champion_name(1)")
    print("-" * 60)
    try:
        champ_name = db.get_champion_name(1)
        if champ_name:
            print(f"[OK] Champion ID 1: {champ_name}")
        else:
            print("[ERROR] Champion ID 1 not found")
    except Exception as e:
        print(f"[ERROR] {e}")
    print()

    # Test 4: Get champion matchups by name
    print("Test 4: get_champion_matchups_by_name('Aatrox')")
    print("-" * 60)
    try:
        matchups = db.get_champion_matchups_by_name("Aatrox")
        print(f"[OK] Found {len(matchups)} matchups for Aatrox")
        if matchups:
            print(f"     First matchup: {matchups[0]}")
    except Exception as e:
        print(f"[ERROR] {e}")
    print()

    # Test 5: Get champion synergies by name
    print("Test 5: get_champion_synergies_by_name('Aatrox')")
    print("-" * 60)
    try:
        synergies = db.get_champion_synergies_by_name("Aatrox")
        print(f"[OK] Found {len(synergies)} synergies for Aatrox")
        if synergies:
            print(f"     First synergy: {synergies[0]}")
    except Exception as e:
        print(f"[ERROR] {e}")
    print()

    # Test 6: Get matchup delta2
    print("Test 6: get_matchup_delta2('Aatrox', 'Darius')")
    print("-" * 60)
    try:
        delta2 = db.get_matchup_delta2("Aatrox", "Darius")
        if delta2 is not None:
            print(f"[OK] Aatrox vs Darius delta2: {delta2}")
        else:
            print("[WARN] Matchup not found (might not have sufficient data)")
    except Exception as e:
        print(f"[ERROR] {e}")
    print()

    # Test 7: Get synergy delta2
    print("Test 7: get_synergy_delta2('Aatrox', 'Yasuo')")
    print("-" * 60)
    try:
        delta2 = db.get_synergy_delta2("Aatrox", "Yasuo")
        if delta2 is not None:
            print(f"[OK] Aatrox + Yasuo synergy delta2: {delta2}")
        else:
            print("[WARN] Synergy not found (might not have sufficient data)")
    except Exception as e:
        print(f"[ERROR] {e}")
    print()

    # Test 8: Champion scores table (should return False)
    print("Test 8: champion_scores_table_exists()")
    print("-" * 60)
    try:
        exists = db.champion_scores_table_exists()
        print(f"[OK] champion_scores_table_exists() returned: {exists}")
        print("     (Expected False - server doesn't use this table)")
    except Exception as e:
        print(f"[ERROR] {e}")
    print()

    print("=" * 60)
    print("Database Wrapper Tests Complete")
    print("=" * 60)


if __name__ == "__main__":
    test_database_wrapper()
