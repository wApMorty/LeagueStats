"""Tests for the predictions.game_id migration (SPEC-08, migration
13cbeb46785a).

Covers:
- The migration adds the column and the partial unique index.
- The unique index rejects a duplicate game_id but allows any number of
  NULL rows (manual "outcome win/loss" resolutions never set game_id).
- Downgrade drops both cleanly.

Model: tests/test_champion_lanes_table.py. Known trap (CHANGELOG.md, fix of
2026-09-04): the fixture must create every table touched by a migration
BEFORE stamping an earlier revision and upgrading through it -- here,
`predictions` must exist before stamping 3e87f22f2ec1, since this migration
only ALTERs it (it doesn't create it).
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
        # Pre-3e87f22f2ec1 schema: that migration drops and recreates this
        # table, so it must exist before upgrading through it.
        conn.execute("""
            CREATE TABLE champion_scores (
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
        # predictions must exist before stamping 3e87f22f2ec1: this
        # migration (13cbeb46785a) only ALTERs it, it doesn't create it.
        conn.execute("""
            CREATE TABLE predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_utc TEXT NOT NULL,
                ally_champions TEXT NOT NULL,
                enemy_champions TEXT NOT NULL,
                ally_lanes TEXT,
                predicted_probability REAL NOT NULL,
                model_version TEXT NOT NULL,
                outcome INTEGER
            )
        """)
        conn.commit()
        conn.close()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.stamp(cfg, "3e87f22f2ec1")
        command.upgrade(cfg, "head")

        return sqlite3.connect(str(db_path))

    def test_game_id_column_added(self, tmp_path):
        conn = self._upgrade_to_head(tmp_path / "migration.db")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(predictions)").fetchall()}
        assert "game_id" in columns
        conn.close()

    def test_unique_index_rejects_duplicate_game_id(self, tmp_path):
        conn = self._upgrade_to_head(tmp_path / "migration.db")
        conn.execute(
            "INSERT INTO predictions "
            "(created_utc, ally_champions, enemy_champions, predicted_probability, "
            "model_version, game_id) "
            "VALUES ('2026-09-05 10:00:00', '1,2,3,4,5', '6,7,8,9,10', 0.5, 'b7-v1', 111)"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO predictions "
                "(created_utc, ally_champions, enemy_champions, predicted_probability, "
                "model_version, game_id) "
                "VALUES ('2026-09-05 11:00:00', '1,2,3,4,5', '6,7,8,9,10', 0.5, 'b7-v1', 111)"
            )
        conn.close()

    def test_unique_index_allows_multiple_null_game_ids(self, tmp_path):
        """Manual 'outcome win/loss' resolutions never set game_id -- NULL
        must not be constrained (SQLite never treats NULL = NULL)."""
        conn = self._upgrade_to_head(tmp_path / "migration.db")
        for _ in range(2):
            conn.execute(
                "INSERT INTO predictions "
                "(created_utc, ally_champions, enemy_champions, predicted_probability, "
                "model_version, game_id) "
                "VALUES ('2026-09-05 10:00:00', '1,2,3,4,5', '6,7,8,9,10', 0.5, 'b7-v1', NULL)"
            )
        conn.commit()
        assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone() == (2,)
        conn.close()

    def test_downgrade_drops_column(self, tmp_path):
        db_path = tmp_path / "migration.db"
        self._upgrade_to_head(db_path).close()

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
        command.downgrade(cfg, "3e87f22f2ec1")

        conn = sqlite3.connect(str(db_path))
        columns = {row[1] for row in conn.execute("PRAGMA table_info(predictions)").fetchall()}
        assert "game_id" not in columns
        conn.close()


class TestPredictionsRepositoryGameId:
    """Database-level behavior once the column exists (uses the app's own
    connect(), not raw sqlite3 -- exercises PredictionsRepository directly)."""

    def test_update_prediction_outcome_stores_game_id(self, db):
        prediction_id = db.insert_prediction([1, 2, 3, 4, 5], [6, 7, 8, 9, 10], None, 0.5, "b7-v1")

        assert db.update_prediction_outcome(prediction_id, 1, game_id=7412339812) is True

        cursor = db.connection.cursor()
        cursor.execute("SELECT outcome, game_id FROM predictions WHERE id = ?", (prediction_id,))
        assert cursor.fetchone() == (1, 7412339812)

    def test_manual_resolution_without_game_id_stays_null(self, db):
        """Backward compatibility (SPEC-08 §2.5): the manual 'outcome
        win/loss' command still calls this without game_id."""
        prediction_id = db.insert_prediction([1], [2], None, 0.5, "b7-v1")

        assert db.update_prediction_outcome(prediction_id, 0) is True

        cursor = db.connection.cursor()
        cursor.execute("SELECT outcome, game_id FROM predictions WHERE id = ?", (prediction_id,))
        assert cursor.fetchone() == (0, None)

    def test_duplicate_game_id_is_rejected_and_returns_false(self, db):
        first_id = db.insert_prediction([1], [2], None, 0.5, "b7-v1")
        second_id = db.insert_prediction([3], [4], None, 0.5, "b7-v1")
        assert db.update_prediction_outcome(first_id, 1, game_id=999) is True

        assert db.update_prediction_outcome(second_id, 1, game_id=999) is False

        cursor = db.connection.cursor()
        cursor.execute("SELECT outcome FROM predictions WHERE id = ?", (second_id,))
        assert cursor.fetchone()[0] is None  # left untouched, not half-updated
