"""
Tests for Error ID System.

Validates that error IDs are:
- Immutable
- Properly categorized
- Log with correct format and severity
- Integrate with Python logging

Author: @pj35 - LeagueStats Coach
"""

import pytest
import logging
from src.error_ids import (
    ErrorID,
    ErrorCategory,
    ErrorSeverity,
    ERR_COOKIE_001,
    ERR_COOKIE_004,
    ERR_COOKIE_005,
    ERR_COOKIE_007,
    ERR_LOG_001,
    ERR_LOG_002,
    ERR_LOG_003,
)


class TestErrorIDImmutability:
    """Test that ErrorID dataclass is immutable."""

    def test_error_id_is_frozen(self):
        """Test that ErrorID instances cannot be modified."""
        assert ERR_COOKIE_001.code == "ERR_COOKIE_001"

        # Attempt to modify should raise
        with pytest.raises(AttributeError):
            ERR_COOKIE_001.code = "MODIFIED"

    def test_error_id_attributes_immutable(self):
        """Test that all ErrorID attributes are immutable."""
        with pytest.raises(AttributeError):
            ERR_COOKIE_001.category = ErrorCategory.DATABASE

        with pytest.raises(AttributeError):
            ERR_COOKIE_001.severity = ErrorSeverity.INFO


class TestErrorIDLogging:
    """Test ErrorID.log() integration with Python logging."""

    def test_error_id_logs_with_code_prefix(self, caplog):
        """Test that error code appears in log message."""
        logger = logging.getLogger("test")
        caplog.set_level(logging.ERROR)

        ERR_COOKIE_001.log(logger, "Test message")

        assert "[ERR_COOKIE_001]" in caplog.text
        assert "Test message" in caplog.text

    def test_error_id_logs_with_correct_severity(self, caplog):
        """Test that log severity matches ErrorID severity."""
        logger = logging.getLogger("test")

        # ERROR severity
        caplog.clear()
        caplog.set_level(logging.ERROR)
        ERR_COOKIE_001.log(logger, "Error message")
        assert "ERROR" in caplog.text

        # WARNING severity
        caplog.clear()
        caplog.set_level(logging.WARNING)
        ERR_COOKIE_004.log(logger, "Warning message")
        assert "WARNING" in caplog.text

        # CRITICAL severity
        caplog.clear()
        caplog.set_level(logging.CRITICAL)
        ERR_COOKIE_005.log(logger, "Critical message")
        assert "CRITICAL" in caplog.text

    def test_error_id_logs_with_exception_info(self, caplog):
        """Test that exception traceback is logged when provided."""
        logger = logging.getLogger("test")
        caplog.set_level(logging.ERROR)

        test_exception = ValueError("Test exception")

        ERR_COOKIE_001.log(logger, "Error with exception", exc_info=test_exception)

        assert "[ERR_COOKIE_001]" in caplog.text
        assert "Error with exception" in caplog.text
        # Traceback should be present
        assert "Traceback" in caplog.text or "ValueError" in caplog.text


class TestErrorIDCategories:
    """Test error categorization."""

    def test_cookie_errors_have_cookie_category(self):
        """Test that cookie errors are categorized correctly."""
        assert ERR_COOKIE_001.category == ErrorCategory.COOKIE
        assert ERR_COOKIE_004.category == ErrorCategory.COOKIE
        assert ERR_COOKIE_005.category == ErrorCategory.COOKIE

    def test_logging_errors_have_logging_category(self):
        """Test that logging errors are categorized correctly."""
        assert ERR_LOG_001.category == ErrorCategory.LOGGING
        assert ERR_LOG_002.category == ErrorCategory.LOGGING

    def test_error_codes_match_category(self):
        """Test that error codes follow naming convention."""
        # Cookie errors should start with ERR_COOKIE_
        assert ERR_COOKIE_001.code.startswith("ERR_COOKIE_")

        # Logging errors should start with ERR_LOG_
        assert ERR_LOG_001.code.startswith("ERR_LOG_")


class TestErrorIDDescriptions:
    """Test error descriptions are meaningful."""

    def test_all_errors_have_descriptions(self):
        """Test that all errors have non-empty descriptions."""
        error_ids = [
            ERR_COOKIE_001,
            ERR_COOKIE_004,
            ERR_COOKIE_005,
            ERR_LOG_001,
            ERR_LOG_002,
        ]

        for error_id in error_ids:
            assert error_id.description
            assert len(error_id.description) > 10  # Meaningful description

    def test_descriptions_are_actionable(self):
        """Test that descriptions indicate what went wrong."""
        # Cookie errors describe cookie banner issues
        assert "cookie" in ERR_COOKIE_001.description.lower()
        assert (
            "banner" in ERR_COOKIE_001.description.lower()
            or "selector" in ERR_COOKIE_001.description.lower()
        )

        # Log errors describe log file issues
        assert "log" in ERR_LOG_001.description.lower()
        assert (
            "write" in ERR_LOG_001.description.lower() or "file" in ERR_LOG_001.description.lower()
        )


class TestErrorIDUniqueness:
    """Test that error codes are unique."""

    def test_error_codes_are_unique(self):
        """Test that no two errors share the same code."""
        error_ids = [
            ERR_COOKIE_001,
            ERR_COOKIE_004,
            ERR_COOKIE_005,
            ERR_LOG_001,
            ERR_LOG_002,
        ]

        codes = [err.code for err in error_ids]
        assert len(codes) == len(set(codes)), "Duplicate error codes found"


class TestNewErrorIDs:
    """Test newly added error IDs for PR review fixes."""

    def test_error_cookie_007_exists(self):
        """Test: ERR_COOKIE_007 defined for WebDriver session loss."""
        assert ERR_COOKIE_007.code == "ERR_COOKIE_007"
        assert ERR_COOKIE_007.category == ErrorCategory.COOKIE
        assert ERR_COOKIE_007.severity == ErrorSeverity.CRITICAL
        assert "webdriver" in ERR_COOKIE_007.description.lower()
        assert "session" in ERR_COOKIE_007.description.lower()

    def test_error_log_003_exists(self):
        """Test: ERR_LOG_003 defined for runtime log write failures."""
        assert ERR_LOG_003.code == "ERR_LOG_003"
        assert ERR_LOG_003.category == ErrorCategory.LOGGING
        assert ERR_LOG_003.severity == ErrorSeverity.CRITICAL
        assert "runtime" in ERR_LOG_003.description.lower()
        assert (
            "write" in ERR_LOG_003.description.lower() or "log" in ERR_LOG_003.description.lower()
        )
