"""Tests for src/data_freshness.py (Horizon 1 — freshness guard-rail)."""

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from src.config_constants import data_quality_config
from src.data_freshness import FreshnessInfo, format_freshness_banner, get_freshness_info


def make_db(path, last_update_utc=None, with_meta_table=True, matchups=100, synergies=50):
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

    def test_stale_database(self, tmp_path):
        db_path = tmp_path / "stale.db"
        old = datetime.now(timezone.utc) - timedelta(days=12)
        make_db(db_path, last_update_utc=old.isoformat())

        info = get_freshness_info(str(db_path))

        assert info.is_stale
        assert 11.9 < info.age_days < 12.1

    def test_pre_migration_db_falls_back_to_mtime(self, tmp_path):
        """Databases without db_meta (pre-b7e41c9a3f02) must still report an age."""
        db_path = tmp_path / "old.db"
        make_db(db_path, with_meta_table=False)

        info = get_freshness_info(str(db_path))

        assert info.source == "file_mtime"
        assert info.last_update is not None
        assert not info.is_stale  # file was just created

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
        assert "INTROUVABLES" in banner
        assert "update_all.py" in banner

    def test_mtime_source_is_flagged_as_estimate(self):
        info = FreshnessInfo(
            last_update=datetime.now(timezone.utc) - timedelta(days=2),
            source="file_mtime",
            matchups_count=100,
            synergies_count=50,
        )
        assert "estimé" in format_freshness_banner(info)
