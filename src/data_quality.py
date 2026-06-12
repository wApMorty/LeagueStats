"""Post-scrape volumetric completeness checks (Horizon 1 — ROADMAP_2026.md H1.4).

The 2026-06-01 incident: the database silently dropped from 40 753 to 16 179
matchups (lane granularity lost) and nobody noticed for 10 days. This module
makes that class of failure LOUD: scripts/update_all.py runs
``assert_completeness()`` after every scrape and aborts (exit 1 + failure
notification) when the volumetry is below the thresholds of
``data_quality_config``.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Tuple

from .config_constants import data_quality_config
from .db import Database

logger = logging.getLogger(__name__)


class DataCompletenessError(Exception):
    """Raised when the post-scrape volumetric check fails."""


@dataclass
class CompletenessReport:
    """Result of a volumetric completeness check."""

    champions_total: int = 0
    matchups_total: int = 0
    synergies_total: int = 0
    champions_without_matchups: List[str] = field(default_factory=list)
    matchups_below_threshold: List[Tuple[str, int]] = field(default_factory=list)
    synergies_below_threshold: List[Tuple[str, int]] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def summary(self) -> str:
        """Human-readable summary (logs + notifications)."""
        status = "OK" if self.passed else "FAILED"
        lines = [
            f"Completeness check {status}: "
            f"{self.champions_total} champions, "
            f"{self.matchups_total} matchups, "
            f"{self.synergies_total} synergies"
        ]
        lines.extend(f"  - {failure}" for failure in self.failures)
        return "\n".join(lines)


def _count_per_champion(db: Database, table: str) -> List[Tuple[str, int]]:
    """Rows per champion for a data table, including champions with 0 rows."""
    cursor = db.connection.cursor()
    cursor.execute(
        f"""
        SELECT c.name, COUNT(t.id)
        FROM champions c
        LEFT JOIN {table} t ON t.champion = c.id
        GROUP BY c.id
        ORDER BY c.name
        """  # nosec B608 - table is an internal literal, never user input
    )
    return cursor.fetchall()


def check_completeness(db: Database, include_synergies: bool = True) -> CompletenessReport:
    """Run all volumetric assertions and return a report (never raises).

    Checks:
        1. Total matchups >= MIN_TOTAL_MATCHUPS (catches the mono-lane regression)
        2. Every champion has >= MIN_MATCHUPS_PER_CHAMPION matchups, all lanes
        3. Same pair of checks for synergies (if include_synergies)
    """
    report = CompletenessReport()
    cfg = data_quality_config
    cursor = db.connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM champions")
    report.champions_total = cursor.fetchone()[0]
    if report.champions_total == 0:
        report.failures.append("champions table is EMPTY")
        return report

    # ── Matchups ─────────────────────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM matchups")
    report.matchups_total = cursor.fetchone()[0]
    if report.matchups_total < cfg.MIN_TOTAL_MATCHUPS:
        report.failures.append(
            f"matchups total {report.matchups_total} < {cfg.MIN_TOTAL_MATCHUPS} "
            f"(mono-lane regression? see docs/runbook_scraping.md)"
        )

    for name, count in _count_per_champion(db, "matchups"):
        if count == 0:
            report.champions_without_matchups.append(name)
        elif count < cfg.MIN_MATCHUPS_PER_CHAMPION:
            report.matchups_below_threshold.append((name, count))

    if report.champions_without_matchups:
        report.failures.append(
            f"{len(report.champions_without_matchups)} champion(s) with ZERO matchups: "
            f"{', '.join(report.champions_without_matchups[:10])}"
            + ("..." if len(report.champions_without_matchups) > 10 else "")
        )
    if report.matchups_below_threshold:
        worst = sorted(report.matchups_below_threshold, key=lambda x: x[1])[:10]
        report.failures.append(
            f"{len(report.matchups_below_threshold)} champion(s) below "
            f"{cfg.MIN_MATCHUPS_PER_CHAMPION} matchups: "
            + ", ".join(f"{name}={count}" for name, count in worst)
        )

    # ── Synergies ────────────────────────────────────────────────────────────
    if include_synergies:
        cursor.execute("SELECT COUNT(*) FROM synergies")
        report.synergies_total = cursor.fetchone()[0]
        if report.synergies_total < cfg.MIN_TOTAL_SYNERGIES:
            report.failures.append(
                f"synergies total {report.synergies_total} < {cfg.MIN_TOTAL_SYNERGIES}"
            )

        below = [
            (name, count)
            for name, count in _count_per_champion(db, "synergies")
            if count < cfg.MIN_SYNERGIES_PER_CHAMPION
        ]
        report.synergies_below_threshold = below
        if below:
            worst = sorted(below, key=lambda x: x[1])[:10]
            report.failures.append(
                f"{len(below)} champion(s) below {cfg.MIN_SYNERGIES_PER_CHAMPION} synergies: "
                + ", ".join(f"{name}={count}" for name, count in worst)
            )

    if report.passed:
        logger.info(report.summary())
    else:
        logger.error(report.summary())
    return report


def assert_completeness(db: Database, include_synergies: bool = True) -> CompletenessReport:
    """Like check_completeness() but raises DataCompletenessError on failure.

    This is the loud-failure entry point used by scripts/update_all.py.
    """
    report = check_completeness(db, include_synergies=include_synergies)
    if not report.passed:
        raise DataCompletenessError(report.summary())
    return report
