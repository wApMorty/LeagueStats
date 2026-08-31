"""Tests for the champion_lanes table (SPEC-04 B4 §4.1, migration 9ed81a3f7fc2).

Covers:
- The migration creates the table with the expected schema/constraints.
- Database.save_champion_lane_distribution() writes and upserts.
- Database.get_all_champion_lane_distributions() prefers champion_lanes and
  falls back to the matchups games volume when a champion is missing.
"""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from src.db import Database


@pytest.fixture(autouse=True)
def _no_alembic_logging_reconfig(monkeypatch):
    """See tests/test_migration_unique_lane.py for why this is needed:
    alembic/env.py's fileConfig() call disables loggers created earlier in
    the same pytest process (disable_existing_loggers=True by default)."""
    monkeypatch.setattr("logging.config.fileConfig", lambda *a, **k: None)


class TestMigration:
    def _upgrade_to_head(self, db_path) -> sqlite3.Connection:
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "CREATE TABLE champions (id INTEGER PRIMARY KEY, key TEXT, name TEXT NOT NULL, title TEXT)"
        )
        conn.execute("INSERT INTO champions (id, name) VALUES (1, 'Aatrox')")
        conn.commit()
        conn.close()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.stamp(cfg, "ea9a2b4722f1")
        command.upgrade(cfg, "head")

        return sqlite3.connect(str(db_path))

    def test_table_created_with_expected_columns(self, tmp_path):
        conn = self._upgrade_to_head(tmp_path / "migration.db")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(champion_lanes)").fetchall()}
        assert columns == {"champion", "lane", "share"}
        conn.close()

    def test_primary_key_prevents_duplicate_champion_lane(self, tmp_path):
        conn = self._upgrade_to_head(tmp_path / "migration.db")
        conn.execute("INSERT INTO champion_lanes (champion, lane, share) VALUES (1, 'top', 75.1)")
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO champion_lanes (champion, lane, share) VALUES (1, 'top', 90.0)"
            )
        conn.close()

    def test_cascade_delete_from_champions(self, tmp_path):
        conn = self._upgrade_to_head(tmp_path / "migration.db")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("INSERT INTO champion_lanes (champion, lane, share) VALUES (1, 'top', 75.1)")
        conn.commit()
        conn.execute("DELETE FROM champions WHERE id = 1")
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM champion_lanes").fetchone() == (0,)
        conn.close()

    def test_downgrade_drops_table(self, tmp_path):
        db_path = tmp_path / "migration.db"
        self._upgrade_to_head(db_path).close()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.downgrade(cfg, "ea9a2b4722f1")

        conn = sqlite3.connect(str(db_path))
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        assert "champion_lanes" not in tables
        conn.close()


@pytest.fixture
def db_with_lanes(tmp_path):
    """Database with champions, matchups (for the fallback) and champion_lanes."""
    db_path = tmp_path / "lanes.db"
    database = Database(str(db_path))
    database.connect()

    cursor = database.connection.cursor()
    cursor.execute(
        "CREATE TABLE champions (id INTEGER PRIMARY KEY, key TEXT, name TEXT NOT NULL, title TEXT)"
    )
    for champ_id, name in [(1, "Aatrox"), (2, "Darius")]:
        cursor.execute("INSERT INTO champions (id, name) VALUES (?, ?)", (champ_id, name))
    database.connection.commit()

    database.init_matchups_table()
    cursor.execute("""CREATE TABLE champion_lanes (
            champion INTEGER NOT NULL,
            lane TEXT NOT NULL,
            share REAL NOT NULL,
            PRIMARY KEY (champion, lane),
            FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE
        )""")
    database.connection.commit()

    yield database
    database.close()


class TestSaveChampionLaneDistribution:
    def test_writes_full_distribution(self, db_with_lanes):
        db_with_lanes.save_champion_lane_distribution(
            1, {"top": 75.1, "jungle": 22.0, "middle": 2.4, "bottom": 0.3, "support": 0.2}
        )
        distributions = db_with_lanes.get_all_champion_lane_distributions()
        assert distributions[1] == {
            "top": 75.1,
            "jungle": 22.0,
            "middle": 2.4,
            "bottom": 0.3,
            "support": 0.2,
        }

    def test_upsert_overwrites_existing_share(self, db_with_lanes):
        db_with_lanes.save_champion_lane_distribution(1, {"top": 75.1})
        db_with_lanes.save_champion_lane_distribution(1, {"top": 80.0})
        distributions = db_with_lanes.get_all_champion_lane_distributions()
        assert distributions[1]["top"] == 80.0

    def test_empty_distribution_is_a_noop(self, db_with_lanes):
        db_with_lanes.save_champion_lane_distribution(1, {})
        assert db_with_lanes.get_all_champion_lane_distributions() == {}


class TestFallbackToMatchups:
    def test_falls_back_when_champion_lanes_empty(self, db_with_lanes):
        cursor = db_with_lanes.connection.cursor()
        cursor.executemany(
            "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane)"
            " VALUES (?, ?, 50.0, 0.0, 0.0, 1.0, ?, ?)",
            [
                (2, 1, 750, "top"),
                (2, 1, 250, "jungle"),
            ],
        )
        db_with_lanes.connection.commit()

        distributions = db_with_lanes.get_all_champion_lane_distributions()
        assert distributions[2] == {"top": 75.0, "jungle": 25.0}

    def test_default_lane_excluded_from_fallback(self, db_with_lanes):
        cursor = db_with_lanes.connection.cursor()
        cursor.execute(
            "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane)"
            " VALUES (2, 1, 50.0, 0.0, 0.0, 1.0, 500, 'default')"
        )
        db_with_lanes.connection.commit()

        assert 2 not in db_with_lanes.get_all_champion_lane_distributions()

    def test_champion_lanes_takes_priority_over_fallback(self, db_with_lanes):
        db_with_lanes.save_champion_lane_distribution(1, {"top": 90.0, "jungle": 10.0})
        cursor = db_with_lanes.connection.cursor()
        cursor.execute(
            "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane)"
            " VALUES (1, 2, 50.0, 0.0, 0.0, 1.0, 500, 'support')"
        )
        db_with_lanes.connection.commit()

        distributions = db_with_lanes.get_all_champion_lane_distributions()
        assert distributions[1] == {"top": 90.0, "jungle": 10.0}

    def test_champion_with_no_data_at_all_is_absent(self, db_with_lanes):
        assert db_with_lanes.get_all_champion_lane_distributions() == {}
