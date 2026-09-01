"""Tests for the main menu's lane-aware parsing (issue #41 follow-up, SPEC-01 A2).

The "Parse Match Statistics" menu (src/ui/data_update_ui.py, reached from
the main menu option 3) used to hardcode lane="top" for every pool-scoped
scrape -- so selecting e.g. "All Jungle Champions" would tag every
matchup/synergy row as if it had been scraped on the top lane.

Since SPEC-01 A2, every menu-triggered parse (pool-scoped or full-roster)
goes through src.pipeline.run_pipeline() -> src.multilane.scrape_all_multilane(),
the same dynamic lane detection used by scripts/update_all.py and the repair
scripts. These tests confirm the menu wiring still passes the pool's real
champions through to that shared pipeline and that lane tagging is not
hardcoded anywhere in the menu layer.
"""

from unittest.mock import MagicMock, patch

from src.ui import data_update_ui


def _setup_pipeline_mocks(monkeypatch, discovered_lane):
    """Wire src.pipeline's dependencies so run_pipeline() runs end to end
    against fakes, and record which lane each scrape call used."""
    fake_db = MagicMock()
    fake_db.connection.cursor.return_value.fetchone.return_value = [5]
    monkeypatch.setattr("src.pipeline.Database", MagicMock(return_value=fake_db))
    monkeypatch.setattr("src.pipeline.Notifier", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr("builtins.input", lambda *_args: "y")

    fake_assistant = MagicMock()
    fake_assistant.calculate_global_scores.return_value = 2
    fake_assistant.precalculate_all_custom_pool_bans.return_value = {}
    monkeypatch.setattr("src.assistant.Assistant", MagicMock(return_value=fake_assistant))

    monkeypatch.setattr(
        "src.multilane.discover_lanes_for_champions",
        lambda champs, patch, normalize_func, **kwargs: {c: [discovered_lane] for c in champs},
    )

    fake_parser = MagicMock()
    fake_parser.patch_version = "14"
    seen_matchup_lanes = []
    seen_synergy_lanes = []

    def fake_parse_page_by_role(
        db,
        champs,
        lane,
        normalize_func,
        include_matchups=True,
        include_synergies=True,
        init_tables=True,
    ):
        # SPEC-02: one page visit covers both datasets; record the lane on
        # whichever side(s) the caller actually asked for, mirroring
        # scrape_all_multilane()'s stats["matchups"]/stats["synergies"] gating.
        if include_matchups:
            seen_matchup_lanes.append(lane)
        if include_synergies:
            seen_synergy_lanes.append(lane)
        return {
            "success": len(champs),
            "failed": 0,
            "total": len(champs),
            "synergies_missing": [],
        }

    fake_parser.parse_page_by_role.side_effect = fake_parse_page_by_role
    monkeypatch.setattr("src.pipeline.ParallelParser", MagicMock(return_value=fake_parser))

    return fake_db, seen_matchup_lanes, seen_synergy_lanes


class TestParseChampionPoolUsesRealLane:
    def test_jungle_pool_tagged_jungle_not_hardcoded_top(self, monkeypatch):
        monkeypatch.setattr(
            data_update_ui,
            "_select_pool_for_parsing",
            lambda: ("All Jungle Champions", ["LeeSin", "Vi"]),
        )
        _fake_db, seen_matchup_lanes, _ = _setup_pipeline_mocks(monkeypatch, "jungle")

        data_update_ui.parse_champion_pool(patch_version="14")

        assert seen_matchup_lanes == ["jungle"]
        assert "top" not in seen_matchup_lanes


class TestParseSynergiesPoolUsesRealLane:
    def test_support_pool_tagged_support_not_hardcoded_top(self, monkeypatch):
        monkeypatch.setattr(
            data_update_ui,
            "_select_pool_for_parsing",
            lambda: ("All Support Champions", ["Thresh", "Lulu"]),
        )
        _fake_db, _, seen_synergy_lanes = _setup_pipeline_mocks(monkeypatch, "support")

        data_update_ui.parse_synergies_pool(patch_version="14")

        assert seen_synergy_lanes == ["support"]
        assert "top" not in seen_synergy_lanes


class TestParseAllDataPoolUsesRealLane:
    def test_adc_pool_tags_matchups_and_synergies_bottom_not_hardcoded_top(self, monkeypatch):
        monkeypatch.setattr(
            data_update_ui,
            "_select_pool_for_parsing",
            lambda: ("All ADC Champions", ["Jinx", "Caitlyn"]),
        )
        _fake_db, seen_matchup_lanes, seen_synergy_lanes = _setup_pipeline_mocks(
            monkeypatch, "bottom"
        )

        data_update_ui.parse_all_data_pool(patch_version="14")

        assert seen_matchup_lanes == ["bottom"]
        assert seen_synergy_lanes == ["bottom"]
        assert "top" not in seen_matchup_lanes
        assert "top" not in seen_synergy_lanes


class TestPoolScopedRunPassesRestrictedChampionList:
    def test_pool_champions_forwarded_not_full_roster(self, monkeypatch):
        """The pool's champions -- not the full roster -- must reach
        scrape_all_multilane(), otherwise a pool-scoped parse would refresh
        and re-tag every champion in the database."""
        monkeypatch.setattr(
            data_update_ui,
            "_select_pool_for_parsing",
            lambda: ("All Jungle Champions", ["LeeSin", "Vi"]),
        )
        _setup_pipeline_mocks(monkeypatch, "jungle")

        with patch("src.pipeline.scrape_all_multilane") as mock_scrape:
            mock_scrape.return_value = {
                "lane_map": {},
                "discovery_failures": [],
                "pages_total": 2,
                "matchups": {"jungle": {"success": 2, "failed": 0, "total": 2}},
                "synergies": {},
                "success": 2,
                "failed": 0,
                "total": 2,
            }
            data_update_ui.parse_champion_pool(patch_version="14")

        assert mock_scrape.call_args.kwargs["champions"] == ["LeeSin", "Vi"]
