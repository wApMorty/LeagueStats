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

# Set process priority to BELOW_NORMAL to avoid blocking PC
try:
    import psutil
    p = psutil.Process(os.getpid())
    if sys.platform == 'win32':
        p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
    else:
        p.nice(10)  # Unix: lower priority (0=normal, 19=lowest)
    print("[PRIORITY] Process priority set to BELOW_NORMAL (background execution)")
except ImportError:
    print("[WARNING] psutil not available, running at normal priority")
except Exception as e:
    print(f"[WARNING] Could not set process priority: {e}")

from src.db import Database
from src.parallel_parser import ParallelParser
from src.assistant import Assistant
from src.config import config
from src.constants import SOLOQ_POOL


class AutoUpdateLogger:
    """Simple logger for auto-update operations."""

    def __init__(self, log_dir: str = "logs"):
        """Initialize logger with log directory."""
        self.log_dir = Path(project_root) / log_dir
        self.log_dir.mkdir(exist_ok=True)
        self.log_file = self.log_dir / "auto_update.log"

    def log(self, level: str, message: str) -> None:
        """
        Log a message with timestamp.

        Args:
            level: Log level (INFO, SUCCESS, WARNING, ERROR, FATAL)
            message: Message to log
        """
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {level}: {message}"

        # Print to console
        print(log_entry)

        # Write to file
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(log_entry + '\n')
        except Exception as e:
            print(f"[ERROR] Could not write to log file: {e}")


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
        Send Windows toast notification.

        Args:
            title: Notification title
            message: Notification message
            duration: Duration in seconds (default: 10)
        """
        if not self.enabled or self.toaster is None:
            print(f"[NOTIFICATION] {title}: {message}")
            return

        try:
            self.toaster.show_toast(
                title,
                message,
                duration=duration,
                threaded=True,
                icon_path=None
            )
        except Exception as e:
            print(f"[WARNING] Could not send notification: {e}")
            print(f"[NOTIFICATION] {title}: {message}")


class PatchVersionDetector:
    """Detect current patch version from LoLalytics."""

    def __init__(self, db: Database):
        """
        Initialize detector.

        Args:
            db: Database instance
        """
        self.db = db
        self.cache_file = Path(project_root) / "data" / "last_patch.json"

    def get_current_patch(self) -> str:
        """
        Get current patch from LoLalytics by scraping a single champion.

        Returns:
            Current patch version (e.g., "15.1")
        """
        # For now, use config.CURRENT_PATCH ("14" = 14 derniers jours)
        # In future, could scrape LoLalytics to detect actual patch number
        return config.CURRENT_PATCH

    def get_last_known_patch(self) -> Optional[str]:
        """
        Get last known patch from cache file.

        Returns:
            Last known patch version or None if not cached
        """
        if not self.cache_file.exists():
            return None

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('patch')
        except Exception as e:
            print(f"[WARNING] Could not read patch cache: {e}")
            return None

    def save_patch(self, patch: str) -> None:
        """
        Save patch version to cache file.

        Args:
            patch: Patch version to save
        """
        try:
            self.cache_file.parent.mkdir(exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'patch': patch,
                    'updated_at': datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"[WARNING] Could not save patch cache: {e}")

    def is_new_patch(self) -> Tuple[bool, str, Optional[str]]:
        """
        Check if there's a new patch available.

        Returns:
            (is_new, current_patch, last_patch)
        """
        current = self.get_current_patch()
        last = self.get_last_known_patch()

        # If using "14" (rolling window), always update
        if current == "14":
            return (True, current, last)

        # Otherwise, check if patch changed
        is_new = (last is None) or (current != last)
        return (is_new, current, last)


def main() -> int:
    """
    Main auto-update function.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    logger = AutoUpdateLogger()
    notifier = WindowsNotifier(enabled=True)

    logger.log("INFO", "="*80)
    logger.log("INFO", "LeagueStats Coach - Auto-Update Database")
    logger.log("INFO", "="*80)
    logger.log("START", "Auto-update process started")

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

        # 2. Check for new patch
        logger.log("INFO", "Checking for new patch version...")
        detector = PatchVersionDetector(db)
        is_new, current_patch, last_patch = detector.is_new_patch()

        if last_patch:
            logger.log("INFO", f"Last known patch: {last_patch}")
        logger.log("INFO", f"Current patch: {current_patch}")

        if not is_new and current_patch != "14":
            logger.log("SKIP", "No new patch detected, skipping update")
            notifier.notify(
                "LeagueStats Coach",
                f"No update needed (patch {current_patch})"
            )
            return 0

        if current_patch == "14":
            logger.log("INFO", "Using rolling 14-day window (always update)")
        else:
            logger.log("SUCCESS", f"New patch detected: {last_patch} → {current_patch}")

        # 3. Send start notification
        notifier.notify(
            "LeagueStats Coach",
            f"Mise à jour démarrée (patch {current_patch})..."
        )

        # 4. Initialize parallel parser
        logger.log("INFO", f"Initializing ParallelParser (10 workers)...")
        parser = ParallelParser(db, max_workers=10, patch_version=current_patch)
        logger.log("SUCCESS", "ParallelParser initialized")

        # 5. Parse SOLOQ_POOL champions (faster, ~5-10 min with parallel)
        champion_count = len(SOLOQ_POOL)
        logger.log("INFO", f"Starting parallel scraping of {champion_count} champions...")
        logger.log("INFO", "Estimated time: ~12 minutes (background process)")

        start_time = datetime.now()
        success_count, failed_count, duration = parser.parse_all_champions()
        end_time = datetime.now()

        duration_min = duration / 60
        logger.log("SUCCESS", f"Scraping completed in {duration_min:.1f} minutes")
        logger.log("INFO", f"Champions parsed: {success_count}/{champion_count} succeeded, {failed_count} failed")

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

        # 8. Save patch version to cache
        detector.save_patch(current_patch)
        logger.log("SUCCESS", f"Patch version saved: {current_patch}")

        # 9. Success notification
        total_time = (end_time - start_time).total_seconds() / 60
        logger.log("SUCCESS", f"Auto-update completed successfully in {total_time:.1f} minutes")
        notifier.notify(
            "LeagueStats Coach ✅",
            f"BD mise à jour avec succès!\n{success_count} champions parsés ({duration_min:.1f} min)",
            duration=15
        )

        logger.log("INFO", "="*80)
        return 0

    except Exception as e:
        # Error handling
        error_msg = str(e)
        logger.log("FATAL", f"Auto-update failed: {error_msg}")
        logger.log("FATAL", traceback.format_exc())

        notifier.notify(
            "LeagueStats Coach ❌",
            f"Échec mise à jour BD:\n{error_msg}",
            duration=20
        )

        logger.log("INFO", "="*80)
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


if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
