"""
Regression tests for multi-lane matchup data aggregation.

Bug Context:
- Issue: "Multiple rows were found when one or none was required"
- Cause: Lolalytics provides multi-lane data (multiple rows per matchup)
- Solution: Aggregate using weighted average by games: SUM(delta2 * games) / SUM(games)

Test Strategy:
- Test with single-lane data (normal behavior)
- Test with multi-lane data (aggregation behavior)
- Test edge cases (zero games, no data)
"""

import pytest
import sqlite3

from src.db import Database


@pytest.fixture
def db_with_multilane_matchups(tmp_path):
    """
    Create test database with multi-lane matchup data.

    Returns:
        Database instance with test data
    """
    db_path = tmp_path / "test_multilane.db"

    # Create schema
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE champions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            role TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE matchups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            enemy INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            FOREIGN KEY (champion) REFERENCES champions (id),
            FOREIGN KEY (enemy) REFERENCES champions (id)
        )
        """
    )

    # Insert test champions
    cursor.execute("INSERT INTO champions (name, role) VALUES ('Ahri', 'Mid')")
    cursor.execute("INSERT INTO champions (name, role) VALUES ('Zed', 'Mid')")
    cursor.execute("INSERT INTO champions (name, role) VALUES ('Yasuo', 'Mid')")

    # Ahri vs Zed: Multi-lane data (2 rows)
    # Lane 1: delta2=5.0, games=300
    # Lane 2: delta2=3.0, games=200
    # Expected weighted average: (5.0*300 + 3.0*200) / (300+200) = 2100/500 = 4.2
    cursor.execute(
        """
        INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games)
        VALUES (1, 2, 52.5, 2.5, 5.0, 1.2, 300)
        """
    )
    cursor.execute(
        """
        INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games)
        VALUES (1, 2, 51.0, 1.0, 3.0, 0.8, 200)
        """
    )

    # Ahri vs Yasuo: Single-lane data (1 row)
    # Expected: delta2=2.5 directly
    cursor.execute(
        """
        INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games)
        VALUES (1, 3, 48.0, -2.0, 2.5, 1.5, 300)
        """
    )

    # Zed vs Ahri: Multi-lane data with different weights
    # Lane 1: delta2=-3.0, games=400
    # Lane 2: delta2=-5.0, games=200
    # Expected weighted average: (-3.0*400 + -5.0*200) / (400+200) = -2200/600 = -3.666...
    cursor.execute(
        """
        INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games)
        VALUES (2, 1, 47.5, -2.5, -3.0, 1.2, 400)
        """
    )
    cursor.execute(
        """
        INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games)
        VALUES (2, 1, 46.0, -4.0, -5.0, 0.8, 200)
        """
    )

    conn.commit()
    conn.close()

    # Create Database instance and connect
    db = Database(str(db_path))
    db.connect()
    return db


def test_single_lane_matchup_returns_direct_delta2(db_with_multilane_matchups):
    """Test that single-lane matchup returns delta2 directly (no aggregation needed)."""
    # Ahri vs Yasuo: Single row with delta2=2.5
    result = db_with_multilane_matchups.get_matchup_delta2("Ahri", "Yasuo")

    assert result is not None
    assert result == pytest.approx(2.5, abs=0.01)


def test_multilane_matchup_returns_weighted_average(db_with_multilane_matchups):
    """Test that multi-lane matchup returns weighted average by games."""
    # Ahri vs Zed: Multi-lane data
    # Lane 1: delta2=5.0, games=300
    # Lane 2: delta2=3.0, games=200
    # Expected: (5.0*300 + 3.0*200) / (300+200) = 4.2
    result = db_with_multilane_matchups.get_matchup_delta2("Ahri", "Zed")

    assert result is not None
    expected_weighted_avg = (5.0 * 300 + 3.0 * 200) / (300 + 200)
    assert result == pytest.approx(expected_weighted_avg, abs=0.01)


def test_multilane_matchup_with_negative_delta2(db_with_multilane_matchups):
    """Test multi-lane aggregation with negative delta2 values."""
    # Zed vs Ahri: Multi-lane data with negative delta2
    # Lane 1: delta2=-3.0, games=400
    # Lane 2: delta2=-5.0, games=200
    # Expected: (-3.0*400 + -5.0*200) / (400+200) = -3.666...
    result = db_with_multilane_matchups.get_matchup_delta2("Zed", "Ahri")

    assert result is not None
    expected_weighted_avg = (-3.0 * 400 + -5.0 * 200) / (400 + 200)
    assert result == pytest.approx(expected_weighted_avg, abs=0.01)


def test_nonexistent_matchup_returns_none(db_with_multilane_matchups):
    """Test that nonexistent matchup returns None."""
    result = db_with_multilane_matchups.get_matchup_delta2("Ahri", "Nonexistent")

    assert result is None


def test_case_insensitive_champion_names(db_with_multilane_matchups):
    """Test that champion name lookup is case-insensitive."""
    # Test with different case variations
    result_lower = db_with_multilane_matchups.get_matchup_delta2("ahri", "yasuo")
    result_upper = db_with_multilane_matchups.get_matchup_delta2("AHRI", "YASUO")
    result_mixed = db_with_multilane_matchups.get_matchup_delta2("AhRi", "YaSuO")

    assert result_lower is not None
    assert result_upper is not None
    assert result_mixed is not None
    assert result_lower == pytest.approx(result_upper, abs=0.01)
    assert result_lower == pytest.approx(result_mixed, abs=0.01)


def test_matchup_respects_quality_thresholds(tmp_path):
    """Test that matchup aggregation respects pickrate and games thresholds."""
    db_path = tmp_path / "test_thresholds.db"

    # Create schema
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE champions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            role TEXT
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE matchups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            enemy INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            FOREIGN KEY (champion) REFERENCES champions (id),
            FOREIGN KEY (enemy) REFERENCES champions (id)
        )
        """
    )

    cursor.execute("INSERT INTO champions (name, role) VALUES ('ChampA', 'Top')")
    cursor.execute("INSERT INTO champions (name, role) VALUES ('ChampB', 'Top')")

    # Insert matchup with insufficient data (pickrate < 0.5 OR games < 200)
    cursor.execute(
        """
        INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games)
        VALUES (1, 2, 50.0, 0.0, 3.0, 0.3, 100)
        """
    )

    conn.commit()
    conn.close()

    # Create Database instance and connect
    db = Database(str(db_path))
    db.connect()

    # Should return None because data doesn't meet quality thresholds
    result = db.get_matchup_delta2("ChampA", "ChampB")
    assert result is None


def test_multilane_weighted_average_calculation_manual():
    """
    Manual verification of weighted average calculation.

    This test documents the expected behavior with explicit math.
    """
    # Test data
    lane1_delta2 = 5.0
    lane1_games = 100
    lane2_delta2 = 3.0
    lane2_games = 50

    # Manual calculation
    numerator = lane1_delta2 * lane1_games + lane2_delta2 * lane2_games
    denominator = lane1_games + lane2_games
    expected = numerator / denominator

    # Expected: (5.0*100 + 3.0*50) / (100+50) = 650/150 = 4.333...
    assert expected == pytest.approx(4.333, abs=0.01)
