"""Migration 5c19a7e2d4b1 (SPEC-19 phase 1) : game_records et rank_snapshots,
montée puis descente, et unicité d'une photo de classement par partie."""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config


@pytest.fixture(autouse=True)
def _no_alembic_logging_reconfig(monkeypatch):
    """Voir tests/test_migration_unique_lane.py : fileConfig() d'alembic/env.py
    désactiverait les loggers déjà créés dans le processus pytest."""
    monkeypatch.setattr("logging.config.fileConfig", lambda *a, **k: None)


def _tables(db_path):
    conn = sqlite3.connect(str(db_path))
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    conn.close()
    return names


def test_upgrade_then_downgrade(tmp_path):
    db_path = tmp_path / "mig.db"
    sqlite3.connect(str(db_path)).close()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(cfg, "13cbeb46785a")

    command.upgrade(cfg, "5c19a7e2d4b1")
    assert {"game_records", "rank_snapshots", "idx_rank_snapshots_game_id"} <= _tables(db_path)

    conn = sqlite3.connect(str(db_path))
    insert = (
        "INSERT INTO rank_snapshots (captured_utc, queue, tier, lp, game_id) "
        "VALUES ('2026-09-29 00:00:00', 'RANKED_SOLO_5x5', 'DIAMOND', 38, ?)"
    )
    conn.execute(insert, (None,))
    conn.execute(insert, (None,))  # photos de démarrage : sans limite
    conn.execute(insert, (7998195590,))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(insert, (7998195590,))
    conn.commit()
    conn.close()

    command.downgrade(cfg, "13cbeb46785a")
    assert not {"game_records", "rank_snapshots"} & _tables(db_path)
