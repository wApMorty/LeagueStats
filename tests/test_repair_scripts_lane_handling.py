"""Tests for the lane-aware repair pipeline in scripts/repair_data.py (issue #41).

Before this change, the repair scripts scraped a single untagged "default"
lane per champion, unlike scripts/update_all.py's nightly multi-lane
pipeline (dynamic lane discovery, one tagged page per played lane). These
tests verify the repair script now reuses the same
discover_lanes_for_champions() + group_champions_by_lane() helpers and, in
particular, that a champion played on several lanes gets a row for each
lane instead of the last lane's insert wiping the earlier ones (clearing a
champion's old rows must happen exactly once, not once per lane).

Both targets (matchups and synergies) share the pipeline and differ only by
their RepairTarget spec, so the multi-lane guard is asserted for each.
"""

import importlib
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

repair_data = importlib.import_module("repair_data")
MATCHUPS = repair_data.MATCHUPS
SYNERGIES = repair_data.SYNERGIES


@pytest.fixture
def logger():
    return logging.getLogger("test_repair_lane_handling")


class TestRepairMatchupsParallel:
    def test_single_lane_champion_scraped_once(self, logger):
        db = MagicMock()
        db.build_champion_cache.return_value = {"Jayce": 1, "Camille": 2}

        def fake_scrape(target, champion, patch_version, headless, lane):
            return champion, lane, [("Camille", 50.0, 0.0, 0.0, 15.0, 100)]

        with patch.object(repair_data, "_scrape_champion", side_effect=fake_scrape):
            groups = {"top": ["Jayce"]}
            stats = repair_data.repair_parallel(MATCHUPS, db, groups, "14", 2, True, logger)

        assert stats == {"success": 1, "failed": 0, "total": 1, "duration": pytest.approx(0, abs=5)}
        db.clear_matchups_for_champion.assert_called_once_with("Jayce", db.build_champion_cache())
        db.add_matchups_batch.assert_called_once_with(
            [("Jayce", "Camille", 50.0, 0.0, 0.0, 15.0, 100)],
            db.build_champion_cache(),
            lane="top",
        )

    def test_multi_lane_champion_cleared_once_and_all_lanes_inserted(self, logger):
        """Regression: a champion played on 2 lanes must not lose the first
        lane's data when the second lane's batch is written."""
        db = MagicMock()
        db.build_champion_cache.return_value = {"Pyke": 1, "Sylas": 2}

        def fake_scrape(target, champion, patch_version, headless, lane):
            return champion, lane, [("Sylas", 50.0, 0.0, 0.0, 10.0, 100)]

        with patch.object(repair_data, "_scrape_champion", side_effect=fake_scrape):
            groups = {"top": ["Pyke"], "support": ["Pyke"]}
            stats = repair_data.repair_parallel(MATCHUPS, db, groups, "14", 2, True, logger)

        assert stats["success"] == 1
        assert stats["failed"] == 0
        assert stats["total"] == 1
        # Cleared exactly once even though Pyke appears in two lane groups
        db.clear_matchups_for_champion.assert_called_once()
        # But inserted once per lane, each tagged correctly
        assert db.add_matchups_batch.call_count == 2
        inserted_lanes = {c.kwargs["lane"] for c in db.add_matchups_batch.call_args_list}
        assert inserted_lanes == {"top", "support"}

    def test_discovery_failure_fallback_lane_none(self, logger):
        db = MagicMock()
        db.build_champion_cache.return_value = {"Broken": 1, "Enemy": 2}

        def fake_scrape(target, champion, patch_version, headless, lane):
            return champion, lane, [("Enemy", 50.0, 0.0, 0.0, 10.0, 100)]

        with patch.object(repair_data, "_scrape_champion", side_effect=fake_scrape):
            groups = {None: ["Broken"]}
            stats = repair_data.repair_parallel(MATCHUPS, db, groups, "14", 2, True, logger)

        assert stats["success"] == 1
        db.add_matchups_batch.assert_called_once_with(
            [("Broken", "Enemy", 50.0, 0.0, 0.0, 10.0, 100)],
            db.build_champion_cache(),
            lane=None,
        )

    def test_champion_with_no_data_counts_as_failed(self, logger):
        db = MagicMock()
        db.build_champion_cache.return_value = {"NoData": 1}

        def fake_scrape(target, champion, patch_version, headless, lane):
            return champion, lane, []

        with patch.object(repair_data, "_scrape_champion", side_effect=fake_scrape):
            groups = {"top": ["NoData"]}
            stats = repair_data.repair_parallel(MATCHUPS, db, groups, "14", 2, True, logger)

        assert stats["success"] == 0
        assert stats["failed"] == 1
        db.clear_matchups_for_champion.assert_not_called()


class TestRepairSynergiesParallel:
    def test_multi_lane_champion_cleared_once_and_all_lanes_inserted(self, logger):
        db = MagicMock()
        db.build_champion_cache.return_value = {"Pyke": 1, "Sylas": 2}

        def fake_scrape(target, champion, patch_version, headless, lane):
            return champion, lane, [("Sylas", 50.0, 0.0, 0.0, 10.0, 100)]

        with patch.object(repair_data, "_scrape_champion", side_effect=fake_scrape):
            groups = {"top": ["Pyke"], "support": ["Pyke"]}
            stats = repair_data.repair_parallel(SYNERGIES, db, groups, "14", 2, True, logger)

        assert stats["success"] == 1
        assert stats["failed"] == 0
        # Synergy clear takes no champion cache (different Database signature)
        db.clear_synergies_for_champion.assert_called_once_with("Pyke")
        assert db.add_synergies_batch.call_count == 2
        inserted_lanes = {c.kwargs["lane"] for c in db.add_synergies_batch.call_args_list}
        assert inserted_lanes == {"top", "support"}


class TestTargetSpecs:
    def test_headless_defaults_preserved_per_target(self):
        """Matchups default to GUI (better Cloudflare bypass), synergies headless."""
        assert MATCHUPS.default_headless is False
        assert SYNERGIES.default_headless is True

    def test_detection_uses_target_table(self):
        db = MagicMock()
        db.connection.cursor.return_value.fetchall.return_value = [("Jayce",)]

        assert repair_data.detect_champions_without_data(db, SYNERGIES) == ["Jayce"]

        executed_sql = db.connection.cursor.return_value.execute.call_args[0][0]
        assert "LEFT JOIN synergies t" in executed_sql


class TestMainUsesLaneDiscovery:
    def test_main_calls_discovery_and_grouping(self, logger, monkeypatch):
        """main() must discover lanes and group by lane before repairing,
        instead of scraping every missing champion on an untagged default
        lane (the pre-fix behavior)."""
        fake_db = MagicMock()
        monkeypatch.setattr(repair_data, "Database", MagicMock(return_value=fake_db))
        monkeypatch.setattr(
            repair_data, "detect_champions_without_data", lambda db, target: ["Jayce"]
        )
        monkeypatch.setattr(repair_data, "detect_empty_champion_scores", lambda db: False)
        monkeypatch.setattr(
            sys, "argv", ["repair_data.py", "--target", "matchups", "--max-workers", "1"]
        )

        discovery_mock = MagicMock(return_value={"Jayce": ["top"]})
        monkeypatch.setattr(repair_data, "discover_lanes_for_champions", discovery_mock)

        repair_mock = MagicMock(
            return_value={"success": 1, "failed": 0, "total": 1, "duration": 0.1}
        )
        monkeypatch.setattr(repair_data, "repair_parallel", repair_mock)

        exit_code = repair_data.main()

        assert exit_code == 0
        discovery_mock.assert_called_once()
        repair_mock.assert_called_once()
        called_groups = repair_mock.call_args.kwargs["groups"]
        assert called_groups == {"top": ["Jayce"]}
        assert repair_mock.call_args.kwargs["target"] is MATCHUPS
