"""Pytest configuration and shared fixtures for LeagueStats Coach tests."""

import pytest
import sqlite3
from pathlib import Path

from src.db import Database
from src.analysis.scoring import ChampionScorer


@pytest.fixture
def temp_db(tmp_path):
    """
    Create a temporary test database with minimal schema.

    Args:
        tmp_path: pytest temporary directory fixture

    Returns:
        Path to temporary database file
    """
    db_path = tmp_path / "test_leaguestats.db"

    # Create minimal database schema
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Champions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS champions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            role TEXT
        )
    """)

    # Matchups table - using production schema column names
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matchups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            enemy INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            patch TEXT,
            FOREIGN KEY (champion) REFERENCES champions(id),
            FOREIGN KEY (enemy) REFERENCES champions(id)
        )
    """)

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def db(temp_db):
    """
    Create and return a connected Database instance with temporary database.

    Args:
        temp_db: Temporary database path fixture

    Returns:
        Connected Database instance
    """
    database = Database(str(temp_db))
    database.connect()
    yield database
    database.close()


@pytest.fixture
def scorer(db):
    """
    Create ChampionScorer instance with test database.

    Args:
        db: Database fixture

    Returns:
        ChampionScorer instance
    """
    return ChampionScorer(db, verbose=False)


@pytest.fixture
def sample_matchups():
    """
    Return sample matchup data for testing.

    Format: (enemy_name, winrate, delta1, delta2, pickrate, games)
    """
    return [
        ("Darius", 48.5, -150, -200, 8.5, 1500),
        ("Garen", 52.0, 100, 150, 12.3, 2000),
        ("Teemo", 45.0, -300, -400, 5.2, 800),
        ("Malphite", 55.5, 250, 300, 10.1, 1800),
        ("Sett", 50.0, 0, 50, 7.8, 1200),
    ]


@pytest.fixture
def sample_champions(db):
    """
    Insert sample champions into test database.

    Args:
        db: Database fixture

    Returns:
        List of inserted champion names
    """
    champions = ["Aatrox", "Darius", "Garen", "Teemo", "Malphite", "Sett"]

    cursor = db.connection.cursor()
    for champ in champions:
        cursor.execute(
            "INSERT OR IGNORE INTO champions (name, role) VALUES (?, ?)",
            (champ, "top")
        )
    db.connection.commit()

    return champions


@pytest.fixture
def insert_matchup(db):
    """
    Helper function to insert matchup data using champion names.

    Args:
        db: Database fixture

    Returns:
        Function that accepts (champion, enemy, winrate, delta1, delta2, pickrate, games)
    """
    def _insert(champion, enemy, winrate, delta1, delta2, pickrate, games):
        """Insert matchup using champion names, creating champions if needed."""
        cursor = db.connection.cursor()

        # Ensure both champions exist in champions table
        for champ_name in [champion, enemy]:
            cursor.execute("INSERT OR IGNORE INTO champions (name) VALUES (?)", (champ_name,))

        # Get champion IDs
        cursor.execute("SELECT id FROM champions WHERE name = ?", (champion,))
        champion_id = cursor.fetchone()[0]

        cursor.execute("SELECT id FROM champions WHERE name = ?", (enemy,))
        enemy_id = cursor.fetchone()[0]

        # Insert matchup - using production schema column names (champion, enemy)
        cursor.execute("""
            INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (champion_id, enemy_id, winrate, delta1, delta2, pickrate, games))

        db.connection.commit()

    return _insert
