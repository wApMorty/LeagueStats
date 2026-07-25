"""
Repair Script for LeagueStats Coach (matchups or synergies).

This script detects and repairs champions that are missing matchup or synergy
data in the database. It performs targeted re-scraping of only the affected
champions to avoid destroying existing data.

CRITICAL SAFETY RULES:
- NEVER calls parse_all_champions() / parse_all_synergies() -- would DROP the table
- NEVER calls init_matchups_table() / init_synergies_table() -- would DROP the table
- Only calls clear_*_for_champion() + add_*_batch() per champion

DETECTION METHOD:
    Uses SQL LEFT JOIN between champions and the target table to find champions
    with zero rows.

LANE HANDLING:
    Reuses the same dynamic lane discovery as the nightly multi-lane pipeline
    (src/lane_discovery.py, src/multilane.py) instead of scraping an untagged
    default lane: missing champions are grouped by their actually-played
    lane(s) (>10% pickrate) and each (champion, lane) page is scraped and
    tagged accordingly, exactly like scripts/update_all.py. Champions whose
    lane discovery fails fall back to the untagged default lane, same as the
    nightly pipeline.

USAGE:
    python scripts/repair_data.py --target matchups
    python scripts/repair_data.py --target synergies --dry-run
    python scripts/repair_data.py --target matchups --max-workers 3

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
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock, local
from typing import Callable, Dict, List, Optional, Tuple
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
from src.config_constants import scraping_config
from src.constants import normalize_champion_name_for_url
from src.lane_discovery import discover_lanes_for_champions
from src.multilane import group_champions_by_lane
from src.parser import Parser

# Thread-local storage: one Firefox driver per worker thread
_thread_local = local()


@dataclass(frozen=True)
class RepairTarget:
    """Everything that differs between a matchup repair and a synergy repair.

    The repair pipeline (detect -> discover lanes -> scrape in parallel ->
    clear once per champion -> insert per lane) is identical for both; only
    the table, the Parser method and the two Database write signatures change.
    """

    name: str  # "matchups" | "synergies"
    table: str  # SQL table holding the rows
    peer: str  # "enemy" | "ally" -- the second champion of a row
    default_headless: bool
    scrape: Callable[[Parser, str, str, Optional[str]], list]
    clear: Callable[[Database, str, dict], None]
    insert: Callable[[Database, list, dict, Optional[str]], None]


MATCHUPS = RepairTarget(
    name="matchups",
    table="matchups",
    peer="enemy",
    # GUI mode bypasses Cloudflare detection better on the matchup pages
    default_headless=False,
    scrape=lambda parser, patch, champion, lane: parser.get_champion_data_on_patch(
        patch, champion, lane
    ),
    clear=lambda db, champion, cache: db.clear_matchups_for_champion(champion, cache),
    insert=lambda db, batch, cache, lane: db.add_matchups_batch(batch, cache, lane=lane),
)

SYNERGIES = RepairTarget(
    name="synergies",
    table="synergies",
    peer="ally",
    default_headless=True,
    scrape=lambda parser, patch, champion, lane: parser.get_champion_synergies_on_patch(
        patch, champion, lane
    ),
    clear=lambda db, champion, cache: db.clear_synergies_for_champion(champion),
    insert=lambda db, batch, cache, lane: db.add_synergies_batch(batch, lane=lane),
)

TARGETS = {target.name: target for target in (MATCHUPS, SYNERGIES)}


def _setup_logging(target: RepairTarget, log_to_file: bool = True) -> logging.Logger:
    """Configure logging for both console and optional file output.

    Args:
        target: Repair target (drives the log file name)
        log_to_file: If True, also write logs to logs/repair_<target>.log

    Returns:
        Configured logger instance
    """
    log_format = "[%(asctime)s] %(levelname)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    handlers: List[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if log_to_file:
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        log_file = log_dir / f"repair_{target.name}.log"
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


def detect_champions_without_data(db: Database, target: RepairTarget) -> List[str]:
    """Find all champions that have zero rows in the target table.

    Uses a LEFT JOIN so champions absent from the table are identified even
    if the table is empty or missing rows.

    Args:
        db: Connected Database instance
        target: Repair target (matchups or synergies)

    Returns:
        Sorted list of champion names with no data
    """
    cursor = db.connection.cursor()
    # Table name comes from the RepairTarget constants above, never from user input
    cursor.execute(
        f"""
        SELECT c.name
        FROM champions c
        LEFT JOIN {target.table} t ON t.champion = c.id
        GROUP BY c.id, c.name
        HAVING COUNT(t.id) = 0
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


def _scrape_champion(
    target: RepairTarget,
    champion: str,
    patch_version: str,
    headless: bool,
    lane: Optional[str],
) -> Tuple[str, Optional[str], list]:
    """Scrape data for a single (champion, lane) page.

    Retries up to 3 times on transient WebDriver / Timeout errors before
    giving up and returning an empty list.

    Args:
        target: Repair target (matchups or synergies)
        champion: Champion name (as stored in the DB, e.g. "AurelionSol")
        patch_version: Patch window string (e.g. "14")
        headless: Whether to run Firefox headless
        lane: Lane to scrape (top/jungle/middle/bottom/support), or None to
              scrape LoLalytics' default lane (lane discovery failure fallback)

    Returns:
        Tuple of (champion_name, lane, rows). rows contains tuples of
        (peer, winrate, delta1, delta2, pickrate, games).
        Returns empty list on failure.
    """
    from selenium.common.exceptions import WebDriverException, TimeoutException

    parser = _get_or_create_parser(headless)
    normalized = normalize_champion_name_for_url(champion)
    lane_label = lane or "default"

    for attempt in range(1, 4):
        try:
            rows = target.scrape(parser, patch_version, normalized, lane)
            return champion, lane, rows
        except (WebDriverException, TimeoutException) as exc:
            if attempt < 3:
                wait_secs = 2**attempt  # 2s, 4s
                logging.getLogger(__name__).warning(
                    f"Attempt {attempt}/3 failed for {champion} {target.name} ({lane_label}): {exc} "
                    f"-- retrying in {wait_secs}s"
                )
                time.sleep(wait_secs)
            else:
                logging.getLogger(__name__).error(
                    f"All 3 attempts failed for {champion} {target.name} ({lane_label}): {exc}"
                )
                return champion, lane, []
        except Exception as exc:
            logging.getLogger(__name__).error(
                f"Unexpected error scraping {champion} {target.name} ({lane_label}): {exc}"
            )
            return champion, lane, []

    return champion, lane, []  # unreachable but satisfies type checker


def repair_parallel(
    target: RepairTarget,
    db: Database,
    groups: Dict[Optional[str], List[str]],
    patch_version: str,
    max_workers: int,
    headless: bool,
    logger: logging.Logger,
) -> dict:
    """Re-scrape and insert rows for the given (lane -> champions) groups in parallel.

    Groups come from group_champions_by_lane(discover_lanes_for_champions(...)),
    the same helpers used by the nightly multi-lane pipeline (src/multilane.py),
    so a champion playing several lanes is scraped and tagged once per lane
    just like a full update_all.py run.

    For each (champion, lane) page this function:
    1. Scrapes data using a dedicated thread-local Firefox driver
    2. Clears existing (empty) rows for that champion, once per champion, via
       target.clear() (safe -- does NOT drop the table) -- done once even if
       the champion has several lanes, so a second lane's insert never wipes
       the first lane's freshly-written rows
    3. Inserts new rows via target.insert(lane=...) inside a shared lock

    NEVER calls parse_all_champions() / parse_all_synergies() or the init_*_table()
    helpers.

    Args:
        target: Repair target (matchups or synergies)
        db: Connected Database instance
        groups: Mapping lane (or None for the discovery-failure fallback) to
                the list of champions to scrape on that lane
        patch_version: Patch window string (e.g. "14")
        max_workers: Number of parallel Firefox workers
        headless: Whether to run Firefox headless
        logger: Logger instance

    Returns:
        dict with keys 'success', 'failed', 'total', 'duration' (champion-level counts)
    """
    db_lock = Lock()
    champion_cache = db.build_champion_cache()
    cleared_champions: set = set()

    all_champions = sorted({champ for champs in groups.values() for champ in champs})
    work_items = [(champ, lane) for lane, champs in groups.items() for champ in champs]

    success_champions: set = set()
    failed_pages = 0
    start_time = time.time()

    logger.info(
        f"Starting parallel {target.name} repair: {len(all_champions)} champions, "
        f"{len(work_items)} (champion, lane) pages, {max_workers} workers, headless={headless}"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_scrape_champion, target, champ, patch_version, headless, lane): (
                champ,
                lane,
            )
            for champ, lane in work_items
        }

        for future in as_completed(futures):
            champion, lane = futures[future]
            lane_label = lane or "default"
            try:
                champ_name, champ_lane, rows = future.result(timeout=120)

                if not rows:
                    logger.warning(
                        f"No {target.name} data returned for {champ_name} ({lane_label}) "
                        "-- skipping insert"
                    )
                    failed_pages += 1
                    continue

                # Thread-safe DB write: clear old (empty) rows once per champion, then insert
                with db_lock:
                    if champ_name not in cleared_champions:
                        target.clear(db, champ_name, champion_cache)
                        cleared_champions.add(champ_name)

                    # Convert to batch format: [(champion, peer, wr, d1, d2, pick, games), ...]
                    batch = [
                        (champ_name, peer, winrate, d1, d2, pick, games)
                        for peer, winrate, d1, d2, pick, games in rows
                    ]
                    target.insert(db, batch, champion_cache, champ_lane)

                logger.info(
                    f"Repaired {champ_name} ({lane_label}): {len(rows)} {target.name} inserted"
                )
                success_champions.add(champ_name)

            except Exception as exc:
                logger.error(f"Failed to repair {champion} ({lane_label}): {exc}")
                failed_pages += 1

    duration = time.time() - start_time
    failed_champions = [c for c in all_champions if c not in success_champions]

    return {
        "success": len(success_champions),
        "failed": len(failed_champions),
        "total": len(all_champions),
        "duration": duration,
    }


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
            "Repair champions missing matchup or synergy data in the LeagueStats "
            "database. Detects affected champions via SQL and re-scrapes them "
            "individually without touching existing data for other champions."
        )
    )
    parser.add_argument(
        "--target",
        choices=sorted(TARGETS),
        required=True,
        help="Which data to repair: matchups or synergies",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print champions missing data without scraping anything",
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
        default=None,
        help=(
            "Run Firefox in headless mode. Default: off for --target matchups "
            "(GUI mode bypasses Cloudflare detection better), on for "
            "--target synergies. Automated services should use --headless "
            "with --firefox-profile."
        ),
    )
    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="Run Firefox with a visible GUI",
    )
    parser.add_argument(
        "--firefox-profile",
        type=str,
        default="",
        metavar="PATH",
        help=(
            "Firefox profile directory containing cf_clearance cookies for lolalytics.com. "
            "Overrides FIREFOX_PROFILE_PATH in config_constants.py. "
            "Use with --headless for automated headless scraping. "
            r"Example: C:\Users\Paul\AppData\Roaming\Mozilla\Firefox\Profiles\xxxxxxxx.lolalytics"
        ),
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
    target = TARGETS[args.target]
    # --headless / --no-headless unset: fall back to the target's default
    headless = target.default_headless if args.headless is None else args.headless
    logger = _setup_logging(target, log_to_file=True)

    # Override profile path from CLI if provided
    if args.firefox_profile:
        scraping_config.FIREFOX_PROFILE_PATH = args.firefox_profile

    logger.info("=" * 70)
    logger.info(f"LeagueStats Coach - Repair {target.name.capitalize()}")
    logger.info("=" * 70)
    logger.info(f"Patch version : {args.patch}")
    logger.info(f"Max workers   : {args.max_workers}")
    logger.info(f"Headless mode : {headless}")
    logger.info(
        f"Firefox profile: {scraping_config.FIREFOX_PROFILE_PATH or '(none — fresh profile)'}"
    )
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

        # ---- Detect champions without data ----
        logger.info(f"Detecting champions without {target.name} data...")
        missing = detect_champions_without_data(db, target)

        if not missing:
            logger.info(f"All champions have {target.name} data. Nothing to repair.")
            return 0

        logger.info(f"Found {len(missing)} champion(s) without {target.name}:")
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

        # ---- Discover lanes for missing champions (same method as update_all.py) ----
        logger.info(f"Discovering lanes for champions missing {target.name}...")
        lane_map = discover_lanes_for_champions(
            missing, args.patch, normalize_champion_name_for_url, max_workers=args.max_workers
        )
        discovery_failures = sorted(champ for champ, lanes in lane_map.items() if not lanes)
        if discovery_failures:
            logger.warning(
                f"Lane discovery failed for {len(discovery_failures)} champion(s) "
                f"(default-lane fallback): {', '.join(discovery_failures)}"
            )

        groups = group_champions_by_lane(lane_map)
        logger.info(
            "Repair plan: %s",
            {lane or "default": len(champs) for lane, champs in groups.items()},
        )

        # ---- Repair: parallel scrape + targeted DB write ----
        stats = repair_parallel(
            target=target,
            db=db,
            groups=groups,
            patch_version=args.patch,
            max_workers=args.max_workers,
            headless=headless,
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

                assistant = Assistant(Database(db_path), verbose=False)
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
