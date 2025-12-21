"""
Shared fixtures for functional tests.

These fixtures provide complete setup for end-to-end testing
of UI functionalities and non-regression testing.
"""

import pytest
import sqlite3
import os

from src.db import Database
from src.assistant import Assistant


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary database with test data."""
    # Use pytest's tmp_path for automatic cleanup
    temp_path = tmp_path / "test_functional.db"

    # Initialize database
    conn = sqlite3.connect(str(temp_path))
    cursor = conn.cursor()

    # Create schema
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS champions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            role TEXT
        )
    """)

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
            FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE,
            FOREIGN KEY (enemy) REFERENCES champions(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS champion_scores (
            id INTEGER PRIMARY KEY,
            avg_delta2 REAL,
            variance REAL,
            coverage REAL,
            peak_impact REAL,
            volatility REAL,
            target_ratio REAL,
            FOREIGN KEY (id) REFERENCES champions(id) ON DELETE CASCADE
        )
    """)

    # Insert test champions
    test_champions = [
        ('Aatrox', 'TOP'),
        ('Ahri', 'MID'),
        ('Jinx', 'ADC'),
        ('Thresh', 'SUPPORT'),
        ('Lee Sin', 'JUNGLE'),
        ('Darius', 'TOP'),
        ('Zed', 'MID'),
        ('Vayne', 'ADC'),
        ('Leona', 'SUPPORT'),
        ('Jarvan IV', 'JUNGLE'),
    ]

    for champ_name, role in test_champions:
        cursor.execute("INSERT INTO champions (name, role) VALUES (?, ?)", (champ_name, role))

    # Insert test matchups (sample data)
    # Schema: champion, enemy, winrate, delta1, delta2, pickrate, games
    # Note: pickrate is a percentage (0.5-100.0 range per config_constants.py)
    matchups_data = [
        # Aatrox matchups
        (1, 6, 52.5, 5.0, 2.5, 15.0, 1000),   # Aatrox vs Darius
        (1, 2, 48.0, 3.0, -1.0, 10.0, 800),   # Aatrox vs Ahri
        # Ahri matchups
        (2, 7, 50.0, 4.0, 1.5, 12.0, 900),    # Ahri vs Zed
        (2, 1, 52.0, -3.0, 1.0, 10.0, 800),   # Ahri vs Aatrox
        # Jinx matchups
        (3, 8, 49.5, 6.0, 1.8, 18.0, 1200),   # Jinx vs Vayne
        (3, 4, 51.0, 7.0, 2.2, 20.0, 1500),   # Jinx vs Thresh
        # Lee Sin matchups
        (5, 10, 51.5, 4.5, 2.0, 16.0, 1100),  # Lee Sin vs Jarvan
        (5, 1, 49.0, 3.5, 1.0, 14.0, 950),    # Lee Sin vs Aatrox
        # Thresh matchups
        (4, 9, 50.5, 5.5, 1.8, 19.0, 1300),   # Thresh vs Leona
        (4, 3, 49.0, 6.5, 2.1, 20.0, 1500),   # Thresh vs Jinx
    ]

    for champion, enemy, winrate, delta1, delta2, pickrate, games in matchups_data:
        cursor.execute("""
            INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (champion, enemy, winrate, delta1, delta2, pickrate, games))

    # Insert test champion scores
    # Schema uses id as primary key (foreign key to champions.id), not name
    scores_data = [
        ('Aatrox', 1.5, 2.0, 0.6, 3.5, 2.1, 0.65),
        ('Ahri', 1.2, 1.5, 0.7, 3.0, 1.6, 0.70),
        ('Jinx', 1.8, 1.8, 0.65, 3.8, 1.9, 0.68),
        ('Thresh', 0.8, 1.2, 0.75, 2.5, 1.3, 0.72),
        ('Lee Sin', 2.0, 2.2, 0.55, 4.0, 2.3, 0.60),
    ]

    for name, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio in scores_data:
        # Get champion ID first
        cursor.execute("SELECT id FROM champions WHERE name = ?", (name,))
        result = cursor.fetchone()
        if result:
            champ_id = result[0]
            cursor.execute("""
                INSERT INTO champion_scores (id, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (champ_id, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio))

    conn.commit()
    conn.close()

    yield str(temp_path)

    # Cleanup handled automatically by pytest's tmp_path fixture


@pytest.fixture
def db(temp_db):
    """Database instance connected to temp database."""
    database = Database(temp_db)
    try:
        database.connect()
        yield database
    finally:
        if database.connection:
            database.close()


@pytest.fixture
def assistant(db):
    """Assistant instance with test database."""
    # Assistant creates its own DB, so we need to replace it
    assistant_instance = Assistant(verbose=False)

    # Close the default DB and replace with our test DB
    assistant_instance.db.close()
    assistant_instance.db = db

    # Reinitialize components with test DB
    from src.analysis.scoring import ChampionScorer
    from src.analysis.tier_list import TierListGenerator
    from src.analysis.recommendations import RecommendationEngine
    from src.analysis.team_analysis import TeamAnalyzer

    assistant_instance.scorer = ChampionScorer(db, verbose=False)
    assistant_instance.tier_list_gen = TierListGenerator(db, assistant_instance.scorer)
    assistant_instance.recommender = RecommendationEngine(db, assistant_instance.scorer)
    assistant_instance.team_analyzer = TeamAnalyzer(db, assistant_instance.scorer)

    yield assistant_instance
    # Don't close db here, it's closed by the db fixture


@pytest.fixture
def sample_champions():
    """List of sample champion names for tests."""
    return ['Aatrox', 'Ahri', 'Jinx', 'Thresh', 'Lee Sin', 'Darius', 'Zed', 'Vayne', 'Leona', 'Jarvan IV']


@pytest.fixture
def sample_pool(sample_champions):
    """Sample champion pool for tests."""
    return {
        'name': 'Test Pool',
        'champions': sample_champions[:5],  # First 5 champions
        'description': 'Test pool for functional tests'
    }


# ====================================================================================
# UNUSED FIXTURES - Reserved for future tests (test_draft_coach.py, test_pool_management.py)
# ====================================================================================
# Uncomment when implementing corresponding test files
#
# @pytest.fixture
# def pool_manager(tmp_path):
#     """Pool manager instance for testing pool operations."""
#     temp_pools_path = tmp_path / "test_pools.json"
#     temp_pools_path.write_text('{}')
#
#     manager = PoolManager(str(temp_pools_path))
#     yield manager
#
#
# @pytest.fixture
# def sample_draft_state():
#     """Sample draft state for tournament coach tests."""
#     return {
#         'ally_team': ['Aatrox', 'Lee Sin', 'Ahri'],
#         'enemy_team': ['Darius', 'Jarvan IV', 'Zed'],
#         'banned_champions': ['Thresh', 'Leona'],
#         'champion_pool': ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Vayne']
#     }
#
#
# @pytest.fixture
# def sample_matchups_data():
#     """Sample matchups data for validation tests."""
#     return [
#         {
#             'champion': 'Aatrox',
#             'enemy': 'Darius',
#             'winrate': 52.5,
#             'delta2': 2.5,
#             'games': 1000
#         },
#         {
#             'champion': 'Ahri',
#             'enemy': 'Zed',
#             'winrate': 50.0,
#             'delta2': 1.5,
#             'games': 900
#         },
#     ]
