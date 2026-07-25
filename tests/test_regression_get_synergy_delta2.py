"""Regression test for bug "Multiple rows" in get_synergy_delta2.

Bug Report:
-----------
Function: src/db.py::Database.get_synergy_delta2()
Error: "Multiple rows were found when one or none was required"
Cause: synergies table contains multiple rows for champion-ally pairs (multi-lane data)

This test ensures the multi-lane case never crashes and that the lookup keeps
returning None for unknown champions/allies.

Author: Python Expert (Claude Sonnet 4.5)
Created: 2026-02-13
Sprint: 2 - Tâche #16 (Support des Synergies)
Rewritten: 2026-07-25 — ported from the decommissioned server/ SQLAlchemy
           implementation to src/db.py (SQLite), against a real temp database
           instead of AsyncMock scaffolding.
"""

import sqlite3

import pytest

from src.db import Database


@pytest.fixture
def db_with_synergies(tmp_path):
    """Database with a synergies table holding multi-lane rows."""
    db_path = tmp_path / "synergies.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE champions (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)"
    )
    cursor.execute(
        """
        CREATE TABLE synergies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            ally INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            lane TEXT
        )
        """
    )
    cursor.executemany(
        "INSERT INTO champions (name) VALUES (?)", [("Yasuo",), ("Malphite",), ("Lulu",)]
    )
    # Yasuo + Malphite: three lanes -> three rows (the "Multiple rows" case)
    cursor.executemany(
        "INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games, lane)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (1, 2, 53.0, 100.0, 220.0, 5.0, 800, "middle"),
            (1, 2, 51.0, 90.0, 180.0, 4.0, 400, "top"),
            (1, 2, 52.0, 95.0, 200.0, 4.5, 600, "bottom"),
            # Yasuo + Lulu: single lane
            (1, 3, 50.0, 80.0, 150.0, 3.0, 1200, "middle"),
        ],
    )
    conn.commit()
    conn.close()

    database = Database(str(db_path))
    database.connect()
    yield database
    database.close()


class TestGetSynergyDelta2MultiLaneRegression:
    """Regression tests for get_synergy_delta2 with multi-lane data."""

    def test_multi_lane_synergy_does_not_raise(self, db_with_synergies):
        """REGRESSION: several rows for one pair must not raise "Multiple rows"."""
        result = db_with_synergies.get_synergy_delta2("Yasuo", "Malphite")

        assert result is not None
        # Current SQLite implementation returns one of the per-lane rows
        assert result in (220.0, 180.0, 200.0)

    def test_single_row_synergy(self, db_with_synergies):
        """Single-lane pair returns that row's delta2."""
        assert db_with_synergies.get_synergy_delta2("Yasuo", "Lulu") == pytest.approx(150.0)

    def test_no_synergy_data(self, db_with_synergies):
        """A known pair with no synergy row returns None."""
        assert db_with_synergies.get_synergy_delta2("Malphite", "Lulu") is None

    def test_champion_not_found(self, db_with_synergies):
        """Unknown champion returns None."""
        assert db_with_synergies.get_synergy_delta2("InvalidChampion", "Malphite") is None

    def test_ally_not_found(self, db_with_synergies):
        """Unknown ally returns None."""
        assert db_with_synergies.get_synergy_delta2("Yasuo", "InvalidAlly") is None

    @pytest.mark.xfail(
        strict=True,
        reason="src/db.py::get_synergy_delta2 uses fetchone() and picks an arbitrary "
        "lane row, while get_matchup_delta2 aggregates a games-weighted average. "
        "Divergence inherited from the decommissioned server/ implementation.",
    )
    def test_multi_lane_synergy_is_games_weighted(self, db_with_synergies):
        """Multi-lane synergies should aggregate like matchups do (weighted by games)."""
        expected = (220.0 * 800 + 180.0 * 400 + 200.0 * 600) / (800 + 400 + 600)
        assert db_with_synergies.get_synergy_delta2("Yasuo", "Malphite") == pytest.approx(
            expected, abs=0.01
        )
