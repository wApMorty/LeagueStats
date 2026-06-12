"""Nightly data pipeline orchestrator (Horizon 1 — ROADMAP_2026.md §3 H1.2).

Industrialized successor of fill_db.py / auto_update_db.py:

    1. Multi-lane scrape (lane discovery >10%, matchups + synergies tagged)
    2. Volumetric completeness check — FAILS LOUDLY on silent data loss
    3. Recalculate champion_scores
    4. Recalculate pool_ban_recommendations
    5. Record freshness metadata in db_meta (read by the app at startup)
    6. Notifications: Windows toast + Discord webhook (DISCORD_WEBHOOK_URL)

Differences with the legacy scripts (per ROADMAP_2026.md decisions):
    - Patch version comes from config.CURRENT_PATCH (no more hardcoded "14")
    - SQLite only: no Neon sync, no Render API refresh (Decisions B & C)
    - Explicit SQLiteDataSource for score recalculation (never Hybrid/remote)

USAGE:
    python scripts/update_all.py                  # full nightly run
    python scripts/update_all.py --skip-synergies # matchups only
    python scripts/update_all.py --workers 8      # override worker count
    pythonw scripts/update_all.py                 # headless (Task Scheduler)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
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
from src.constants import normalize_champion_name_for_url
from src.data_quality import DataCompletenessError, assert_completeness
from src.db import Database
from src.multilane import scrape_all_multilane
from src.notifications import Notifier
from src.parallel_parser import ParallelParser

logger = logging.getLogger("update_all")


def _setup_logging() -> Path:
    """File + console logging, safe under pythonw.exe (no stdout)."""
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "update_all.log"

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(
        logging.Formatter(
            "[%(asctime)s] %(name)s - %(levelname)s: %(message)s", "%Y-%m-%d %H:%M:%S"
        )
    )
    root.addHandler(file_handler)

    if hasattr(sys, "stdout") and sys.stdout is not None:
        console = logging.StreamHandler(sys.stdout)
        console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        root.addHandler(console)

    # External libraries are extremely verbose
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    return log_file


def _set_process_priority() -> None:
    """BELOW_NORMAL priority so the nightly run never freezes the PC."""
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
    return parser.parse_args()


def _format_report(stats: dict, scores: int, bans: dict, duration_min: float) -> str:
    """Notification body summarizing the run."""
    lanes_summary = ", ".join(
        f"{lane}: {s['success']}/{s['total']}" for lane, s in stats["matchups"].items()
    )
    lines = [
        f"Pages: {stats['success']}/{stats['total']} ok ({stats['failed']} échecs)",
        f"Matchups par lane — {lanes_summary}",
        f"Scores recalculés: {scores} champions",
        f"Pools de bans: {sum(1 for c in bans.values() if c > 0)}/{len(bans)}",
        f"Durée: {duration_min:.1f} min",
    ]
    if stats["discovery_failures"]:
        lines.append(
            f"⚠️ Découverte lanes en échec ({len(stats['discovery_failures'])}): "
            + ", ".join(stats["discovery_failures"][:5])
        )
    return "\n".join(lines)


def main() -> int:
    args = _parse_args()
    log_file = _setup_logging()
    _set_process_priority()
    notifier = Notifier()

    logger.info("=" * 80)
    logger.info(
        "update_all starting — patch=%s, workers=%d, synergies=%s (log: %s)",
        args.patch,
        args.workers,
        not args.skip_synergies,
        log_file,
    )
    start_time = datetime.now()

    db = None
    parser = None
    assistant = None
    try:
        # ── 1. Scrape multi-lane ─────────────────────────────────────────────
        db = Database(config.DATABASE_PATH)
        db.connect()

        parser = ParallelParser(
            max_workers=args.workers,
            patch_version=args.patch,
            headless=scraping_config.HEADLESS,
        )
        stats = scrape_all_multilane(
            db, parser, normalize_champion_name_for_url, include_synergies=not args.skip_synergies
        )
        parser.close()
        parser = None

        # ── 2. Completeness gate (before recalculating anything) ────────────
        if args.skip_completeness:
            logger.warning("Completeness check SKIPPED (--skip-completeness)")
        else:
            assert_completeness(db, include_synergies=not args.skip_synergies)

        # ── 3 & 4. Scores + ban recommendations (SQLite only, Decision C) ───
        from src.assistant import Assistant
        from src.sqlite_data_source import SQLiteDataSource

        assistant = Assistant(data_source=SQLiteDataSource(config.DATABASE_PATH), verbose=False)
        scores_count = assistant.calculate_global_scores()
        logger.info("champion_scores recalculated: %d champions", scores_count)

        ban_results = assistant.precalculate_all_custom_pool_bans()
        logger.info(
            "pool_ban_recommendations recalculated: %d pools, %d recommendations",
            len(ban_results),
            sum(ban_results.values()),
        )
        assistant.close()
        assistant = None

        # ── 5. Freshness metadata (only after a fully successful run) ───────
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM matchups")
        matchups_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM synergies")
        synergies_count = cursor.fetchone()[0]

        db.set_meta("last_update_utc", datetime.now(timezone.utc).isoformat())
        db.set_meta("last_update_patch", str(args.patch))
        db.set_meta("matchups_count", str(matchups_count))
        db.set_meta("synergies_count", str(synergies_count))

        # ── 6. Success notification ──────────────────────────────────────────
        duration_min = (datetime.now() - start_time).total_seconds() / 60
        report = _format_report(stats, scores_count, ban_results, duration_min)
        logger.info("update_all completed successfully in %.1f min", duration_min)
        logger.info("\n%s", report)
        notifier.notify_success("LeagueStats — BD mise à jour", report)
        logger.info("=" * 80)
        return 0

    except DataCompletenessError as e:
        logger.error("COMPLETENESS CHECK FAILED:\n%s", e)
        notifier.notify_failure(
            "LeagueStats — Données incomplètes",
            f"Le scrape a terminé mais la volumétrie est insuffisante.\n{e}\n"
            f"Voir {log_file} et docs/runbook_scraping.md",
        )
        return 1

    except Exception as e:
        import traceback

        logger.error("update_all FAILED: %s", e)
        logger.error(traceback.format_exc())
        notifier.notify_failure(
            "LeagueStats — Échec mise à jour",
            f"{type(e).__name__}: {e}\nVoir {log_file}",
        )
        return 1

    finally:
        for resource, label in ((parser, "parser"), (assistant, "assistant"), (db, "db")):
            if resource is not None:
                try:
                    resource.close()
                except Exception as e:
                    logger.warning("Cleanup of %s failed: %s", label, e)


if __name__ == "__main__":
    sys.exit(main())
