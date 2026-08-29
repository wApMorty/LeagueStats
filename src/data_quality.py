"""Post-scrape volumetric completeness checks (Horizon 1 — ROADMAP_2026.md H1.4).

The 2026-06-01 incident: the database silently dropped from 40 753 to 16 179
matchups (lane granularity lost) and nobody noticed for 10 days. This module
makes that class of failure LOUD: scripts/update_all.py runs
``assert_completeness()`` after every scrape and aborts (exit 1 + failure
notification) when the volumetry is below the thresholds of
``data_quality_config``.

SPEC-01 A4 — the 2026-07-16 incident: 566/566 pages scraped fine, but 13
champions came back without synergies, and the all-or-nothing check aborted
the *entire* pipeline (scores and bans included) over that. Completeness is
now graded: a handful of incomplete champions is a ``warning`` (the pipeline
continues, scores/bans still get recomputed); only a collapsed global
volumetry or a large share of incomplete champions is a ``blocking_failure``.
"""

import logging
from dataclasses import dataclass, field
from typing import List, Tuple

from .config_constants import data_quality_config
from .db import Database

logger = logging.getLogger(__name__)


class DataCompletenessError(Exception):
    """Raised when the post-scrape volumetric check fails (blocking only)."""


@dataclass
class CompletenessReport:
    """Result of a volumetric completeness check.

    ``blocking_failures`` means the database is unusable: ``assert_completeness()``
    raises. ``warnings`` means a handful of champions are incomplete: the
    pipeline logs and continues (scores/bans recomputed, targeted repair
    attempted, status reported as "partial").
    """

    champions_total: int = 0
    matchups_total: int = 0
    synergies_total: int = 0
    champions_without_matchups: List[str] = field(default_factory=list)
    matchups_below_threshold: List[Tuple[str, int]] = field(default_factory=list)
    synergies_below_threshold: List[Tuple[str, int]] = field(default_factory=list)
    blocking_failures: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """False only on a blocking failure — a warning-only report still passes."""
        return not self.blocking_failures

    @property
    def incomplete_matchup_champions(self) -> List[str]:
        """Champions with zero or below-threshold matchups, for targeted repair."""
        names = set(self.champions_without_matchups) | {
            name for name, _ in self.matchups_below_threshold
        }
        return sorted(names)

    @property
    def incomplete_synergy_champions(self) -> List[str]:
        """Champions with zero or below-threshold synergies, for targeted repair."""
        return sorted(name for name, _ in self.synergies_below_threshold)

    def summary(self) -> str:
        """Human-readable summary (logs + notifications)."""
        status = "FAILED" if not self.passed else ("PARTIAL" if self.warnings else "OK")
        lines = [
            f"Completeness check {status}: "
            f"{self.champions_total} champions, "
            f"{self.matchups_total} matchups, "
            f"{self.synergies_total} synergies"
        ]
        lines.extend(f"  - {failure}" for failure in self.blocking_failures)
        lines.extend(f"  - [warning] {warning}" for warning in self.warnings)
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
    """Run all volumetric assertions and return a graded report (never raises).

    Checks:
        1. Total matchups >= MIN_TOTAL_MATCHUPS (catches the mono-lane regression) — blocking
        2. Total synergies >= MIN_TOTAL_SYNERGIES (if include_synergies) — blocking
        3. Share of champions with zero/below-threshold matchups or synergies
           > MAX_INCOMPLETE_CHAMPIONS_RATIO — blocking; below that ratio, the
           same per-champion gaps are reported as warnings only.
    """
    report = CompletenessReport()
    cfg = data_quality_config
    cursor = db.connection.cursor()

    cursor.execute("SELECT COUNT(*) FROM champions")
    report.champions_total = cursor.fetchone()[0]
    if report.champions_total == 0:
        report.blocking_failures.append("champions table is EMPTY")
        logger.error(report.summary())
        return report

    # ── Matchups ─────────────────────────────────────────────────────────────
    cursor.execute("SELECT COUNT(*) FROM matchups")
    report.matchups_total = cursor.fetchone()[0]
    if report.matchups_total < cfg.MIN_TOTAL_MATCHUPS:
        report.blocking_failures.append(
            f"matchups total {report.matchups_total} < {cfg.MIN_TOTAL_MATCHUPS} "
            f"(mono-lane regression? see docs/runbook_scraping.md)"
        )

    for name, count in _count_per_champion(db, "matchups"):
        if count == 0:
            report.champions_without_matchups.append(name)
        elif count < cfg.MIN_MATCHUPS_PER_CHAMPION:
            report.matchups_below_threshold.append((name, count))

    per_champion_issues: List[str] = []
    if report.champions_without_matchups:
        per_champion_issues.append(
            f"{len(report.champions_without_matchups)} champion(s) with ZERO matchups: "
            f"{', '.join(report.champions_without_matchups[:10])}"
            + ("..." if len(report.champions_without_matchups) > 10 else "")
        )
    if report.matchups_below_threshold:
        worst = sorted(report.matchups_below_threshold, key=lambda x: x[1])[:10]
        per_champion_issues.append(
            f"{len(report.matchups_below_threshold)} champion(s) below "
            f"{cfg.MIN_MATCHUPS_PER_CHAMPION} matchups: "
            + ", ".join(f"{name}={count}" for name, count in worst)
        )

    # ── Synergies ────────────────────────────────────────────────────────────
    if include_synergies:
        cursor.execute("SELECT COUNT(*) FROM synergies")
        report.synergies_total = cursor.fetchone()[0]
        if report.synergies_total < cfg.MIN_TOTAL_SYNERGIES:
            report.blocking_failures.append(
                f"synergies total {report.synergies_total} < {cfg.MIN_TOTAL_SYNERGIES}"
            )

        report.synergies_below_threshold = [
            (name, count)
            for name, count in _count_per_champion(db, "synergies")
            if count < cfg.MIN_SYNERGIES_PER_CHAMPION
        ]
        if report.synergies_below_threshold:
            worst = sorted(report.synergies_below_threshold, key=lambda x: x[1])[:10]
            per_champion_issues.append(
                f"{len(report.synergies_below_threshold)} champion(s) below "
                f"{cfg.MIN_SYNERGIES_PER_CHAMPION} synergies: "
                + ", ".join(f"{name}={count}" for name, count in worst)
            )

    # ── Grade the per-champion issues: blocking above the ratio, warning below ─
    incomplete = set(report.incomplete_matchup_champions)
    if include_synergies:
        incomplete |= set(report.incomplete_synergy_champions)
    ratio = len(incomplete) / report.champions_total if report.champions_total else 0.0

    if per_champion_issues:
        if ratio > cfg.MAX_INCOMPLETE_CHAMPIONS_RATIO:
            report.blocking_failures.append(
                f"{len(incomplete)}/{report.champions_total} champions incomplete "
                f"({ratio:.1%}) > {cfg.MAX_INCOMPLETE_CHAMPIONS_RATIO:.0%} threshold"
            )
            report.blocking_failures.extend(per_champion_issues)
        else:
            report.warnings.extend(per_champion_issues)

    if not report.passed:
        logger.error(report.summary())
    elif report.warnings:
        logger.warning(report.summary())
    else:
        logger.info(report.summary())
    return report


def assert_completeness(db: Database, include_synergies: bool = True) -> CompletenessReport:
    """Like check_completeness() but raises DataCompletenessError on a blocking failure.

    This is the loud-failure entry point used by scripts/update_all.py.
    A warning-only report (a few incomplete champions, below the ratio) does
    NOT raise — the caller is expected to inspect ``report.warnings`` and
    ``report.incomplete_*_champions`` to continue with a "partial" status.
    """
    report = check_completeness(db, include_synergies=include_synergies)
    if not report.passed:
        raise DataCompletenessError(report.summary())
    return report
