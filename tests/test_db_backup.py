"""Tests for src/db_backup.py — snapshot/restore around destructive pipeline
runs (SPEC-01 A5)."""

import sqlite3

from src.db_backup import backup_database, purge_old_backups, restore_database


def _make_db(path, rows):
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE matchups (id INTEGER PRIMARY KEY, value TEXT)")
    conn.executemany("INSERT INTO matchups (value) VALUES (?)", [(r,) for r in rows])
    conn.commit()
    conn.close()


def _row_values(path):
    conn = sqlite3.connect(str(path))
    values = [row[0] for row in conn.execute("SELECT value FROM matchups ORDER BY id")]
    conn.close()
    return values


class TestBackupDatabase:
    def test_backup_copies_current_data_to_sibling_file(self, tmp_path):
        db_path = tmp_path / "db.db"
        _make_db(db_path, ["Ahri", "Zed"])

        backup_path = backup_database(str(db_path))

        assert backup_path.exists()
        assert backup_path.parent == tmp_path
        assert backup_path.name.startswith("db.backup-")
        assert _row_values(backup_path) == ["Ahri", "Zed"]

    def test_backup_is_safe_with_an_open_connection_on_the_source(self, tmp_path):
        """The whole point of using sqlite3.Connection.backup() instead of
        shutil.copy: it must not corrupt/lock up on an already-open source,
        since run_pipeline() keeps its own Database connection open."""
        db_path = tmp_path / "db.db"
        _make_db(db_path, ["Ahri"])
        live_connection = sqlite3.connect(str(db_path))
        try:
            backup_path = backup_database(str(db_path))
            assert _row_values(backup_path) == ["Ahri"]
        finally:
            live_connection.close()


class TestRestoreDatabase:
    def test_restore_reverts_a_dropped_table(self, tmp_path):
        db_path = tmp_path / "db.db"
        _make_db(db_path, ["Ahri", "Zed"])
        backup_path = backup_database(str(db_path))

        # Simulate the DROP that scrape_all_multilane() does before scraping,
        # followed by a crash: the table is gone/incomplete.
        conn = sqlite3.connect(str(db_path))
        conn.execute("DROP TABLE matchups")
        conn.commit()
        conn.close()

        restore_database(backup_path, str(db_path))

        assert _row_values(db_path) == ["Ahri", "Zed"]


class TestPurgeOldBackups:
    def test_keeps_only_the_most_recent_n_backups(self, tmp_path):
        db_path = tmp_path / "db.db"
        _make_db(db_path, ["Ahri"])
        names = [
            "db.backup-20260101T000000Z.db",
            "db.backup-20260102T000000Z.db",
            "db.backup-20260103T000000Z.db",
            "db.backup-20260104T000000Z.db",
        ]
        for name in names:
            (tmp_path / name).write_bytes(b"")

        purge_old_backups(str(db_path), retention=3)

        remaining = sorted(p.name for p in tmp_path.glob("db.backup-*.db"))
        assert remaining == names[1:]

    def test_does_not_touch_unrelated_files(self, tmp_path):
        db_path = tmp_path / "db.db"
        _make_db(db_path, ["Ahri"])
        (tmp_path / "db.backup-20260101T000000Z.db").write_bytes(b"")
        (tmp_path / "notes.db").write_bytes(b"")

        purge_old_backups(str(db_path), retention=0)

        assert (tmp_path / "notes.db").exists()
        assert (tmp_path / "db.db").exists()
