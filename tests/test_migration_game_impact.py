"""Migration c8f3a1d95e26 (SPEC-20 phase 3) : game_impact, montée puis descente, et
lectures et écritures du dépôt de coaching."""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from src.repositories.coaching import CoachingRepository


@pytest.fixture(autouse=True)
def _no_alembic_logging_reconfig(monkeypatch):
    """Voir tests/test_migration_unique_lane.py."""
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
    command.stamp(cfg, "a4d2e9c7b813")

    command.upgrade(cfg, "c8f3a1d95e26")
    assert {"game_impact", "idx_game_impact_game"} <= _tables(db_path)

    command.downgrade(cfg, "a4d2e9c7b813")
    assert not {"game_impact", "idx_game_impact_game"} & _tables(db_path)


def _record(db, game_id, timeline):
    db.insert_game_record(
        game_id=game_id,
        queue_id=420,
        game_creation_utc=f"2026-10-01 00:00:{game_id:02d}",
        duration_s=1800,
        player_participant_id=1,
        raw_game="{}",
        raw_timeline=timeline,
        raw_eog=None,
    )


def test_save_replaces_and_reads_back_in_event_order(db):
    repo = CoachingRepository(db)
    row = lambda pid, t, d: {
        "participant_id": pid,
        "event_time_ms": t,
        "event_type": "kill",
        "delta_p": d,
    }
    repo.save_impact(1, "wp-aaa", [row(2, 9000, 0.05), row(1, 4000, -0.03)])
    repo.save_impact(1, "wp-bbb", [row(1, 4000, -0.04)])  # remplace, ne cumule pas
    rows = repo.impact_rows(1)
    assert [(r["participant_id"], r["delta_p"], r["model_version"]) for r in rows] == [
        (1, -0.04, "wp-bbb")
    ]
    repo.save_impact(2, "wp-bbb", [row(1, 8000, 0.1), row(1, 2000, 0.2), row(3, 2000, 0.3)])
    assert [r["event_time_ms"] for r in repo.impact_rows(2, participant_id=1)] == [2000, 8000]


def test_games_without_impact_skips_done_and_timeline_less(db):
    repo = CoachingRepository(db)
    _record(db, 1, "{}")
    _record(db, 2, "{}")
    _record(db, 3, None)  # pas de timeline : rien à calculer
    repo.save_impact(
        1,
        "wp-aaa",
        [{"participant_id": 1, "event_time_ms": 0, "event_type": "kill", "delta_p": 0.0}],
    )
    assert [g["game_id"] for g in repo.games_without_impact()] == [2]
