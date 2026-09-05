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

Wrapper CLI mince (dette de code, TODO.md P4) : le moteur de réparation
(RepairTarget, detect_*, _scrape_champion, repair_parallel) vit dans
src/repair_engine.py, même principe que src/pipeline.py pour
scripts/update_all.py.
"""

import sys
import argparse
import logging
import traceback
from pathlib import Path
from typing import List, Optional

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

from src import repair_engine

# MATCHUPS/SYNERGIES re-exported for backward compatibility (tests import
# them as scripts.repair_data.MATCHUPS/SYNERGIES) -- not used in this file.
from src.repair_engine import (  # noqa: F401
    MATCHUPS,
    SYNERGIES,
    TARGETS,
    detect_champions_without_data,
    detect_empty_champion_scores,
    repair_parallel,
)
from src.db import Database
from src.config import config
from src.config_constants import scraping_config
from src.constants import normalize_champion_name_for_url
from src.lane_discovery import discover_lanes_for_champions
from src.multilane import group_champions_by_lane
from src.parser import Parser


def _setup_logging(target, log_to_file: bool = True) -> logging.Logger:
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
    # We monkey-patch repair_engine._get_or_create_parser to register parsers here.
    # (Patches the engine module directly -- _scrape_champion, which calls
    # _get_or_create_parser, lives in src/repair_engine.py, not here.)
    parsers_registry: List[Parser] = []
    original_get_parser = repair_engine._get_or_create_parser

    def _tracked_get_or_create_parser(headless: bool) -> Parser:
        parser_instance = original_get_parser(headless)
        if parser_instance not in parsers_registry:
            parsers_registry.append(parser_instance)
        return parser_instance

    # Patch the module-level function reference used by worker threads
    repair_engine._get_or_create_parser = _tracked_get_or_create_parser

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
            repair_engine._cleanup_thread_parsers(parsers_registry, logger)

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
