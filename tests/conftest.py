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

    # Matchups table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS matchups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion_id INTEGER NOT NULL,
            enemy_id INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            patch TEXT,
            FOREIGN KEY (champion_id) REFERENCES champions(id),
            FOREIGN KEY (enemy_id) REFERENCES champions(id)
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
