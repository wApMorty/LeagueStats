"""Tests de la migration predictions.strategy (SPEC-46, migration a3f6c1d8b7e2)."""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config


@pytest.fixture(autouse=True)
def _no_alembic_logging_reconfig(monkeypatch):
    """Voir tests/test_migration_unique_lane.py : le fileConfig d'alembic/env.py désactive les
    loggers créés plus tôt dans le même processus pytest."""
    monkeypatch.setattr("logging.config.fileConfig", lambda *a, **k: None)


@pytest.fixture
def base(tmp_path):
    """Base à la révision précédente, avec une prédiction déjà écrite."""
    path = tmp_path / "migration.db"
    with sqlite3.connect(str(path)) as conn:
        conn.execute("""
            CREATE TABLE predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_utc TEXT NOT NULL,
                ally_champions TEXT NOT NULL,
                enemy_champions TEXT NOT NULL,
                ally_lanes TEXT,
                predicted_probability REAL NOT NULL,
                model_version TEXT NOT NULL,
                outcome INTEGER,
                game_id INTEGER
            )
            """)
        conn.execute(
            "INSERT INTO predictions (created_utc, ally_champions, enemy_champions, "
            "predicted_probability, model_version) "
            "VALUES ('2026-10-29 10:00:00', '1,2,3,4,5', '6,7,8,9,10', 0.5, 'spec43-v1')"
        )
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{path}")
    command.stamp(config, "e5b7d2a14c93")
    return path, config


def _columns(path):
    with sqlite3.connect(str(path)) as conn:
        return {row[1] for row in conn.execute("PRAGMA table_info(predictions)")}


def test_la_colonne_est_ajoutee_et_les_lignes_existantes_restent_nulles(base):
    path, config = base

    command.upgrade(config, "head")

    assert "strategy" in _columns(path)
    with sqlite3.connect(str(path)) as conn:
        assert conn.execute("SELECT strategy FROM predictions").fetchall() == [(None,)]


def test_le_downgrade_retire_la_colonne_et_garde_les_lignes(base):
    path, config = base
    command.upgrade(config, "head")

    command.downgrade(config, "-1")

    assert "strategy" not in _columns(path)
    with sqlite3.connect(str(path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM predictions").fetchone() == (1,)
