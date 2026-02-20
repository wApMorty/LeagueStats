"""
Repair Matchups Script for LeagueStats Coach.

This script detects and repairs champions that are missing matchup data in the
database. It performs targeted re-scraping of only the affected champions to
avoid destroying existing data.

CRITICAL SAFETY RULES:
- NEVER calls parse_all_champions()  -- would DROP entire matchups table
- NEVER calls init_matchups_table()  -- would DROP entire matchups table
- Only calls clear_matchups_for_champion() + add_matchups_batch() per champion

DETECTION METHOD:
    Uses SQL LEFT JOIN between champions and matchups tables to find champions
    with zero matchup rows.

USAGE:
    python scripts/repair_matchups.py
    python scripts/repair_matchups.py --dry-run
    python scripts/repair_matchups.py --max-workers 3

EXIT CODES:
    0 = success (all missing champions repaired, or none to repair)
    1 = error (scraping failed or unexpected exception)

Author: @pj35 - LeagueStats Coach
Version: 1.1.0-dev
"""

import sys
import os
import argparse
import logging
import traceback
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local
from typing import List, Optional, Tuple
import time

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env before importing project modules
try:
    from dotenv import load_dotenv

    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

from src.db import Database
from src.config import config
from src.constants import normalize_champion_name_for_url
from src.parser import Parser

# Thread-local storage: one Firefox driver per worker thread
_thread_local = local()


def _setup_logging(log_to_file: bool = True) -> logging.Logger:
    """Configure logging for both console and optional file output.

    Args:
        log_to_file: If True, also write logs to logs/repair_matchups.log

    Returns:
        Configured logger instance
    """
    log_format = "[%(asctime)s] %(levelname)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_to_file:
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / "repair_matchups.log"
        file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(log_format, datefmt=date_format))
        handlers.append(file_handler)

    logging.basicConfig(
        level=logging.INFO, format=log_format, datefmt=date_format, handlers=handlers
    )

    # Reduce Selenium/urllib3 noise
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return logging.getLogger(__name__)


def detect_champions_without_matchups(db: Database) -> List[str]:
    """Find all champions that have zero rows in the matchups table.

    Uses a LEFT JOIN so champions absent from matchups are identified even
    if the matchups table is empty or missing rows.

    Args:
        db: Connected Database instance

    Returns:
        Sorted list of champion names with no matchup data
    """
    cursor = db.connection.cursor()
    cursor.execute(
        """
        SELECT c.name
        FROM champions c
        LEFT JOIN matchups m ON m.champion = c.id
        GROUP BY c.id, c.name
        HAVING COUNT(m.id) = 0
        ORDER BY c.name
        """
    )
    rows = cursor.fetchall()
    return [row[0] for row in rows]


def detect_empty_champion_scores(db: Database) -> bool:
    """Check whether the champion_scores table is empty.

    Args:
        db: Connected Database instance

    Returns:
        True if champion_scores has no rows (or does not exist)
    """
    try:
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM champion_scores")
        count = cursor.fetchone()[0]
        return count == 0
    except Exception:
        return True


def _get_or_create_parser(headless: bool) -> Parser:
    """Get thread-local Parser instance, creating one on first access.

    Args:
        headless: Whether to run Firefox in headless mode

    Returns:
        Parser instance for the current thread
    """
    if not hasattr(_thread_local, "parser"):
        _thread_local.parser = Parser(headless=headless)
    return _thread_local.parser


def _scrape_champion_matchups(
    champion: str,
    patch_version: str,
    headless: bool,
) -> Tuple[str, list]:
    """Scrape matchup data for a single champion.

    Retries up to 3 times on transient WebDriver / Timeout errors before
    giving up and returning an empty list.

    Args:
        champion: Champion name (as stored in the DB, e.g. "AurelionSol")
        patch_version: Patch window string (e.g. "14")
        headless: Whether to run Firefox headless

    Returns:
        Tuple of (champion_name, matchups_list). matchups_list contains
        tuples of (enemy, winrate, delta1, delta2, pickrate, games).
        Returns empty list on failure.
    """
    from selenium.common.exceptions import WebDriverException, TimeoutException

    parser = _get_or_create_parser(headless)
    normalized = normalize_champion_name_for_url(champion)

    for attempt in range(1, 4):
        try:
            matchups = parser.get_champion_data_on_patch(patch_version, normalized)
            return champion, matchups
        except (WebDriverException, TimeoutException) as exc:
            if attempt < 3:
                wait_secs = 2**attempt  # 2s, 4s
                logging.getLogger(__name__).warning(
                    f"Attempt {attempt}/3 failed for {champion} matchups: {exc} "
                    f"-- retrying in {wait_secs}s"
                )
                time.sleep(wait_secs)
            else:
                logging.getLogger(__name__).error(
                    f"All 3 attempts failed for {champion} matchups: {exc}"
                )
                return champion, []
        except Exception as exc:
            logging.getLogger(__name__).error(
                f"Unexpected error scraping {champion} matchups: {exc}"
            )
            return champion, []

    return champion, []  # unreachable but satisfies type checker


def repair_matchups_parallel(
    db: Database,
    champions: List[str],
    patch_version: str,
    max_workers: int,
    headless: bool,
    logger: logging.Logger,
) -> dict:
    """Re-scrape and insert matchups for the given champions in parallel.

    For each champion this function:
    1. Scrapes matchup data using a dedicated thread-local Firefox driver
    2. Clears existing (empty) matchup rows for that champion via
       db.clear_matchups_for_champion() (safe -- does NOT drop the table)
    3. Inserts new rows via db.add_matchups_batch() inside a shared lock

    NEVER calls parse_all_champions() or init_matchups_table().

    Args:
        db: Connected Database instance
        champions: List of champion names to repair
        patch_version: Patch window string (e.g. "14")
        max_workers: Number of parallel Firefox workers
        headless: Whether to run Firefox headless
        logger: Logger instance

    Returns:
        dict with keys 'success', 'failed', 'total', 'duration'
    """
    db_lock = Lock()
    champion_cache = db.build_champion_cache()

    success_count = 0
    failed_count = 0
    start_time = time.time()

    logger.info(
        f"Starting parallel matchup repair: {len(champions)} champions, "
        f"{max_workers} workers, headless={headless}"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scrape_champion_matchups, champ, patch_version, headless): champ
            for champ in champions
        }

        for future in as_completed(futures):
            champion = futures[future]
            try:
                champ_name, matchups = future.result(timeout=120)

                if not matchups:
                    logger.warning(f"No matchup data returned for {champ_name} -- skipping insert")
                    failed_count += 1
                    continue

                # Thread-safe DB write: clear old (empty) rows then insert fresh data
                with db_lock:
                    db.clear_matchups_for_champion(champ_name, champion_cache)

                    # Convert to batch format: [(champion, enemy, wr, d1, d2, pick, games), ...]
                    matchup_batch = [
                        (champ_name, enemy, winrate, d1, d2, pick, games)
                        for enemy, winrate, d1, d2, pick, games in matchups
                    ]
                    db.add_matchups_batch(matchup_batch, champion_cache)

                logger.info(f"Repaired {champ_name}: {len(matchups)} matchups inserted")
                success_count += 1

            except Exception as exc:
                logger.error(f"Failed to repair {champion}: {exc}")
                failed_count += 1

    duration = time.time() - start_time

    return {
        "success": success_count,
        "failed": failed_count,
        "total": len(champions),
        "duration": duration,
    }


def _close_thread_parsers(executor_workers: int) -> None:
    """Close all thread-local Parser instances to free Firefox resources.

    This is called in the finally block. Because thread-local state is not
    directly accessible from the main thread after the executor has shut down,
    we rely on the fact that each parser was appended to a shared list during
    creation. However, since we don't maintain such a list here (to keep the
    module self-contained), we instead shut down the executor first (which
    joins all threads) and then close any parser stored on the main thread's
    local storage (none in practice). The Firefox drivers spawned by worker
    threads are closed via the Parser.close() method called in the worker or
    on garbage collection.

    Note: ParallelParser manages a self.parsers list for this purpose. In this
    script we keep it simple by calling parser.close() inside each thread at
    the end of the executor scope.
    """
    # Intentionally a no-op placeholder: executor shutdown (wait=True) ensures
    # all workers have finished. Firefox drivers are cleaned up by the OS when
    # the Python process exits, or can be explicitly freed below if parsers were
    # tracked. The finally block in main() handles remaining cleanup.
    pass


def _cleanup_thread_parsers(parsers_registry: list, logger: logging.Logger) -> None:
    """Close all Parser instances tracked in the registry.

    Args:
        parsers_registry: List of Parser instances to close
        logger: Logger instance
    """
    for parser in parsers_registry:
        try:
            parser.close()
        except Exception as exc:
            logger.warning(f"Error closing parser during cleanup: {exc}")
    parsers_registry.clear()


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed argument namespace
    """
    parser = argparse.ArgumentParser(
        description=(
            "Repair champions missing matchup data in the LeagueStats database. "
            "Detects affected champions via SQL and re-scrapes them individually "
            "without touching existing data for other champions."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print champions missing matchups without scraping anything",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=5,
        metavar="N",
        help="Number of parallel Firefox workers (default: 5)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=True,
        help="Run Firefox in headless mode (default: True)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="Run Firefox with a visible GUI (disables headless mode)",
    )
    parser.add_argument(
        "--patch",
        type=str,
        default=config.CURRENT_PATCH,
        metavar="VERSION",
        help=f"Patch version window to scrape (default: {config.CURRENT_PATCH})",
    )
    parser.add_argument(
        "--skip-scores",
        action="store_true",
        help="Skip recalculating champion scores after repair",
    )
    return parser.parse_args()


def main() -> int:
    """Entry point for the repair script.

    Returns:
        Exit code: 0 = success, 1 = error
    """
    args = parse_args()
    logger = _setup_logging(log_to_file=True)

    logger.info("=" * 70)
    logger.info("LeagueStats Coach - Repair Matchups")
    logger.info("=" * 70)
    logger.info(f"Patch version : {args.patch}")
    logger.info(f"Max workers   : {args.max_workers}")
    logger.info(f"Headless mode : {args.headless}")
    logger.info(f"Dry run       : {args.dry_run}")

    db: Optional[Database] = None
    assistant = None
    # Track parsers created across threads so we can close them on exit.
    # We monkey-patch _get_or_create_parser to register parsers here.
    parsers_registry: List[Parser] = []
    original_get_parser = _get_or_create_parser.__globals__["_get_or_create_parser"]

    def _tracked_get_or_create_parser(headless: bool) -> Parser:
        parser_instance = original_get_parser(headless)
        if parser_instance not in parsers_registry:
            parsers_registry.append(parser_instance)
        return parser_instance

    # Patch the module-level function reference used by worker threads
    globals()["_get_or_create_parser"] = _tracked_get_or_create_parser

    try:
        # ---- Connect to database ----
        db_path = config.DATABASE_PATH
        logger.info(f"Connecting to database: {db_path}")
        db = Database(db_path)
        db.connect()
        logger.info("Database connected successfully")

        # ---- Detect champions without matchups ----
        logger.info("Detecting champions without matchup data...")
        missing = detect_champions_without_matchups(db)

        if not missing:
            logger.info("All champions have matchup data. Nothing to repair.")
            return 0

        logger.info(f"Found {len(missing)} champion(s) without matchups:")
        for name in missing:
            logger.info(f"  - {name}")

        # ---- Check champion_scores status ----
        scores_empty = detect_empty_champion_scores(db)
        if scores_empty:
            logger.info("champion_scores table is empty -- will recalculate after repair")

        # ---- Dry-run: stop here ----
        if args.dry_run:
            logger.info("Dry-run mode: no scraping performed.")
            return 0

        # ---- Repair: parallel scrape + targeted DB write ----
        stats = repair_matchups_parallel(
            db=db,
            champions=missing,
            patch_version=args.patch,
            max_workers=args.max_workers,
            headless=args.headless,
            logger=logger,
        )

        duration_min = stats["duration"] / 60
        logger.info(
            f"Repair completed: {stats['success']}/{stats['total']} champions repaired "
            f"in {duration_min:.1f} min ({stats['failed']} failed)"
        )

        if stats["failed"] > 0:
            logger.warning(
                f"{stats['failed']} champion(s) could not be repaired. "
                "Check logs above for individual errors."
            )

        # ---- Recalculate global scores ----
        if not args.skip_scores and (stats["success"] > 0 or scores_empty):
            logger.info("Recalculating champion scores...")
            try:
                from src.assistant import Assistant
                from src.sqlite_data_source import SQLiteDataSource

                data_source = SQLiteDataSource(db_path)
                assistant = Assistant(data_source=data_source, verbose=False)
                assistant.calculate_global_scores()
                logger.info("Champion scores recalculated successfully")
            except Exception as exc:
                logger.error(f"Failed to recalculate champion scores: {exc}")
                logger.debug(traceback.format_exc())
                # Non-fatal: repair itself succeeded
        else:
            logger.info("Skipping champion score recalculation (--skip-scores or nothing repaired)")

        # Return 1 if any champion failed scraping, 0 if all succeeded
        return 0 if stats["failed"] == 0 else 1

    except Exception as exc:
        logger.error(f"Fatal error during repair: {exc}")
        logger.error(traceback.format_exc())
        return 1

    finally:
        # ---- Cleanup Firefox drivers ----
        if parsers_registry:
            logger.info(f"Closing {len(parsers_registry)} Firefox driver(s)...")
            _cleanup_thread_parsers(parsers_registry, logger)

        # ---- Close assistant if still open ----
        if assistant is not None:
            try:
                assistant.close()
                logger.info("Assistant closed")
            except Exception as exc:
                logger.warning(f"Error closing assistant: {exc}")

        # ---- Close database ----
        if db is not None:
            try:
                db.close()
                logger.info("Database connection closed")
            except Exception as exc:
                logger.warning(f"Error closing database: {exc}")

        logger.info("Repair script finished")
        logger.info("=" * 70)


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
