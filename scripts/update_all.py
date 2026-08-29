"""Nightly data pipeline entry point (Horizon 1 — ROADMAP_2026.md §3 H1.2).

Thin CLI wrapper around src/pipeline.py:run_pipeline(), the single pipeline
also used by the in-app menu (src/ui/lol_coach_legacy.py) — SPEC-01 A2.

    1. Multi-lane scrape (lane discovery >10%, matchups + synergies tagged)
    2. Volumetric completeness check — FAILS LOUDLY on silent data loss
    3. Recalculate champion_scores
    4. Recalculate pool_ban_recommendations
    5. Record freshness metadata in db_meta (read by the app at startup)
    6. Notifications: Windows toast + Discord webhook (DISCORD_WEBHOOK_URL)

Differences with the legacy scripts (per ROADMAP_2026.md decisions):
    - Patch version comes from config.CURRENT_PATCH (no more hardcoded "14")
    - SQLite only: no Neon sync, no Render API refresh (Decisions B & C)
    - Explicit local Database for score recalculation (never remote)

USAGE:
    python scripts/update_all.py                  # full nightly run
    python scripts/update_all.py --skip-synergies # matchups only
    python scripts/update_all.py --workers 8      # override worker count
    python scripts/update_all.py --recompute-only # scores/bans only, no scrape
    pythonw scripts/update_all.py                 # headless (Task Scheduler)
"""

import argparse
import os
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load .env (DISCORD_WEBHOOK_URL) before anything else
try:
    from dotenv import load_dotenv

    _env_path = project_root / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except ImportError:
    pass  # rely on the process environment

from src.config import config
from src.config_constants import scraping_config
from src.pipeline import _setup_logging, run_pipeline


def _set_process_priority() -> None:
    """BELOW_NORMAL priority so the nightly run never freezes the PC."""
    import logging

    logger = logging.getLogger("update_all")
    try:
        import psutil

        process = psutil.Process(os.getpid())
        if sys.platform == "win32":
            process.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        else:
            process.nice(10)
        logger.info("Process priority set to BELOW_NORMAL")
    except Exception as e:
        logger.warning("Could not set process priority: %s", e)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LeagueStats nightly data pipeline")
    parser.add_argument(
        "--patch",
        default=config.CURRENT_PATCH,
        help=f"LoLalytics patch parameter (default from config: {config.CURRENT_PATCH})",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=scraping_config.DEFAULT_MAX_WORKERS,
        help=f"Parallel Selenium workers (default: {scraping_config.DEFAULT_MAX_WORKERS})",
    )
    parser.add_argument(
        "--skip-synergies", action="store_true", help="Scrape matchups only (faster diagnostic run)"
    )
    parser.add_argument(
        "--skip-completeness",
        action="store_true",
        help="Skip the volumetric check (diagnostic only — NEVER for the nightly task)",
    )
    parser.add_argument(
        "--recompute-only",
        action="store_true",
        help="Skip scrape and completeness check; only recalculate scores/bans from existing data",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    _setup_logging()
    _set_process_priority()

    result = run_pipeline(
        include_synergies=not args.skip_synergies,
        workers=args.workers,
        patch=args.patch,
        recompute_only=args.recompute_only,
        skip_completeness=args.skip_completeness,
    )
    # "partial" (SPEC-01 A4: a few champions incomplete, pipeline still ran
    # scores/bans and attempted a targeted repair) is not a task failure —
    # only "failed" should make the nightly Task Scheduler entry non-zero.
    return 0 if result.status in ("ok", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
