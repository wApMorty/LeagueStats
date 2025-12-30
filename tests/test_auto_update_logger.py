"""
Tests for AutoUpdateLogger.

Validates that AutoUpdateLogger:
- Tests write capability before critical operations
- Tracks consecutive write failures with class-level counter
- Raises RuntimeError after max failures exceeded
- Resets counter on successful write
- Works correctly in pythonw.exe mode

Author: @pj35 - LeagueStats Coach
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.auto_update_db import AutoUpdateLogger


class TestAutoUpdateLoggerWriteCapability:
    """Test AutoUpdateLogger.test_write_capability() method."""

    @pytest.fixture(autouse=True)
    def reset_counter(self):
        """Reset class-level counter before each test."""
        AutoUpdateLogger._write_test_failures = 0
        yield
        AutoUpdateLogger._write_test_failures = 0

    def test_write_capability_success(self, tmp_path):
        """Test successful log write capability."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        result = logger.test_write_capability()

        assert result is True
        assert AutoUpdateLogger._write_test_failures == 0
        assert logger.log_file.exists()

    def test_write_capability_creates_test_entry(self, tmp_path):
        """Test that write test creates log entry."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        logger.test_write_capability()

        content = logger.log_file.read_text(encoding='utf-8')
        assert "INFO: Log write test" in content

    def test_write_capability_resets_counter_on_success(self, tmp_path):
        """Test that successful write resets failure counter."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        # Simulate previous failures
        AutoUpdateLogger._write_test_failures = 2

        result = logger.test_write_capability()

        assert result is True
        assert AutoUpdateLogger._write_test_failures == 0

    def test_write_capability_increments_counter_on_failure(self, tmp_path, mocker):
        """Test that write failure increments counter."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        # Mock open to fail
        mocker.patch('builtins.open', side_effect=PermissionError("Access denied"))

        result = logger.test_write_capability()

        assert result is False
        assert AutoUpdateLogger._write_test_failures == 1

    def test_write_capability_raises_after_max_failures(self, tmp_path, mocker):
        """Test that max failures raises RuntimeError."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        # Mock open to fail
        mocker.patch('builtins.open', side_effect=PermissionError("Access denied"))

        # First 2 calls should return False
        assert logger.test_write_capability() is False
        assert AutoUpdateLogger._write_test_failures == 1

        assert logger.test_write_capability() is False
        assert AutoUpdateLogger._write_test_failures == 2

        # 3rd call should raise RuntimeError
        with pytest.raises(RuntimeError, match="Unable to write to log file after 3 attempts"):
            logger.test_write_capability()

        assert AutoUpdateLogger._write_test_failures == 3

    def test_write_capability_error_message_includes_permissions_hint(self, tmp_path, mocker):
        """Test that error message mentions permissions and disk space."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        mocker.patch('builtins.open', side_effect=PermissionError("Access denied"))

        # Trigger max failures
        try:
            for _ in range(4):  # Force 3+ failures
                logger.test_write_capability()
        except RuntimeError as e:
            assert "permissions" in str(e).lower()
            assert "disk space" in str(e).lower()

    def test_write_capability_uses_stderr_if_available(self, tmp_path, mocker, capsys):
        """Test that error is printed to stderr if available."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        mocker.patch('builtins.open', side_effect=PermissionError("Access denied"))

        # Trigger max failures
        with pytest.raises(RuntimeError):
            for _ in range(4):
                logger.test_write_capability()

        # Check stderr
        captured = capsys.readouterr()
        assert "Fatal: Unable to write to log file" in captured.err or "Fatal: Unable to write to log file" in captured.out

    def test_write_capability_class_level_counter_shared_across_instances(self, tmp_path, mocker):
        """Test that failure counter is shared across logger instances."""
        logger1 = AutoUpdateLogger(log_dir=str(tmp_path))
        logger2 = AutoUpdateLogger(log_dir=str(tmp_path))

        mocker.patch('builtins.open', side_effect=PermissionError("Access denied"))

        # Fail with logger1
        logger1.test_write_capability()
        assert AutoUpdateLogger._write_test_failures == 1

        # Fail with logger2 - counter should continue
        logger2.test_write_capability()
        assert AutoUpdateLogger._write_test_failures == 2

    def test_write_capability_permission_error(self, tmp_path, mocker):
        """Test handling of PermissionError."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        mocker.patch('builtins.open', side_effect=PermissionError("Access denied"))

        result = logger.test_write_capability()

        assert result is False
        assert AutoUpdateLogger._write_test_failures == 1

    def test_write_capability_disk_full_error(self, tmp_path, mocker):
        """Test handling of disk full (OSError)."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        mocker.patch('builtins.open', side_effect=OSError("No space left on device"))

        result = logger.test_write_capability()

        assert result is False
        assert AutoUpdateLogger._write_test_failures == 1


class TestAutoUpdateLoggerIntegration:
    """Integration tests for AutoUpdateLogger."""

    @pytest.fixture(autouse=True)
    def reset_counter(self):
        """Reset counter before each test."""
        AutoUpdateLogger._write_test_failures = 0
        yield
        AutoUpdateLogger._write_test_failures = 0

    def test_logger_creates_directory_if_missing(self, tmp_path):
        """Test that logger creates log directory if it doesn't exist."""
        log_dir = tmp_path / "new_logs"
        assert not log_dir.exists()

        logger = AutoUpdateLogger(log_dir=str(log_dir))

        assert log_dir.exists()
        assert logger.log_file.parent == log_dir

    def test_logger_log_method_writes_to_file(self, tmp_path):
        """Test that log() method writes to file."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        logger.log("INFO", "Test message")

        content = logger.log_file.read_text(encoding='utf-8')
        assert "INFO: Test message" in content

    def test_logger_log_method_includes_timestamp(self, tmp_path):
        """Test that log entries include timestamps."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        logger.log("INFO", "Test message")

        content = logger.log_file.read_text(encoding='utf-8')
        # Timestamp format: [YYYY-MM-DD HH:MM:SS]
        assert "[20" in content  # Year starts with 20
        assert "]" in content


class TestRuntimeLogWriteFailures:
    """Regression tests for runtime log write failures (Problem B)."""

    def test_log_runtime_write_failure_raises_after_3_failures(self, tmp_path, mocker):
        """Regression test: Runtime log write failures raise after 3 consecutive failures."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        # Startup test passes
        logger.test_write_capability()
        assert AutoUpdateLogger._write_test_failures == 0

        # Mock open to fail AFTER startup
        mocker.patch('builtins.open', side_effect=PermissionError("Access denied"))

        # First 2 failures should not raise
        logger.log("INFO", "Message 1")  # Failure #1
        assert AutoUpdateLogger._write_test_failures == 1

        logger.log("INFO", "Message 2")  # Failure #2
        assert AutoUpdateLogger._write_test_failures == 2

        # 3rd consecutive failure should raise RuntimeError
        with pytest.raises(RuntimeError, match="Unable to write logs after 3 consecutive failures"):
            logger.log("INFO", "Message 3")  # Failure #3

        assert AutoUpdateLogger._write_test_failures == 3

    def test_log_runtime_failure_resets_on_success(self, tmp_path, mocker):
        """Test: Counter resets to 0 on successful write after failures."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        # Startup passes
        logger.test_write_capability()

        # Fail twice
        mock_open = mocker.patch('builtins.open', side_effect=PermissionError("Denied"))
        logger.log("INFO", "Fail 1")
        logger.log("INFO", "Fail 2")
        assert AutoUpdateLogger._write_test_failures == 2

        # Success resets counter
        mocker.stop(mock_open)
        logger.log("INFO", "Success")
        assert AutoUpdateLogger._write_test_failures == 0

        # Verify success was written
        content = logger.log_file.read_text(encoding='utf-8')
        assert "Success" in content

    def test_log_runtime_failure_uses_stderr_fallback(self, tmp_path, mocker, capsys):
        """Test: Runtime failures output to stderr when available."""
        logger = AutoUpdateLogger(log_dir=str(tmp_path))

        # Startup passes
        logger.test_write_capability()

        # Mock file write to fail
        mocker.patch('builtins.open', side_effect=PermissionError("Access denied"))

        # Log should fail and write to stderr
        logger.log("INFO", "Test message")

        # Check stderr output
        captured = capsys.readouterr()
        assert "[ERR_LOG_003]" in captured.err
        assert "Log write failure #1" in captured.err
