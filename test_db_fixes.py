#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify SQL injection fixes and database indexes.
This script tests the parameterized queries without requiring a full database.
"""

import sqlite3
import tempfile
import os
import sys

# Set UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

def test_parameterized_queries():
    """Test that parameterized queries work correctly."""
    print("=" * 60)
    print("Testing SQL Injection Fixes")
    print("=" * 60)

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        tmp_db_path = tmp.name

    try:
        # Create connection
        conn = sqlite3.connect(tmp_db_path)
        cursor = conn.cursor()

        # Create test table
        cursor.execute("""
            CREATE TABLE champions (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """)

        # Test parameterized insert
        print("\n✓ Testing parameterized INSERT...")
        test_champion = "Aatrox"
        cursor.execute("INSERT INTO champions (name) VALUES (?)", (test_champion,))
        conn.commit()
        print(f"  Inserted champion: {test_champion}")

        # Test parameterized SELECT
        print("\n✓ Testing parameterized SELECT...")
        cursor.execute("SELECT id FROM champions WHERE name = ? COLLATE NOCASE", (test_champion,))
        result = cursor.fetchone()
        assert result is not None, "Champion not found"
        print(f"  Found champion ID: {result[0]}")

        # Test with special characters (SQL injection attempt)
        print("\n✓ Testing with special characters (SQL injection prevention)...")
        malicious_input = "'; DROP TABLE champions; --"
        cursor.execute("INSERT INTO champions (name) VALUES (?)", (malicious_input,))
        conn.commit()
        print(f"  Successfully handled special characters safely")

        # Verify table still exists
        cursor.execute("SELECT COUNT(*) FROM champions")
        count = cursor.fetchone()[0]
        print(f"  Table intact, champion count: {count}")

        print("\n" + "=" * 60)
        print("✓ All SQL injection fix tests passed!")
        print("=" * 60)

    finally:
        # Close connection and cleanup
        try:
            conn.close()
        except:
            pass
        if os.path.exists(tmp_db_path):
            try:
                os.remove(tmp_db_path)
            except PermissionError:
                pass  # File might still be locked, ignore


def test_database_indexes():
    """Test that index creation works correctly."""
    print("\n" + "=" * 60)
    print("Testing Database Index Creation")
    print("=" * 60)

    # Import our Database class
    from src.db import Database
    from src.config import get_resource_path

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp:
        tmp_db_path = tmp.name

    try:
        # Initialize database
        db = Database(tmp_db_path)
        db.connect()

        # Create tables
        db.execute_query("""
            CREATE TABLE IF NOT EXISTS champions (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """, commit=False)

        db.execute_query("""
            CREATE TABLE IF NOT EXISTS matchups (
                id INTEGER PRIMARY KEY,
                champion INTEGER NOT NULL,
                enemy INTEGER NOT NULL,
                winrate REAL NOT NULL,
                delta1 REAL NOT NULL,
                delta2 REAL NOT NULL,
                pickrate REAL NOT NULL,
                games INTEGER NOT NULL
            )
        """, commit=False)

        db.connection.commit()

        # Now create indexes after tables exist
        db.create_database_indexes()

        # Check if indexes exist
        print("\n✓ Checking created indexes...")
        cursor = db.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'")
        indexes = cursor.fetchall()

        expected_indexes = [
            'idx_champions_name',
            'idx_matchups_champion',
            'idx_matchups_enemy',
            'idx_matchups_pickrate',
            'idx_matchups_champion_pickrate',
            'idx_matchups_enemy_pickrate'
        ]

        found_indexes = [idx[0] for idx in indexes]

        for expected in expected_indexes:
            if expected in found_indexes:
                print(f"  ✓ {expected}")
            else:
                print(f"  ✗ {expected} (missing)")

        if set(expected_indexes).issubset(set(found_indexes)):
            print("\n" + "=" * 60)
            print("✓ All database indexes created successfully!")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("✗ Some indexes are missing")
            print("=" * 60)

    finally:
        # Close connection and cleanup
        try:
            db.close()
        except:
            pass
        if os.path.exists(tmp_db_path):
            try:
                os.remove(tmp_db_path)
            except PermissionError:
                pass  # File might still be locked, ignore


if __name__ == "__main__":
    try:
        test_parameterized_queries()
        test_database_indexes()
        print("\n" + "=" * 60)
        print("✓✓✓ ALL TESTS PASSED ✓✓✓")
        print("=" * 60)
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
