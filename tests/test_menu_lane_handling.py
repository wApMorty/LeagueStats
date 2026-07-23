"""Tests for the main menu's lane-aware parsing (issue #41 follow-up).

The "Parse Match Statistics" menu (src/ui/lol_coach_legacy.py, reached from
the main menu option 3) used to hardcode lane="top" for every pool-scoped
scrape (parse_champion_pool, parse_synergies_pool, parse_all_data_pool) --
so selecting e.g. "All Jungle Champions" would tag every matchup/synergy row
as if it had been scraped on the top lane. The "All Champions" variants
(parse_all_champions, parse_synergies_all, parse_all_data_all) scraped an
untagged default lane instead. Both are now routed through
_scrape_by_discovered_lane(), which reuses discover_lanes_for_champions() +
group_champions_by_lane() -- the same dynamic lane detection as
scripts/update_all.py and the repair scripts.
"""

from unittest.mock import MagicMock

import pytest

from src.ui import lol_coach_legacy


class TestScrapeByDiscoveredLane:
    def test_aggregates_stats_across_lane_groups(self, monkeypatch):
        def fake_role_fn(champs, lane):
            return {"success": len(champs), "failed": 0, "total": len(champs)}

        monkeypatch.setattr(
            "src.lane_discovery.discover_lanes_for_champions",
            lambda champs, patch, normalize_func: {"LeeSin": ["jungle"], "Caitlyn": ["bottom"]},
        )

        stats = lol_coach_legacy._scrape_by_discovered_lane(
            ["LeeSin", "Caitlyn"], "14", str.lower, fake_role_fn
        )

        assert stats == {"success": 2, "failed": 0, "total": 2}

    def test_role_fn_receives_discovered_lane_not_hardcoded_top(self, monkeypatch):
        seen_lanes = []

        def fake_role_fn(champs, lane):
            seen_lanes.append(lane)
            return {"success": len(champs), "failed": 0, "total": len(champs)}

        monkeypatch.setattr(
            "src.lane_discovery.discover_lanes_for_champions",
            lambda champs, patch, normalize_func: {"LeeSin": ["jungle"]},
        )

        lol_coach_legacy._scrape_by_discovered_lane(["LeeSin"], "14", str.lower, fake_role_fn)

        assert seen_lanes == ["jungle"]
        assert "top" not in seen_lanes

    def test_discovery_failure_falls_back_to_default_lane(self, monkeypatch):
        seen_lanes = []

        def fake_role_fn(champs, lane):
            seen_lanes.append(lane)
            return {"success": 0, "failed": len(champs), "total": len(champs)}

        monkeypatch.setattr(
            "src.lane_discovery.discover_lanes_for_champions",
            lambda champs, patch, normalize_func: {"Broken": []},
        )

        lol_coach_legacy._scrape_by_discovered_lane(["Broken"], "14", str.lower, fake_role_fn)

        assert seen_lanes == [None]


def _setup_menu_mocks(monkeypatch, discovered_lane):
    """Common wiring for the parse_* menu functions: DB, ParallelParser,
    Assistant, and lane discovery mocked; user always confirms."""
    fake_db = MagicMock()
    fake_db.connection.cursor.return_value.fetchone.return_value = [5]
    monkeypatch.setattr(lol_coach_legacy, "Database", MagicMock(return_value=fake_db))
    monkeypatch.setattr("builtins.input", lambda *_args: "y")

    fake_assistant = MagicMock()
    fake_assistant.calculate_global_scores.return_value = 2
    fake_assistant.precalculate_all_custom_pool_bans.return_value = {}
    monkeypatch.setattr(lol_coach_legacy, "Assistant", MagicMock(return_value=fake_assistant))

    monkeypatch.setattr(
        "src.lane_discovery.discover_lanes_for_champions",
        lambda champs, patch, normalize_func: {c: [discovered_lane] for c in champs},
    )

    fake_parser = MagicMock()
    seen_matchup_lanes = []
    seen_synergy_lanes = []

    def fake_matchups(db, champs, lane, normalize_func, init_tables=True):
        seen_matchup_lanes.append(lane)
        return {"success": len(champs), "failed": 0, "total": len(champs)}

    def fake_synergies(db, champs, lane, normalize_func, init_tables=True):
        seen_synergy_lanes.append(lane)
        return {"success": len(champs), "failed": 0, "total": len(champs)}

    fake_parser.parse_champions_by_role.side_effect = fake_matchups
    fake_parser.parse_synergies_by_role.side_effect = fake_synergies
    monkeypatch.setattr(lol_coach_legacy, "ParallelParser", MagicMock(return_value=fake_parser))

    return fake_db, seen_matchup_lanes, seen_synergy_lanes


class TestParseChampionPoolUsesRealLane:
    def test_jungle_pool_tagged_jungle_not_hardcoded_top(self, monkeypatch):
        monkeypatch.setattr(
            lol_coach_legacy,
            "_select_pool_for_parsing",
            lambda: ("All Jungle Champions", ["LeeSin", "Vi"]),
        )
        _fake_db, seen_matchup_lanes, _ = _setup_menu_mocks(monkeypatch, "jungle")

        lol_coach_legacy.parse_champion_pool(patch_version="14")

        assert seen_matchup_lanes == ["jungle"]
        assert "top" not in seen_matchup_lanes


class TestParseSynergiesPoolUsesRealLane:
    def test_support_pool_tagged_support_not_hardcoded_top(self, monkeypatch):
        monkeypatch.setattr(
            lol_coach_legacy,
            "_select_pool_for_parsing",
            lambda: ("All Support Champions", ["Thresh", "Lulu"]),
        )
        _fake_db, _, seen_synergy_lanes = _setup_menu_mocks(monkeypatch, "support")

        lol_coach_legacy.parse_synergies_pool(patch_version="14")

        assert seen_synergy_lanes == ["support"]
        assert "top" not in seen_synergy_lanes


class TestParseAllDataPoolUsesRealLane:
    def test_adc_pool_tags_matchups_and_synergies_bottom_not_hardcoded_top(self, monkeypatch):
        monkeypatch.setattr(
            lol_coach_legacy,
            "_select_pool_for_parsing",
            lambda: ("All ADC Champions", ["Jinx", "Caitlyn"]),
        )
        _fake_db, seen_matchup_lanes, seen_synergy_lanes = _setup_menu_mocks(monkeypatch, "bottom")

        lol_coach_legacy.parse_all_data_pool(patch_version="14")

        assert seen_matchup_lanes == ["bottom"]
        assert seen_synergy_lanes == ["bottom"]
        assert "top" not in seen_matchup_lanes
        assert "top" not in seen_synergy_lanes
