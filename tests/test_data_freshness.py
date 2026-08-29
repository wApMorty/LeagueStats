"""Tests for src/data_freshness.py (Horizon 1 — freshness guard-rail)."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.config_constants import data_quality_config
from src.data_freshness import FreshnessInfo, format_freshness_banner, get_freshness_info


def make_db(
    path,
    last_update_utc=None,
    last_scrape_utc=None,
    last_scrape_status=None,
    with_meta_table=True,
    matchups=100,
    synergies=50,
):
    """Create a minimal database for freshness tests."""
    conn = sqlite3.connect(str(path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE matchups (id INTEGER PRIMARY KEY)")
    cursor.execute("CREATE TABLE synergies (id INTEGER PRIMARY KEY)")
    cursor.executemany("INSERT INTO matchups DEFAULT VALUES", [()] * matchups)
    cursor.executemany("INSERT INTO synergies DEFAULT VALUES", [()] * synergies)
    if with_meta_table:
        cursor.execute("CREATE TABLE db_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if last_update_utc:
            cursor.execute(
                "INSERT INTO db_meta (key, value) VALUES ('last_update_utc', ?)",
                (last_update_utc,),
            )
        if last_scrape_utc:
            cursor.execute(
                "INSERT INTO db_meta (key, value) VALUES ('last_scrape_utc', ?)",
                (last_scrape_utc,),
            )
        if last_scrape_status:
            cursor.execute(
                "INSERT INTO db_meta (key, value) VALUES ('last_scrape_status', ?)",
                (last_scrape_status,),
            )
    conn.commit()
    conn.close()


class TestGetFreshnessInfo:
    def test_fresh_database_from_db_meta(self, tmp_path):
        db_path = tmp_path / "fresh.db"
        now = datetime.now(timezone.utc)
        make_db(db_path, last_update_utc=now.isoformat())

        info = get_freshness_info(str(db_path))

        assert info.source == "db_meta"
        assert info.age_days < 0.01
        assert not info.is_stale
        assert info.matchups_count == 100
        assert info.synergies_count == 50

    def test_prefers_last_scrape_utc_over_last_update_utc(self, tmp_path):
        """SPEC-01 A3: last_scrape_utc is the authoritative freshness key;
        last_update_utc is only a legacy fallback."""
        db_path = tmp_path / "fresh.db"
        now = datetime.now(timezone.utc)
        stale = now - timedelta(days=30)
        make_db(db_path, last_update_utc=stale.isoformat(), last_scrape_utc=now.isoformat())

        info = get_freshness_info(str(db_path))

        assert info.age_days < 0.01

    def test_falls_back_to_last_update_utc_when_no_last_scrape_utc(self, tmp_path):
        """Bases written before A3 only have last_update_utc."""
        db_path = tmp_path / "legacy.db"
        now = datetime.now(timezone.utc)
        make_db(db_path, last_update_utc=now.isoformat())

        info = get_freshness_info(str(db_path))

        assert info.source == "db_meta"
        assert info.age_days < 0.01

    def test_reads_scrape_status(self, tmp_path):
        db_path = tmp_path / "partial.db"
        now = datetime.now(timezone.utc)
        make_db(db_path, last_scrape_utc=now.isoformat(), last_scrape_status="partial")

        info = get_freshness_info(str(db_path))

        assert info.scrape_status == "partial"

    def test_stale_database(self, tmp_path):
        db_path = tmp_path / "stale.db"
        old = datetime.now(timezone.utc) - timedelta(days=12)
        make_db(db_path, last_update_utc=old.isoformat())

        info = get_freshness_info(str(db_path))

        assert info.is_stale
        assert 11.9 < info.age_days < 12.1

    def test_database_without_meta_has_unknown_freshness(self, tmp_path):
        """SPEC-01 A3: the mtime fallback is removed — db.db is rewritten on
        every session (pools, bans), so its mtime tracked the last *open*,
        not the last update, and silently hid six weeks of stale data in the
        2026-08 incident. Without db_meta, freshness is unknown, not
        estimated."""
        db_path = tmp_path / "old.db"
        make_db(db_path, with_meta_table=False)

        info = get_freshness_info(str(db_path))

        assert info.last_update is None
        assert info.is_stale

    def test_missing_database_is_unknown_and_stale(self, tmp_path):
        info = get_freshness_info(str(tmp_path / "nope.db"))
        assert info.source == "unknown"
        assert info.last_update is None
        assert info.is_stale


class TestFormatFreshnessBanner:
    def test_fresh_banner(self):
        info = FreshnessInfo(
            last_update=datetime.now(timezone.utc) - timedelta(hours=5),
            source="db_meta",
            matchups_count=40753,
            synergies_count=30668,
        )
        banner = format_freshness_banner(info)
        assert banner.startswith("[OK]")
        assert "40 753" in banner
        assert "5 h" in banner

    def test_stale_banner_warns_with_action(self):
        info = FreshnessInfo(
            last_update=datetime.now(timezone.utc) - timedelta(days=11),
            source="db_meta",
            matchups_count=16179,
            synergies_count=12943,
        )
        banner = format_freshness_banner(info)
        assert "OBSOLÈTES" in banner
        assert str(data_quality_config.FRESHNESS_WARNING_DAYS) in banner
        assert "update_all.py" in banner

    def test_unknown_banner(self):
        banner = format_freshness_banner(FreshnessInfo())
        assert "INCONNUE" in banner
        assert "update_all.py" in banner

    def test_partial_scrape_status_adds_warning_line(self):
        info = FreshnessInfo(
            last_update=datetime.now(timezone.utc) - timedelta(hours=5),
            source="db_meta",
            matchups_count=40753,
            synergies_count=30668,
            scrape_status="partial",
        )
        banner = format_freshness_banner(info)
        assert banner.startswith("[OK]")
        assert "incomplet" in banner
        assert "partial" in banner

    def test_ok_scrape_status_has_no_extra_warning(self):
        info = FreshnessInfo(
            last_update=datetime.now(timezone.utc) - timedelta(hours=5),
            source="db_meta",
            matchups_count=40753,
            synergies_count=30668,
            scrape_status="ok",
        )
        assert "incomplet" not in format_freshness_banner(info)
