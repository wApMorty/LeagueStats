"""Migration b52d1e7c9a40 (SPEC-52 tâche 258) : rank_snapshots.puuid et rattachement de l'historique."""

import json
import sqlite3

import pytest
from alembic import command
from alembic.config import Config

SOLO, FLEX = "RANKED_SOLO_5x5", "RANKED_FLEX_SR"


@pytest.fixture(autouse=True)
def _no_alembic_logging_reconfig(monkeypatch):
    """Voir tests/test_migration_unique_lane.py : fileConfig() d'alembic/env.py
    désactiverait les loggers déjà créés dans le processus pytest."""
    monkeypatch.setattr("logging.config.fileConfig", lambda *a, **k: None)


def _game(game_id, puuid, participant_id=3):
    raw = {
        "participantIdentities": [
            {"participantId": 1, "player": {"puuid": "someone-else"}},
            {"participantId": participant_id, "player": {"puuid": puuid}},
        ]
    }
    return (game_id, 420, "2026-11-07 10:00:00", participant_id, json.dumps(raw), "2026-11-07")


def _migrate(tmp_path, games, photos):
    """Base à la révision a3f6c1d8b7e2 avec `games` et `photos`, puis montée à b52d1e7c9a40."""
    db_path = tmp_path / "mig.db"
    sqlite3.connect(str(db_path)).close()
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(cfg, "13cbeb46785a")
    command.upgrade(cfg, "5c19a7e2d4b1")  # crée game_records et rank_snapshots
    command.stamp(cfg, "a3f6c1d8b7e2")
    conn = sqlite3.connect(str(db_path))
    conn.executemany(
        "INSERT INTO game_records (game_id, queue_id, game_creation_utc, player_participant_id, "
        "raw_game, captured_utc) VALUES (?, ?, ?, ?, ?, ?)",
        games,
    )
    conn.executemany(
        "INSERT INTO rank_snapshots (captured_utc, queue, tier, lp, wins, losses, game_id) "
        "VALUES (?, ?, 'GOLD', 10, ?, ?, ?)",
        photos,
    )
    conn.commit()
    conn.close()
    command.upgrade(cfg, "b52d1e7c9a40")
    return cfg, db_path


def _puuids(db_path):
    conn = sqlite3.connect(str(db_path))
    rows = [row[0] for row in conn.execute("SELECT puuid FROM rank_snapshots ORDER BY id")]
    conn.close()
    return rows


def test_upgrade_then_downgrade(tmp_path):
    cfg, db_path = _migrate(tmp_path, [], [])
    conn = sqlite3.connect(str(db_path))
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    conn.close()
    assert "idx_rank_snapshots_puuid" in names

    command.downgrade(cfg, "a3f6c1d8b7e2")
    conn = sqlite3.connect(str(db_path))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(rank_snapshots)")}
    names = {row[0] for row in conn.execute("SELECT name FROM sqlite_master")}
    conn.close()
    assert "puuid" not in columns and "idx_rank_snapshots_puuid" not in names


def test_linked_photo_takes_the_account_of_its_game(tmp_path):
    _, db_path = _migrate(
        tmp_path,
        [_game(1, "main"), _game(2, "smurf", participant_id=7)],
        [("2026-11-03 10:00:00", SOLO, 450, 459, 1), ("2026-11-07 10:00:00", SOLO, 18, 17, 2)],
    )
    assert _puuids(db_path) == ["main", "smurf"]


def test_startup_photo_takes_the_account_with_the_nearest_game_count(tmp_path):
    _, db_path = _migrate(
        tmp_path,
        [_game(1, "main"), _game(2, "smurf")],
        [
            ("2026-11-03 10:00:00", SOLO, 450, 459, 1),
            ("2026-11-07 10:00:00", SOLO, 18, 17, 2),
            ("2026-11-07 09:00:00", SOLO, 17, 15, None),  # 3 parties du total du smurf
            ("2026-11-04 09:00:00", SOLO, 451, 460, None),
        ],
    )
    assert _puuids(db_path)[2:] == ["smurf", "main"]


def test_ambiguous_startup_photo_stays_without_account(tmp_path):
    _, db_path = _migrate(
        tmp_path,
        [_game(1, "main"), _game(2, "smurf")],
        [
            ("2026-11-03 10:00:00", SOLO, 20, 20, 1),
            ("2026-11-07 10:00:00", SOLO, 22, 22, 2),
            ("2026-11-07 09:00:00", SOLO, 21, 21, None),
        ],
    )
    assert _puuids(db_path)[2] is None


def test_flex_photo_follows_its_startup_pair_and_a_lone_one_stays_null(tmp_path):
    _, db_path = _migrate(
        tmp_path,
        [_game(2, "smurf")],
        [
            ("2026-11-07 10:00:00", SOLO, 18, 17, 2),
            ("2026-11-07 09:00:00", SOLO, 17, 17, None),
            ("2026-11-07 09:00:01", FLEX, 3, 1, None),  # paire à 1 s
            ("2026-11-07 15:00:00", FLEX, 3, 1, None),  # isolée
        ],
    )
    assert _puuids(db_path)[1:] == ["smurf", "smurf", None]
