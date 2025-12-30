"""
Auto-Update Database Script for LeagueStats Coach.

This script automatically updates the champion matchup database by:
1. Detecting new patch versions from LoLalytics
2. Scraping champion data using parallel parser (12min execution)
3. Recalculating tier list scores
4. Sending notifications on success/failure
5. Logging all operations for debugging

REQUIREMENTS:
- Web Scraping Parallèle (Tâche #4) - COMPLETED ✅
- ParallelParser with 10 workers (12min execution time)
- Process priority set to BELOW_NORMAL (background execution)

USAGE:
- Manual: python scripts/auto_update_db.py
- Scheduled: Task Scheduler daily at 3 AM
- Background: pythonw.exe (no console window)

Author: @pj35 - LeagueStats Coach
Version: 1.1.0-dev
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import json
import traceback
from typing import Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


# Set process priority to BELOW_NORMAL to avoid blocking PC (only when run as main)
def _set_process_priority():
    """Set process priority to BELOW_NORMAL for background execution."""
    try:
        import psutil

        p = psutil.Process(os.getpid())
        if sys.platform == "win32":
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            p.nice(10)  # Unix: lower priority (0=normal, 19=lowest)
        print("[PRIORITY] Process priority set to BELOW_NORMAL (background execution)")
    except ImportError:
        print("[WARNING] psutil not available, running at normal priority")
    except Exception as e:
        print(f"[WARNING] Could not set process priority: {e}")


from src.parallel_parser import ParallelParser
from src.assistant import Assistant
from src.db import Database
from src.config import config
from src.constants import normalize_champion_name_for_url
from src.error_ids import ERR_LOG_001, ERR_LOG_002


class AutoUpdateLogger:
    """
    Simple logger for auto-update operations with write capability testing.

    Attributes:
        _write_test_failures: Class-level counter for consecutive write failures
        _max_write_failures: Maximum allowed consecutive failures before aborting
    """

    # Class-level counters for write test failures
    _write_test_failures = 0
    _max_write_failures = 3

    def __init__(self, log_dir: str = "logs"):
        """Initialize logger with log directory."""
        self.log_dir = Path(project_root) / log_dir
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "auto_update.log"

    def test_write_capability(self) -> bool:
        """
        Test if log file is writable.

        Returns:
            True if write successful, False otherwise

        Raises:
            RuntimeError: If max consecutive failures exceeded
        """
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            test_entry = f"[{timestamp}] INFO: Log write test\n"

            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(test_entry)

            # Reset counter on success
            AutoUpdateLogger._write_test_failures = 0
            return True

        except Exception as e:
            AutoUpdateLogger._write_test_failures += 1

            error_msg = (
                f"Fatal: Unable to write to log file after "
                f"{AutoUpdateLogger._max_write_failures} attempts. "
                f"Check file permissions and disk space."
            )

            if AutoUpdateLogger._write_test_failures >= AutoUpdateLogger._max_write_failures:
                # Use stderr if available, otherwise raise
                if hasattr(sys, "stderr") and sys.stderr is not None:
                    print(error_msg, file=sys.stderr)
                    print(f"Last error: {e}", file=sys.stderr)

                raise RuntimeError(error_msg) from e

            return False

    def log(self, level: str, message: str) -> None:
        """
        Log a message with timestamp.

        Args:
            level: Log level (INFO, SUCCESS, WARNING, ERROR, FATAL)
            message: Message to log

        Raises:
            RuntimeError: If max consecutive write failures exceeded during runtime
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {level}: {message}"

        # Print to console (if available)
        if hasattr(sys, "stdout") and sys.stdout is not None:
            print(log_entry)

        # Write to file
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_entry + "\n")

            # Reset counter on successful write
            AutoUpdateLogger._write_test_failures = 0

        except Exception as e:
            AutoUpdateLogger._write_test_failures += 1

            # CRITICAL: Log write failed during runtime
            error_msg = (
                f"[ERR_LOG_003] Log write failure #{AutoUpdateLogger._write_test_failures}: {e}"
            )

            # Try stderr as fallback
            if hasattr(sys, "stderr") and sys.stderr is not None:
                print(error_msg, file=sys.stderr)

            # Abort if too many consecutive failures
            if AutoUpdateLogger._write_test_failures >= AutoUpdateLogger._max_write_failures:
                fatal_msg = (
                    f"FATAL: Unable to write logs after {AutoUpdateLogger._max_write_failures} "
                    f"consecutive failures during auto-update execution. Aborting."
                )

                if hasattr(sys, "stderr") and sys.stderr is not None:
                    print(fatal_msg, file=sys.stderr)

                raise RuntimeError(fatal_msg) from e


class WindowsNotifier:
    """Windows notification system using win10toast."""

    def __init__(self, enabled: bool = True):
        """
        Initialize notifier.

        Args:
            enabled: Enable notifications (default: True)
        """
        self.enabled = enabled
        self.toaster = None

        if enabled:
            try:
                from win10toast import ToastNotifier

                self.toaster = ToastNotifier()
            except ImportError:
                print("[WARNING] win10toast not available, notifications disabled")
                self.enabled = False

    def notify(self, title: str, message: str, duration: int = 10) -> None:
        """
        Send Windows toast notification with fallback to log file.

        Args:
            title: Notification title
            message: Notification message
            duration: Duration in seconds (default: 10)
        """
        # Try console output (GUI mode)
        if not self.enabled or self.toaster is None:
            if hasattr(sys, "stdout") and sys.stdout is not None:
                print(f"[NOTIFICATION] {title}: {message}")
            # In pythonw.exe: skip print(), will fallback to log below if needed
            return

        try:
            self.toaster.show_toast(
                title, message, duration=duration, threaded=True, icon_path=None
            )
        except Exception as e:
            # Notification failed - log to file as fallback
            fallback_msg = f"NOTIFICATION FAILED - {title}: {message} (Error: {e})"

            # Try stderr first
            if hasattr(sys, "stderr") and sys.stderr is not None:
                print(f"[WARNING] {fallback_msg}", file=sys.stderr)

            # Write to notification log file (persistent fallback)
            try:
                log_dir = Path(__file__).parent.parent / "logs"
                log_dir.mkdir(exist_ok=True)
                notification_log = log_dir / "notifications.log"
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                with open(notification_log, "a", encoding="utf-8") as f:
                    f.write(f"[{timestamp}] {fallback_msg}\n")

            except Exception as log_error:
                # Both notification and log fallback failed
                # This is truly silent in pythonw.exe - nothing we can do
                pass


def main() -> int:
    """
    Main auto-update function.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    logger = AutoUpdateLogger()
    notifier = WindowsNotifier(enabled=True)

    # Configure Python logging to capture ALL logs (including parallel_parser.py)
    # This is critical for pythonw.exe where stdout/stderr don't exist
    import logging

    log_dir = Path(project_root) / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "auto_update.log"

    # Configure root logger to write to file
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Changed from DEBUG to reduce verbosity

    # Remove existing handlers to avoid duplicates
    root_logger.handlers.clear()

    # File handler for all logs
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)  # Changed from DEBUG to reduce verbosity
    file_formatter = logging.Formatter(
        "[%(asctime)s] %(name)s - %(levelname)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)

    # Reduce verbosity of external libraries (Selenium, urllib3)
    # These are extremely verbose in DEBUG mode
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Keep our modules at INFO level for useful diagnostics
    logging.getLogger("src").setLevel(logging.INFO)

    # Console handler only if stdout exists (not pythonw.exe)
    # More robust check for pythonw.exe: hasattr() prevents AttributeError
    if hasattr(sys, "stdout") and sys.stdout is not None:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)
    else:
        # Running in pythonw.exe mode (no console output)
        logger.log("WARNING", "Running in pythonw.exe mode - no console output")

        # CRITICAL: Test log write capability BEFORE proceeding
        # If we can't write logs in headless mode, we're blind
        if not logger.test_write_capability():
            # Fatal: Unable to log in headless mode
            ERR_LOG_002.log(
                logging.getLogger(__name__),
                "Unable to write to log file in pythonw.exe mode - aborting",
                exc_info=True,
            )
            sys.exit(1)

        logger.log("SUCCESS", "Log write test passed - proceeding with auto-update")

    logger.log("INFO", "=" * 80)
    logger.log("INFO", "LeagueStats Coach - Auto-Update Database")
    logger.log("INFO", "=" * 80)
    logger.log("START", "Auto-update process started")
    logger.log("INFO", f"Python logging configured - all logs will be written to {log_file}")

    db = None
    parser = None
    assistant = None

    try:
        # 1. Initialize database
        logger.log("INFO", "Initializing database...")
        db_path = config.DATABASE_PATH
        db = Database(db_path)
        db.connect()
        logger.log("SUCCESS", f"Database connected: {db_path}")

        # 2. Using rolling 14-day window (always update)
        patch_version = "14"
        logger.log("INFO", f"Using patch version: {patch_version} (rolling 14-day window)")

        # 3. Send start notification
        notifier.notify("LeagueStats Coach", f"Mise à jour démarrée (patch {patch_version})...")

        # 4. Initialize parallel parser with headless mode
        logger.log("INFO", f"Initializing ParallelParser (10 workers, headless mode)...")
        parser = ParallelParser(max_workers=10, patch_version=patch_version, headless=True)
        logger.log("SUCCESS", "ParallelParser initialized in headless mode (no GUI)")

        # 5. Parse all champions (dynamically from Riot API, ~12 min with parallel)
        logger.log("INFO", "Starting parallel scraping of champions from Riot API...")
        logger.log("INFO", "Estimated time: ~12 minutes (background process)")

        start_time = datetime.now()
        stats = parser.parse_all_champions(db, normalize_champion_name_for_url)
        end_time = datetime.now()

        success_count = stats.get("success", 0)
        failed_count = stats.get("failed", 0)
        total_count = stats.get("total", 0)
        duration = stats.get("duration", 0)

        duration_min = duration / 60
        logger.log("SUCCESS", f"Scraping completed in {duration_min:.1f} minutes")
        logger.log(
            "INFO",
            f"Champions parsed: {success_count}/{total_count} succeeded, {failed_count} failed",
        )

        # Warning if many failures (indicates headless mode issues)
        if failed_count > 0:
            failure_rate = (failed_count / total_count) * 100
            logger.log(
                "WARNING", f"Failure rate: {failure_rate:.1f}% ({failed_count} champions failed)"
            )
            if failure_rate > 50:
                logger.log(
                    "ERROR",
                    "High failure rate detected - possible headless mode compatibility issue",
                )
                logger.log("ERROR", "Check logs/auto_update.log for detailed scraping errors")

        # 6. Close parser to free resources
        parser.close()
        parser = None
        logger.log("INFO", "ParallelParser closed (Firefox drivers cleaned up)")

        # 7. Recalculate champion scores
        logger.log("INFO", "Recalculating champion scores...")
        assistant = Assistant(verbose=False)
        assistant.calculate_global_scores()
        assistant.close()
        assistant = None
        logger.log("SUCCESS", "Champion scores recalculated")

        # 8. Success notification
        total_time = (end_time - start_time).total_seconds() / 60
        logger.log("SUCCESS", f"Auto-update completed successfully in {total_time:.1f} minutes")
        notifier.notify(
            "LeagueStats Coach ✅",
            f"BD mise à jour avec succès!\n{success_count} champions parsés ({duration_min:.1f} min)",
            duration=15,
        )

        logger.log("INFO", "=" * 80)
        return 0

    except Exception as e:
        # Error handling
        error_msg = str(e)
        logger.log("FATAL", f"Auto-update failed: {error_msg}")
        logger.log("FATAL", traceback.format_exc())

        notifier.notify("LeagueStats Coach ❌", f"Échec mise à jour BD:\n{error_msg}", duration=20)

        logger.log("INFO", "=" * 80)
        return 1

    finally:
        # Cleanup resources
        if parser:
            try:
                parser.close()
                logger.log("INFO", "ParallelParser cleanup completed")
            except Exception as e:
                logger.log("WARNING", f"ParallelParser cleanup failed: {e}")

        if assistant:
            try:
                assistant.close()
                logger.log("INFO", "Assistant cleanup completed")
            except Exception as e:
                logger.log("WARNING", f"Assistant cleanup failed: {e}")

        if db:
            try:
                db.close()
                logger.log("INFO", "Database connection closed")
            except Exception as e:
                logger.log("WARNING", f"Database cleanup failed: {e}")

        # Cleanup logging handlers to avoid resource leaks
        # logging already imported at module level (line 198)
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)


if __name__ == "__main__":
    _set_process_priority()
    exit_code = main()
    sys.exit(exit_code)
