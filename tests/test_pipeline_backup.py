"""Integration test for SPEC-01 A5: a run that fails after the pre-scrape
backup must leave the database in exactly its pre-run state — no mocks on
src.db_backup here, unlike tests/test_pipeline.py, since the point is to
exercise the real backup -> DROP -> crash -> restore sequence end to end."""

import sqlite3
from unittest.mock import MagicMock

import src.pipeline as pipeline_module


def _seed_db(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE champions (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute(
        "CREATE TABLE matchups (id INTEGER PRIMARY KEY, champion INTEGER, enemy INTEGER, "
        "winrate REAL, delta1 REAL, delta2 REAL, pickrate REAL, games INTEGER, lane TEXT)"
    )
    conn.execute(
        "CREATE TABLE synergies (id INTEGER PRIMARY KEY, champion INTEGER, ally INTEGER, "
        "winrate REAL, delta1 REAL, delta2 REAL, pickrate REAL, games INTEGER, lane TEXT)"
    )
    conn.execute(
        "CREATE TABLE db_meta (key TEXT PRIMARY KEY, value TEXT, "
        "updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    conn.executemany(
        "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(1, 2, 50.0, 0.0, 0.0, 5.0, 1000, "top") for _ in range(50)],
    )
    conn.commit()
    conn.close()


def test_run_pipeline_failure_mid_scrape_restores_exact_pre_scrape_state(monkeypatch, tmp_path):
    """Reproduces the 2026-06-01 incident's mechanism: DROP happens, then the
    run dies before repopulating the tables. A5 must undo the DROP."""
    db_path = tmp_path / "db.db"
    _seed_db(db_path)
    monkeypatch.setattr(pipeline_module.config, "DATABASE_PATH", str(db_path))

    def _crash_after_drop(db, parser, normalize_func, **kwargs):
        # Mirrors src/multilane.py:scrape_all_multilane() — it DROPs +
        # recreates matchups/synergies before ~45 min of scraping starts.
        db.init_matchups_table()
        db.init_synergies_table()
        raise RuntimeError("network died mid-scrape")

    monkeypatch.setattr(pipeline_module, "scrape_all_multilane", _crash_after_drop)
    monkeypatch.setattr(pipeline_module, "ParallelParser", MagicMock())
    monkeypatch.setattr(pipeline_module, "Notifier", MagicMock(return_value=MagicMock()))

    conn = sqlite3.connect(str(db_path))
    matchups_before = conn.execute("SELECT COUNT(*) FROM matchups").fetchone()[0]
    conn.close()
    assert matchups_before == 50

    result = pipeline_module.run_pipeline()

    assert result.status == "failed"

    conn = sqlite3.connect(str(db_path))
    matchups_after = conn.execute("SELECT COUNT(*) FROM matchups").fetchone()[0]
    conn.close()
    assert matchups_after == matchups_before

    backups = list(tmp_path.glob("db.backup-*.db"))
    assert len(backups) == 1, "the backup taken before the DROP must survive the restore"
