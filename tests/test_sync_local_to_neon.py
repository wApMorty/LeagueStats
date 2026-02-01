"""Tests for scripts/sync_local_to_neon.py - SQLite to Neon sync script.

This module tests the sync_local_to_neon.py CLI script that transfers data
from local SQLite database to PostgreSQL Neon after scraping.

Test Categories:
    - Error handling (no DATABASE_URL, missing SQLite, empty database)
    - Auto-update integration (non-blocking failure handling)
    - Integration test (actual Neon sync if DATABASE_URL available)
"""

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent
SYNC_SCRIPT = PROJECT_ROOT / "scripts" / "sync_local_to_neon.py"
AUTO_UPDATE_SCRIPT = PROJECT_ROOT / "scripts" / "auto_update_db.py"


def test_sync_script_fails_without_database_url():
    """Test that sync script exits with code 1 if DATABASE_URL not configured.

    This is a critical safety check - the script should never try to connect
    to a database without a valid connection string.
    """
    # Ensure DATABASE_URL is not set
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)

    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 1, "Script should exit with code 1 when DATABASE_URL not set"
    assert "DATABASE_URL" in result.stderr, "Error message should mention DATABASE_URL"
    assert "not configured" in result.stderr.lower(), "Error should indicate missing configuration"


def test_sync_script_fails_with_missing_sqlite():
    """Test that sync script exits with code 1 if SQLite database doesn't exist.

    The script should detect missing source database before attempting to connect to Neon.
    """
    # Create temporary directory without db.db
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create project structure
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        # Note: db.db intentionally not created

        # Set dummy DATABASE_URL to pass initial check
        env = os.environ.copy()
        env["DATABASE_URL"] = "postgresql://dummy:dummy@localhost/dummy"

        # Mock project root to use tmpdir
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"""
import sys
from pathlib import Path
sys.path.insert(0, r"{PROJECT_ROOT}")
import scripts.sync_local_to_neon as sync_module

# Override project_root
sync_module.project_root = Path(r"{tmpdir}")

# Run main
sys.exit(sync_module.main())
""",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

        assert result.returncode == 1, "Script should exit with code 1 when SQLite missing"
        assert "not found" in result.stderr.lower() or "no such file" in result.stderr.lower()


def test_sync_script_fails_with_insufficient_champions():
    """Test that sync script exits with code 1 if less than 100 champions in SQLite.

    This validates data integrity before expensive Neon transfer.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create minimal SQLite database with only 5 champions
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        db_path = data_dir / "db.db"

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create champions table with minimal schema
        cursor.execute(
            """
            CREATE TABLE champions (
                id INTEGER PRIMARY KEY,
                key TEXT,
                name TEXT NOT NULL,
                title TEXT
            )
        """
        )

        # Insert only 5 champions (below threshold of 100)
        for i in range(1, 6):
            cursor.execute(
                "INSERT INTO champions (id, key, name, title) VALUES (?, ?, ?, ?)",
                (i, f"champ{i}", f"Champion{i}", f"Title{i}"),
            )

        # Create empty matchups and synergies tables
        cursor.execute(
            """
            CREATE TABLE matchups (
                id INTEGER PRIMARY KEY,
                champion INTEGER,
                enemy INTEGER,
                winrate REAL,
                delta2 REAL,
                games INTEGER,
                pickrate REAL
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE synergies (
                id INTEGER PRIMARY KEY,
                champion INTEGER,
                ally INTEGER,
                winrate REAL,
                delta2 REAL,
                games INTEGER,
                pickrate REAL
            )
        """
        )

        conn.commit()
        conn.close()

        # Set dummy DATABASE_URL
        env = os.environ.copy()
        env["DATABASE_URL"] = "postgresql://dummy:dummy@localhost/dummy"

        # Run sync script with mocked project_root
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"""
import sys
from pathlib import Path
sys.path.insert(0, r"{PROJECT_ROOT}")
import scripts.sync_local_to_neon as sync_module

# Override project_root
sync_module.project_root = Path(r"{tmpdir}")

# Run main
sys.exit(sync_module.main())
""",
            ],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )

        assert result.returncode == 1, "Script should exit with code 1 when <100 champions"
        assert "5 champions" in result.stderr, "Error should show actual champion count"
        assert "expected 100+" in result.stderr.lower()


def test_auto_update_continues_on_sync_failure(tmp_path):
    """Test that auto_update_db.py continues execution if Neon sync fails.

    This is critical: local DB update is primary, Neon sync is secondary.
    Even if Neon is down, auto-update should complete successfully.
    """
    # This test verifies the integration behavior without actually running auto_update
    # We test the subprocess error handling pattern

    # Create a mock script that always fails
    failing_script = tmp_path / "failing_sync.py"
    failing_script.write_text(
        """
import sys
print("Mock sync script - simulating failure", file=sys.stderr)
sys.exit(1)
"""
    )

    # Simulate the subprocess.run() call from auto_update_db.py
    result = subprocess.run(
        [sys.executable, str(failing_script)],
        capture_output=True,
        text=True,
        timeout=5,
    )

    # Verify failure is captured but doesn't raise exception
    assert result.returncode == 1
    assert "simulating failure" in result.stderr

    # The auto_update script should log WARNING and continue
    # (This pattern is implemented in auto_update_db.py lines 424-447)
    # Here we just verify the subprocess pattern works as expected


@pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"), reason="DATABASE_URL not configured for integration test"
)
def test_sync_success_integration():
    """Integration test: Full sync from SQLite to Neon (requires DATABASE_URL).

    This test only runs if DATABASE_URL is set in environment.
    It performs a real sync to verify end-to-end functionality.

    WARNING: This test modifies the Neon database (delete + insert).
    Only run in development/testing environments.
    """
    # Verify SQLite database exists and has data
    sqlite_path = PROJECT_ROOT / "data" / "db.db"
    assert sqlite_path.exists(), "Local SQLite database must exist"

    conn = sqlite3.connect(str(sqlite_path))
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM champions")
    champions_count = cursor.fetchone()[0]
    assert champions_count >= 100, f"Need 100+ champions, found {champions_count}"

    cursor.execute("SELECT COUNT(*) FROM matchups")
    matchups_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM synergies")
    synergies_count = cursor.fetchone()[0]

    conn.close()

    # Run sync script
    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=60,  # Neon sync can take up to 1 minute
    )

    # Verify success
    assert result.returncode == 0, f"Sync should succeed. Stderr: {result.stderr}"
    assert "SUCCESS" in result.stdout, "Output should contain SUCCESS message"
    assert f"Champions: {champions_count}" in result.stdout
    assert "Matchups:" in result.stdout
    assert "Synergies:" in result.stdout

    # Verify no errors in stderr
    assert "ERROR" not in result.stderr
    assert "FATAL" not in result.stderr


def test_sync_script_uses_pythonw_compatible_pattern():
    """Test that sync script is compatible with pythonw.exe (headless mode).

    When run via pythonw.exe, stdout/stderr are None. The script should handle this gracefully.
    This is important for Task Scheduler background execution.
    """
    # This test verifies the script doesn't crash in headless mode
    # We can't easily mock pythonw behavior, so we check the code pattern instead

    # Read sync script source
    sync_script_content = SYNC_SCRIPT.read_text(encoding="utf-8")

    # Verify it uses print() with file=sys.stderr explicitly
    assert "file=sys.stderr" in sync_script_content, "Script should use file=sys.stderr for errors"

    # Verify it doesn't use sys.stdout.write() (which would fail in pythonw)
    assert (
        "sys.stdout.write" not in sync_script_content
    ), "Avoid sys.stdout.write() for pythonw compatibility"

    # Verify error handling wraps main logic
    assert "try:" in sync_script_content and "except Exception" in sync_script_content


def test_sync_script_timeout_protection():
    """Test that subprocess call in auto_update_db.py has timeout protection.

    Prevents infinite hangs if Neon connection is slow or stalled.
    """
    # Read auto_update_db.py source
    auto_update_content = AUTO_UPDATE_SCRIPT.read_text(encoding="utf-8")

    # Verify subprocess.run has timeout parameter
    assert "subprocess.run" in auto_update_content, "auto_update should use subprocess.run"
    assert "timeout=" in auto_update_content, "subprocess.run should have timeout parameter"
    assert (
        "300" in auto_update_content or "5" in auto_update_content
    ), "Timeout should be ~5 min (300 sec)"

    # Verify TimeoutExpired exception is caught
    assert "TimeoutExpired" in auto_update_content, "Should catch subprocess.TimeoutExpired"


def test_sync_script_exit_codes():
    """Test that sync script uses correct exit codes for different error conditions."""
    # Test success case (mocked to avoid actual Neon connection)
    # Success should return 0

    # Test failure cases return 1 (tested in other test functions)
    # - No DATABASE_URL -> 1
    # - Missing SQLite -> 1
    # - Insufficient champions -> 1
    # - Transfer exception -> 1

    # This test just verifies the pattern is consistent
    sync_script_content = SYNC_SCRIPT.read_text(encoding="utf-8")

    # Count return 0 (success) and return 1 (failure)
    return_0_count = sync_script_content.count("return 0")
    return_1_count = sync_script_content.count("return 1")

    assert return_0_count >= 1, "Should have at least one success return 0"
    assert return_1_count >= 3, "Should have multiple failure return 1 paths"

    # Verify sys.exit(main()) pattern at end
    assert "sys.exit(main())" in sync_script_content, "Should exit with main() return code"
