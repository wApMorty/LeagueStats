"""Tests for the lane-aware repair pipeline in scripts/repair_matchups.py and
scripts/repair_synergies.py (issue #41).

Before this change, the repair scripts scraped a single untagged "default"
lane per champion, unlike scripts/update_all.py's nightly multi-lane
pipeline (dynamic lane discovery, one tagged page per played lane). These
tests verify the repair scripts now reuse the same
discover_lanes_for_champions() + group_champions_by_lane() helpers and, in
particular, that a champion played on several lanes gets a row for each
lane instead of the last lane's insert wiping the earlier ones (clearing a
champion's old rows must happen exactly once, not once per lane).
"""

import importlib
import logging
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

repair_matchups = importlib.import_module("repair_matchups")
repair_synergies = importlib.import_module("repair_synergies")


@pytest.fixture
def logger():
    return logging.getLogger("test_repair_lane_handling")


class TestRepairMatchupsParallel:
    def test_single_lane_champion_scraped_once(self, logger):
        db = MagicMock()
        db.build_champion_cache.return_value = {"Jayce": 1, "Camille": 2}

        def fake_scrape(champion, patch_version, headless, lane):
            return champion, lane, [("Camille", 50.0, 0.0, 0.0, 15.0, 100)]

        with patch.object(repair_matchups, "_scrape_champion_matchups", side_effect=fake_scrape):
            groups = {"top": ["Jayce"]}
            stats = repair_matchups.repair_matchups_parallel(db, groups, "14", 2, True, logger)

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

        def fake_scrape(champion, patch_version, headless, lane):
            return champion, lane, [("Sylas", 50.0, 0.0, 0.0, 10.0, 100)]

        with patch.object(repair_matchups, "_scrape_champion_matchups", side_effect=fake_scrape):
            groups = {"top": ["Pyke"], "support": ["Pyke"]}
            stats = repair_matchups.repair_matchups_parallel(db, groups, "14", 2, True, logger)

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

        def fake_scrape(champion, patch_version, headless, lane):
            return champion, lane, [("Enemy", 50.0, 0.0, 0.0, 10.0, 100)]

        with patch.object(repair_matchups, "_scrape_champion_matchups", side_effect=fake_scrape):
            groups = {None: ["Broken"]}
            stats = repair_matchups.repair_matchups_parallel(db, groups, "14", 2, True, logger)

        assert stats["success"] == 1
        db.add_matchups_batch.assert_called_once_with(
            [("Broken", "Enemy", 50.0, 0.0, 0.0, 10.0, 100)],
            db.build_champion_cache(),
            lane=None,
        )

    def test_champion_with_no_data_counts_as_failed(self, logger):
        db = MagicMock()
        db.build_champion_cache.return_value = {"NoData": 1}

        def fake_scrape(champion, patch_version, headless, lane):
            return champion, lane, []

        with patch.object(repair_matchups, "_scrape_champion_matchups", side_effect=fake_scrape):
            groups = {"top": ["NoData"]}
            stats = repair_matchups.repair_matchups_parallel(db, groups, "14", 2, True, logger)

        assert stats["success"] == 0
        assert stats["failed"] == 1
        db.clear_matchups_for_champion.assert_not_called()


class TestRepairSynergiesParallel:
    def test_multi_lane_champion_cleared_once_and_all_lanes_inserted(self, logger):
        db = MagicMock()
        db.build_champion_cache.return_value = {"Pyke": 1, "Sylas": 2}

        def fake_scrape(champion, patch_version, headless, lane):
            return champion, lane, [("Sylas", 50.0, 0.0, 0.0, 10.0, 100)]

        with patch.object(repair_synergies, "_scrape_champion_synergies", side_effect=fake_scrape):
            groups = {"top": ["Pyke"], "support": ["Pyke"]}
            stats = repair_synergies.repair_synergies_parallel(db, groups, "14", 2, True, logger)

        assert stats["success"] == 1
        assert stats["failed"] == 0
        db.clear_synergies_for_champion.assert_called_once_with("Pyke")
        assert db.add_synergies_batch.call_count == 2
        inserted_lanes = {c.kwargs["lane"] for c in db.add_synergies_batch.call_args_list}
        assert inserted_lanes == {"top", "support"}


class TestMainUsesLaneDiscovery:
    def test_repair_matchups_main_calls_discovery_and_grouping(self, logger, monkeypatch):
        """main() must discover lanes and group by lane before repairing,
        instead of scraping every missing champion on an untagged default
        lane (the pre-fix behavior)."""
        fake_db = MagicMock()
        monkeypatch.setattr(repair_matchups, "Database", MagicMock(return_value=fake_db))
        monkeypatch.setattr(
            repair_matchups, "detect_champions_without_matchups", lambda db: ["Jayce"]
        )
        monkeypatch.setattr(repair_matchups, "detect_empty_champion_scores", lambda db: False)
        monkeypatch.setattr(sys, "argv", ["repair_matchups.py", "--max-workers", "1"])

        discovery_mock = MagicMock(return_value={"Jayce": ["top"]})
        monkeypatch.setattr(repair_matchups, "discover_lanes_for_champions", discovery_mock)

        repair_mock = MagicMock(
            return_value={"success": 1, "failed": 0, "total": 1, "duration": 0.1}
        )
        monkeypatch.setattr(repair_matchups, "repair_matchups_parallel", repair_mock)

        exit_code = repair_matchups.main()

        assert exit_code == 0
        discovery_mock.assert_called_once()
        repair_mock.assert_called_once()
        called_groups = repair_mock.call_args.kwargs["groups"]
        assert called_groups == {"top": ["Jayce"]}
