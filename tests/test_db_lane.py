"""Tests for the lane column and db_meta table (Horizon 1, migration b7e41c9a3f02).

Covers:
- Lane tagging in add_matchups_batch / add_synergies_batch
- NULL lane for legacy (untagged) inserts
- Lane-aware composite indexes created by init tables
- db_meta set/get round-trip and graceful degradation without the table
"""

import sqlite3

import pytest

from src.db import Database


@pytest.fixture
def full_db(tmp_path):
    """Database with production schema created via Database init methods."""
    db_path = tmp_path / "lane_test.db"
    database = Database(str(db_path))
    database.connect()

    cursor = database.connection.cursor()
    cursor.execute(
        """CREATE TABLE champions (
            id INTEGER PRIMARY KEY,
            key TEXT,
            name TEXT NOT NULL,
            title TEXT
        )"""
    )
    for champ_id, name in [(1, "Aatrox"), (2, "Darius"), (3, "Garen")]:
        cursor.execute("INSERT INTO champions (id, name) VALUES (?, ?)", (champ_id, name))
    database.connection.commit()

    database.init_matchups_table()
    database.init_synergies_table()
    cursor.execute(
        """CREATE TABLE db_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )"""
    )
    database.connection.commit()

    yield database
    database.close()


class TestLaneColumn:
    """Lane tagging on matchups and synergies."""

    def test_matchups_batch_tags_lane(self, full_db):
        inserted = full_db.add_matchups_batch(
            [("Aatrox", "Darius", 51.0, 1.0, 2.0, 5.0, 1000)], lane="top"
        )
        assert inserted == 1

        cursor = full_db.connection.cursor()
        cursor.execute("SELECT lane FROM matchups")
        assert cursor.fetchone()[0] == "top"

    def test_matchups_batch_without_lane_is_null(self, full_db):
        full_db.add_matchups_batch([("Aatrox", "Darius", 51.0, 1.0, 2.0, 5.0, 1000)])

        cursor = full_db.connection.cursor()
        cursor.execute("SELECT lane FROM matchups")
        assert cursor.fetchone()[0] is None

    def test_same_matchup_on_two_lanes_is_distinguishable(self, full_db):
        """The exact regression from AUDIT_2026_06: multi-lane rows must be distinguishable."""
        row = ("Aatrox", "Darius", 51.0, 1.0, 2.0, 5.0, 1000)
        full_db.add_matchups_batch([row], lane="top")
        full_db.add_matchups_batch([row], lane="middle")

        cursor = full_db.connection.cursor()
        cursor.execute("SELECT lane FROM matchups ORDER BY lane")
        lanes = [r[0] for r in cursor.fetchall()]
        assert lanes == ["middle", "top"]

    def test_synergies_batch_tags_lane(self, full_db):
        full_db.add_synergies_batch([("Aatrox", "Garen", 52.0, 1.0, 1.5, 4.0, 800)], lane="support")

        cursor = full_db.connection.cursor()
        cursor.execute("SELECT lane FROM synergies")
        assert cursor.fetchone()[0] == "support"

    def test_lane_indexes_created(self, full_db):
        cursor = full_db.connection.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}

        assert "idx_matchups_champion_lane_pickrate" in indexes
        assert "idx_matchups_enemy_lane_pickrate" in indexes
        assert "idx_synergies_champion_lane_pickrate" in indexes
        assert "idx_synergies_ally_lane_pickrate" in indexes


class TestDbMeta:
    """db_meta key/value store for freshness monitoring."""

    def test_set_and_get_roundtrip(self, full_db):
        full_db.set_meta("last_update_utc", "2026-06-12T03:00:00Z")
        assert full_db.get_meta("last_update_utc") == "2026-06-12T03:00:00Z"

    def test_set_overwrites_existing_key(self, full_db):
        full_db.set_meta("matchups_count", "16179")
        full_db.set_meta("matchups_count", "40753")
        assert full_db.get_meta("matchups_count") == "40753"

    def test_get_missing_key_returns_none(self, full_db):
        assert full_db.get_meta("nonexistent") is None

    def test_get_without_table_returns_none(self, tmp_path):
        """Pre-migration databases (no db_meta table) must not crash the app."""
        db_path = tmp_path / "old_schema.db"
        sqlite3.connect(str(db_path)).close()

        database = Database(str(db_path))
        database.connect()
        try:
            assert database.get_meta("last_update_utc") is None
        finally:
            database.close()


class TestAlembicMigration:
    """The migration file must chain correctly from the current head."""

    def test_migration_chain(self):
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config("alembic.ini")
        script = ScriptDirectory.from_config(config)

        head = script.get_current_head()
        assert head == "b7e41c9a3f02"

        migration = script.get_revision("b7e41c9a3f02")
        assert migration.down_revision == "cc46f5edf9b2"
