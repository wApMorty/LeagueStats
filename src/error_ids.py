"""
Error ID System for LeagueStats Coach.

Provides unique error identifiers for Sentry tracking and log filtering.
Each error has:
- Unique ID (ERR_XXX_NNN format)
- Category (COOKIE, DB, SCRAPING, etc.)
- Severity (CRITICAL, ERROR, WARNING)
- Description

Usage:
    from src.error_ids import ERR_COOKIE_001

    try:
        # risky operation
    except Exception as e:
        ERR_COOKIE_001.log(logger, "Cookie banner failed", exc_info=e)

Author: @pj35 - LeagueStats Coach
Version: 1.1.0-dev
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional
import logging


class ErrorCategory(Enum):
    """Error categories for classification and filtering."""
    COOKIE = "COOKIE"
    DATABASE = "DB"
    SCRAPING = "SCRAPING"
    LOGGING = "LOGGING"
    PARSER = "PARSER"
    NETWORK = "NETWORK"


class ErrorSeverity(Enum):
    """Error severity levels matching Python logging."""
    CRITICAL = "CRITICAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


@dataclass(frozen=True)
class ErrorID:
    """
    Immutable error identifier with metadata.

    Attributes:
        code: Unique error code (e.g., "ERR_COOKIE_001")
        category: Error category for filtering
        severity: Severity level
        description: Human-readable description

    Example:
        ERR_COOKIE_001 = ErrorID(
            "ERR_COOKIE_001",
            ErrorCategory.COOKIE,
            ErrorSeverity.ERROR,
            "Cookie banner ID selector failed"
        )
    """
    code: str
    category: ErrorCategory
    severity: ErrorSeverity
    description: str

    def log(
        self,
        logger: logging.Logger,
        message: str,
        exc_info: Optional[Exception] = None
    ) -> None:
        """
        Log error with ID prefix for tracking.

        Args:
            logger: Logger instance to use
            message: Error message
            exc_info: Optional exception for traceback

        Example:
            ERR_COOKIE_001.log(logger, "Failed to find button", exc_info=e)
            # Output: [ERR_COOKIE_001] Failed to find button
        """
        formatted_msg = f"[{self.code}] {message}"
        log_level = getattr(logging, self.severity.value)
        logger.log(log_level, formatted_msg, exc_info=exc_info)


# =============================================================================
# Cookie Banner Errors (ERR_COOKIE_XXX)
# =============================================================================

ERR_COOKIE_001 = ErrorID(
    "ERR_COOKIE_001",
    ErrorCategory.COOKIE,
    ErrorSeverity.ERROR,
    "Cookie banner ID selector failed with unexpected error"
)

ERR_COOKIE_002 = ErrorID(
    "ERR_COOKIE_002",
    ErrorCategory.COOKIE,
    ErrorSeverity.ERROR,
    "Cookie banner CSS selector failed with unexpected error"
)

ERR_COOKIE_003 = ErrorID(
    "ERR_COOKIE_003",
    ErrorCategory.COOKIE,
    ErrorSeverity.ERROR,
    "Cookie banner XPath selector failed with unexpected error"
)

ERR_COOKIE_004 = ErrorID(
    "ERR_COOKIE_004",
    ErrorCategory.COOKIE,
    ErrorSeverity.WARNING,
    "Cookie button found but not interactable"
)

ERR_COOKIE_005 = ErrorID(
    "ERR_COOKIE_005",
    ErrorCategory.COOKIE,
    ErrorSeverity.CRITICAL,
    "Page load failed after cookie banner handling (headless mode)"
)

ERR_COOKIE_006 = ErrorID(
    "ERR_COOKIE_006",
    ErrorCategory.COOKIE,
    ErrorSeverity.ERROR,
    "Coordinate-based cookie click failed (GUI mode)"
)


# =============================================================================
# Logging Errors (ERR_LOG_XXX)
# =============================================================================

ERR_LOG_001 = ErrorID(
    "ERR_LOG_001",
    ErrorCategory.LOGGING,
    ErrorSeverity.CRITICAL,
    "Log file write test failed"
)

ERR_LOG_002 = ErrorID(
    "ERR_LOG_002",
    ErrorCategory.LOGGING,
    ErrorSeverity.CRITICAL,
    "Unable to write to log file in headless mode (pythonw.exe)"
)


# =============================================================================
# Parser Errors (ERR_PARSER_XXX)
# =============================================================================

ERR_PARSER_001 = ErrorID(
    "ERR_PARSER_001",
    ErrorCategory.PARSER,
    ErrorSeverity.ERROR,
    "WebDriver operation failed"
)


# =============================================================================
# Database Errors (ERR_DB_XXX)
# =============================================================================

ERR_DB_001 = ErrorID(
    "ERR_DB_001",
    ErrorCategory.DATABASE,
    ErrorSeverity.ERROR,
    "Database connection failed"
)

ERR_DB_002 = ErrorID(
    "ERR_DB_002",
    ErrorCategory.DATABASE,
    ErrorSeverity.ERROR,
    "Database query failed"
)


# =============================================================================
# Scraping Errors (ERR_SCRAPING_XXX)
# =============================================================================

ERR_SCRAPING_001 = ErrorID(
    "ERR_SCRAPING_001",
    ErrorCategory.SCRAPING,
    ErrorSeverity.ERROR,
    "Champion data scraping failed"
)

ERR_SCRAPING_002 = ErrorID(
    "ERR_SCRAPING_002",
    ErrorCategory.SCRAPING,
    ErrorSeverity.WARNING,
    "Partial scraping failure (some champions failed)"
)
