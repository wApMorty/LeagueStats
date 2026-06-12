"""Tests for src/multilane.py (Horizon 1 — multi-lane orchestration)."""

from unittest.mock import MagicMock, call, patch

from src.multilane import group_champions_by_lane, scrape_all_multilane


class TestGroupChampionsByLane:
    def test_inverts_champion_lanes_mapping(self):
        lane_map = {
            "Aatrox": ["top", "jungle"],
            "Caitlyn": ["bottom"],
            "Pyke": ["support"],
        }
        groups = group_champions_by_lane(lane_map)

        assert groups["top"] == ["Aatrox"]
        assert groups["jungle"] == ["Aatrox"]
        assert groups["bottom"] == ["Caitlyn"]
        assert groups["support"] == ["Pyke"]
        assert None not in groups  # no discovery failures
        assert "middle" not in groups  # empty lanes are dropped

    def test_discovery_failures_grouped_under_none(self):
        groups = group_champions_by_lane({"Aatrox": ["top"], "Broken": []})
        assert groups[None] == ["Broken"]

    def test_champions_sorted_within_lane(self):
        groups = group_champions_by_lane({"Zed": ["middle"], "Ahri": ["middle"]})
        assert groups["middle"] == ["Ahri", "Zed"]


class TestScrapeAllMultilane:
    def _make_db(self, champions):
        db = MagicMock()
        db.create_riot_champions_table.return_value = True
        db.get_all_champion_names.return_value = dict(enumerate(champions))
        return db

    def _make_parser(self):
        parser = MagicMock()
        parser.patch_version = "14"
        parser.parse_champions_by_role.return_value = {"success": 1, "failed": 0, "total": 1}
        parser.parse_synergies_by_role.return_value = {"success": 1, "failed": 0, "total": 1}
        return parser

    def test_tables_initialized_once_then_per_lane_scrapes(self):
        db = self._make_db(["Aatrox", "Caitlyn"])
        parser = self._make_parser()
        lane_map = {"Aatrox": ["top"], "Caitlyn": ["bottom"]}

        with patch("src.multilane.discover_lanes_for_champions", return_value=lane_map):
            stats = scrape_all_multilane(db, parser, str.lower)

        # Tables reset exactly once for the whole run
        db.update_champions_from_riot_api.assert_called_once()
        db.init_matchups_table.assert_called_once()
        db.init_synergies_table.assert_called_once()

        # One scrape pass per non-empty lane, never re-initializing tables
        matchup_calls = parser.parse_champions_by_role.call_args_list
        assert call(db, ["Aatrox"], "top", str.lower, init_tables=False) in matchup_calls
        assert call(db, ["Caitlyn"], "bottom", str.lower, init_tables=False) in matchup_calls
        assert all(c.kwargs["init_tables"] is False for c in matchup_calls)

        assert stats["success"] == 4  # 2 lanes x (matchups + synergies)
        assert stats["failed"] == 0
        assert stats["discovery_failures"] == []

    def test_discovery_failure_falls_back_to_default_lane(self):
        db = self._make_db(["Broken"])
        parser = self._make_parser()

        with patch("src.multilane.discover_lanes_for_champions", return_value={"Broken": []}):
            stats = scrape_all_multilane(db, parser, str.lower)

        parser.parse_champions_by_role.assert_called_once_with(
            db, ["Broken"], None, str.lower, init_tables=False
        )
        assert stats["discovery_failures"] == ["Broken"]

    def test_synergies_can_be_skipped(self):
        db = self._make_db(["Aatrox"])
        parser = self._make_parser()

        with patch("src.multilane.discover_lanes_for_champions", return_value={"Aatrox": ["top"]}):
            stats = scrape_all_multilane(db, parser, str.lower, include_synergies=False)

        db.init_synergies_table.assert_not_called()
        parser.parse_synergies_by_role.assert_not_called()
        assert stats["synergies"] == {}
        assert stats["pages_total"] == 1

    def test_multi_lane_champion_scraped_on_each_lane(self):
        db = self._make_db(["Aatrox"])
        parser = self._make_parser()

        with patch(
            "src.multilane.discover_lanes_for_champions",
            return_value={"Aatrox": ["top", "jungle"]},
        ):
            stats = scrape_all_multilane(db, parser, str.lower, include_synergies=False)

        lanes_scraped = [c.args[2] for c in parser.parse_champions_by_role.call_args_list]
        assert sorted(lanes_scraped) == ["jungle", "top"]
        assert stats["pages_total"] == 2
