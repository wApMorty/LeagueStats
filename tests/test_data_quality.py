"""Tests for src/data_quality.py (Horizon 1 — volumetric completeness).

These tests encode two regressions:
- 2026-06-01: a silent 40k -> 16k matchup loss must fail loudly (blocking).
- 2026-07-16: 566/566 pages scraped fine but 13/566 champions came back
  without synergies, and the all-or-nothing check aborted the whole
  pipeline over that. SPEC-01 A4 grades completeness: a small share of
  incomplete champions is a warning (pipeline continues); only a collapsed
  global volumetry or a large share of incomplete champions blocks.
"""

import pytest

from src.config_constants import data_quality_config
from src.data_quality import (
    DataCompletenessError,
    assert_completeness,
    check_completeness,
)
from src.db import Database


@pytest.fixture
def quality_db(tmp_path):
    """Database with production-like schema and a configurable population."""
    database = Database(str(tmp_path / "quality.db"))
    database.connect()
    cursor = database.connection.cursor()
    cursor.execute(
        "CREATE TABLE champions (id INTEGER PRIMARY KEY, key TEXT, name TEXT NOT NULL, title TEXT)"
    )
    database.connection.commit()
    database.init_matchups_table()
    database.init_synergies_table()
    yield database
    database.close()


def populate(db, champions=3, matchups_per_champ=100, synergies_per_champ=80):
    """Insert N champions, each with the given row counts (enemy = next champion)."""
    cursor = db.connection.cursor()
    for i in range(1, champions + 1):
        cursor.execute("INSERT INTO champions (id, name) VALUES (?, ?)", (i, f"Champ{i}"))
    for i in range(1, champions + 1):
        enemy = i % champions + 1
        for _ in range(matchups_per_champ):
            cursor.execute(
                "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane)"
                " VALUES (?, ?, 50.0, 0.0, 0.0, 5.0, 1000, 'top')",
                (i, enemy),
            )
        for _ in range(synergies_per_champ):
            cursor.execute(
                "INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games, lane)"
                " VALUES (?, ?, 50.0, 0.0, 0.0, 5.0, 1000, 'top')",
                (i, enemy),
            )
    db.connection.commit()


def clear_matchups(db, champion_id):
    cursor = db.connection.cursor()
    cursor.execute("DELETE FROM matchups WHERE champion = ?", (champion_id,))
    db.connection.commit()


def clear_synergies(db, champion_id):
    cursor = db.connection.cursor()
    cursor.execute("DELETE FROM synergies WHERE champion = ?", (champion_id,))
    db.connection.commit()


@pytest.fixture(autouse=True)
def small_thresholds(monkeypatch):
    """Scale global thresholds down to the small test populations."""
    monkeypatch.setattr(data_quality_config, "MIN_TOTAL_MATCHUPS", 250)
    monkeypatch.setattr(data_quality_config, "MIN_TOTAL_SYNERGIES", 200)
    monkeypatch.setattr(data_quality_config, "MIN_MATCHUPS_PER_CHAMPION", 75)
    monkeypatch.setattr(data_quality_config, "MIN_SYNERGIES_PER_CHAMPION", 50)
    monkeypatch.setattr(data_quality_config, "MAX_INCOMPLETE_CHAMPIONS_RATIO", 0.05)


class TestCheckCompleteness:
    def test_healthy_database_passes(self, quality_db):
        populate(quality_db, champions=3, matchups_per_champ=100, synergies_per_champ=80)
        report = check_completeness(quality_db)
        assert report.passed
        assert not report.warnings
        assert report.matchups_total == 300
        assert report.synergies_total == 240
        assert "OK" in report.summary()

    def test_empty_champions_table_fails(self, quality_db):
        report = check_completeness(quality_db)
        assert not report.passed
        assert "EMPTY" in report.summary()

    def test_global_matchup_loss_blocks(self, quality_db):
        """The 40k -> 16k silent loss scenario: total below the floor blocks
        regardless of the per-champion ratio."""
        populate(quality_db, champions=3, matchups_per_champ=80, synergies_per_champ=80)
        report = check_completeness(quality_db)
        assert not report.passed
        assert any("matchups total 240 < 250" in f for f in report.blocking_failures)
        assert "runbook" in report.summary()

    def test_synergies_can_be_excluded(self, quality_db):
        populate(quality_db, champions=3, matchups_per_champ=100, synergies_per_champ=0)
        report = check_completeness(quality_db, include_synergies=False)
        assert report.passed
        assert report.synergies_total == 0


class TestGradedCompleteness:
    """SPEC-01 A4: blocking_failures vs warnings, gated by MAX_INCOMPLETE_CHAMPIONS_RATIO."""

    def test_few_incomplete_champions_warn_and_continue(self, quality_db):
        """3/173 champions with zero synergies (~1.7%) is below the 5%
        ratio: a warning, not a block — mirrors the 2026-07-16 incident."""
        populate(quality_db, champions=173, matchups_per_champ=100, synergies_per_champ=80)
        for champion_id in (1, 2, 3):
            clear_synergies(quality_db, champion_id)

        report = check_completeness(quality_db)
        assert report.passed
        assert report.warnings
        assert report.incomplete_synergy_champions == ["Champ1", "Champ2", "Champ3"]
        assert "PARTIAL" in report.summary()

    def test_many_incomplete_champions_block(self, quality_db):
        """20/173 champions with zero matchups (~11.6%) exceeds the 5%
        ratio: the run is blocked."""
        populate(quality_db, champions=173, matchups_per_champ=100, synergies_per_champ=80)
        for champion_id in range(1, 21):
            clear_matchups(quality_db, champion_id)

        report = check_completeness(quality_db)
        assert not report.passed
        assert not report.warnings
        assert len(report.incomplete_matchup_champions) == 20

    def test_champion_below_threshold_counts_toward_ratio(self, quality_db):
        populate(quality_db, champions=173, matchups_per_champ=100, synergies_per_champ=80)
        cursor = quality_db.connection.cursor()
        cursor.execute(
            "DELETE FROM matchups WHERE champion = 1 AND id NOT IN "
            "(SELECT id FROM matchups WHERE champion = 1 LIMIT 10)"
        )
        quality_db.connection.commit()

        report = check_completeness(quality_db)
        assert report.passed
        assert ("Champ1", 10) in report.matchups_below_threshold
        assert "Champ1" in report.incomplete_matchup_champions


class TestAssertCompleteness:
    def test_raises_on_blocking_failure(self, quality_db):
        populate(quality_db, champions=3, matchups_per_champ=10, synergies_per_champ=10)
        with pytest.raises(DataCompletenessError, match="Completeness check FAILED"):
            assert_completeness(quality_db)

    def test_returns_report_on_success(self, quality_db):
        populate(quality_db, champions=3, matchups_per_champ=100, synergies_per_champ=80)
        report = assert_completeness(quality_db)
        assert report.passed

    def test_does_not_raise_on_warning_only(self, quality_db):
        """A few incomplete champions must not raise — the pipeline is meant
        to catch this as report.warnings and continue (SPEC-01 A4)."""
        populate(quality_db, champions=173, matchups_per_champ=100, synergies_per_champ=80)
        clear_synergies(quality_db, 1)

        report = assert_completeness(quality_db)
        assert report.passed
        assert report.warnings
