"""Shared data pipeline: scrape -> completeness -> scores -> bans -> freshness (SPEC-01 A2).

Before this module existed, ``scripts/update_all.py`` and the in-app menu
(``src/ui/lol_coach_legacy.py``) each reimplemented the same
scrape -> recalculate schema, but drifted apart: the menu never ran the
completeness gate, never wrote ``db_meta``, and never logged to file or
notified. ``run_pipeline()`` is now the single code path both call, so every
menu-triggered run gets the same safeguards as the nightly CLI run.

USAGE:
    from src.pipeline import run_pipeline

    result = run_pipeline()                          # full roster
    result = run_pipeline(champions=["Ahri", "Zed"])  # pool scope, no scrape reset elsewhere
    result = run_pipeline(recompute_only=True)        # scores/bans only, no scrape
"""

import logging
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .config import config
from .config_constants import scraping_config
from .constants import normalize_champion_name_for_url
from .data_quality import DataCompletenessError, assert_completeness
from .db import Database
from .multilane import scrape_all_multilane
from .notifications import Notifier
from .parallel_parser import ParallelParser

logger = logging.getLogger("update_all")

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _setup_logging() -> Path:
    """File + console logging, safe under pythonw.exe (no stdout)."""
    log_dir = PROJECT_ROOT / "logs"
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


@dataclass
class PipelineResult:
    """Outcome of a run_pipeline() call."""

    status: str  # "ok" or "failed"
    scores_count: int = 0
    ban_results: Dict[str, int] = field(default_factory=dict)
    scrape_stats: Optional[dict] = None
    matchups_count: int = 0
    synergies_count: int = 0
    duration_min: float = 0.0
    report: str = ""
    error: Optional[str] = None


def _format_report(stats: dict, scores: int, bans: dict, duration_min: float) -> str:
    """Notification body summarizing a scrape + recompute run."""
    lanes_summary = (
        ", ".join(f"{lane}: {s['success']}/{s['total']}" for lane, s in stats["matchups"].items())
        or "-"
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


def _format_recompute_report(scores: int, bans: dict, duration_min: float) -> str:
    """Notification body for a --recompute-only run (no scrape stats available)."""
    lines = [
        "Mode: recalcul seul (pas de scrape)",
        f"Scores recalculés: {scores} champions",
        f"Pools de bans: {sum(1 for c in bans.values() if c > 0)}/{len(bans)}",
        f"Durée: {duration_min:.1f} min",
    ]
    return "\n".join(lines)


def run_pipeline(
    champions: Optional[List[str]] = None,
    include_matchups: bool = True,
    include_synergies: bool = True,
    workers: Optional[int] = None,
    patch: Optional[str] = None,
    recompute_only: bool = False,
    skip_completeness: bool = False,
) -> PipelineResult:
    """Scrape (optional) -> completeness gate -> scores -> bans -> db_meta.

    This is the single pipeline shared by ``scripts/update_all.py`` (CLI,
    full roster, scheduled) and the in-app menu (interactive, full roster or
    a restricted pool) — see SPEC-01 A2.

    Args:
        champions: Restrict the scrape to these champions (a "pool"). ``None``
            (default) refreshes the whole roster from the Riot API and runs
            the whole-database completeness gate. A restricted list scopes
            the scrape and skips that gate, since it would always fail
            against champions outside the pool.
        include_matchups: Scrape matchups.
        include_synergies: Scrape synergies.
        workers: Parallel Selenium workers (default: scraping_config).
        patch: LoLalytics patch parameter (default: config.CURRENT_PATCH).
        recompute_only: Skip scrape and completeness check; only recalculate
            scores/bans from data already in the database.
        skip_completeness: Skip the volumetric check (diagnostic only).

    Returns:
        PipelineResult with the run's outcome. Never raises: failures are
        captured in ``status="failed"`` / ``error``.
    """
    log_file = _setup_logging()
    notifier = Notifier()
    resolved_patch = patch or config.CURRENT_PATCH

    logger.info("=" * 80)
    logger.info(
        "Pipeline starting — champions=%s, patch=%s, matchups=%s, synergies=%s, "
        "recompute_only=%s (log: %s)",
        "all" if champions is None else f"{len(champions)} (pool)",
        resolved_patch,
        include_matchups,
        include_synergies,
        recompute_only,
        log_file,
    )
    start_time = datetime.now()

    db = Database(config.DATABASE_PATH)
    db.connect()
    parser = None
    assistant = None
    stats = None
    try:
        if recompute_only:
            logger.info("recompute-only: scrape and completeness check skipped")
        else:
            # ── 1. Scrape (multi-lane, tagged) ───────────────────────────────
            parser = ParallelParser(
                max_workers=workers or scraping_config.DEFAULT_MAX_WORKERS,
                patch_version=resolved_patch,
                headless=scraping_config.HEADLESS,
            )
            stats = scrape_all_multilane(
                db,
                parser,
                normalize_champion_name_for_url,
                champions=champions,
                include_matchups=include_matchups,
                include_synergies=include_synergies,
            )
            parser.close()
            parser = None

            # ── 2. Completeness gate (before recalculating anything) ────────
            if skip_completeness:
                logger.warning("Completeness check SKIPPED (--skip-completeness)")
            elif champions is not None:
                logger.info(
                    "Pool-scoped run (%d champion(s)): whole-roster completeness " "check skipped",
                    len(champions),
                )
            else:
                assert_completeness(db, include_synergies=include_synergies)

        # ── 3 & 4. Scores + ban recommendations (SQLite only) ───────────────
        from .assistant import Assistant

        assistant = Assistant(Database(config.DATABASE_PATH), verbose=False)
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

        # ── 5. Freshness metadata ────────────────────────────────────────────
        cursor = db.connection.cursor()
        cursor.execute("SELECT COUNT(*) FROM matchups")
        matchups_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM synergies")
        synergies_count = cursor.fetchone()[0]

        if recompute_only:
            db.set_meta("last_recompute_utc", datetime.now(timezone.utc).isoformat())
        else:
            db.set_meta("last_update_utc", datetime.now(timezone.utc).isoformat())
        db.set_meta("last_update_patch", str(resolved_patch))
        db.set_meta("matchups_count", str(matchups_count))
        db.set_meta("synergies_count", str(synergies_count))

        # ── 6. Success notification ──────────────────────────────────────────
        duration_min = (datetime.now() - start_time).total_seconds() / 60
        if recompute_only:
            report = _format_recompute_report(scores_count, ban_results, duration_min)
        else:
            report = _format_report(stats, scores_count, ban_results, duration_min)
        logger.info("Pipeline completed successfully in %.1f min", duration_min)
        logger.info("\n%s", report)
        notifier.notify_success("LeagueStats — BD mise à jour", report)
        logger.info("=" * 80)

        return PipelineResult(
            status="ok",
            scores_count=scores_count,
            ban_results=ban_results,
            scrape_stats=stats,
            matchups_count=matchups_count,
            synergies_count=synergies_count,
            duration_min=duration_min,
            report=report,
        )

    except DataCompletenessError as e:
        logger.error("COMPLETENESS CHECK FAILED:\n%s", e)
        notifier.notify_failure(
            "LeagueStats — Données incomplètes",
            f"Le scrape a terminé mais la volumétrie est insuffisante.\n{e}\n"
            f"Voir {log_file} et docs/runbook_scraping.md",
        )
        return PipelineResult(status="failed", error=str(e))

    except Exception as e:
        logger.error("Pipeline FAILED: %s", e)
        logger.error(traceback.format_exc())
        notifier.notify_failure(
            "LeagueStats — Échec mise à jour",
            f"{type(e).__name__}: {e}\nVoir {log_file}",
        )
        return PipelineResult(status="failed", error=f"{type(e).__name__}: {e}")

    finally:
        for resource, label in ((parser, "parser"), (assistant, "assistant"), (db, "db")):
            if resource is not None:
                try:
                    resource.close()
                except Exception as e:
                    logger.warning("Cleanup of %s failed: %s", label, e)
