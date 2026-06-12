"""Tests for src/lane_discovery.py (Horizon 1 — multi-lane pipeline).

The HTML fixture reproduces the real LoLalytics SSR structure observed on
2026-06-12 (Qwik comments, lane icons with alt="X lane", share percentage
in a sibling div).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.lane_discovery import (
    LaneDiscoveryError,
    discover_lanes_for_champions,
    fetch_lane_distribution,
    parse_lane_distribution,
    select_lanes,
)

# Faithful excerpt of the SSR lane picker (Aatrox, 2026-06-12)
LANE_PICKER_HTML = """
<div class="flex h-[51px] w-[197px] gap-[3px] pt-[3px]" q:key="lf__aatrox_all">
<a href="/lol/aatrox/build/" class="h-[37px] w-[37px] border">
<img width="27" src="https://cdn5.lolalytics.com/lane27/top.webp" alt="top lane" class="m-auto" q:id="1j">
<div class="mt-[8px] text-center text-[9px]"><!--qv q:key=w2_1-->75.1%<!--/qv--></div></a>
<a href="/lol/aatrox/build/?lane=jungle" class="h-[37px] w-[37px] border">
<img width="27" src="https://cdn5.lolalytics.com/lane27/jungle.webp" alt="jungle lane" class="m-auto" q:id="1l">
<div class="mt-[8px] text-center text-[9px]"><!--qv q:key=w2_1-->22.0%<!--/qv--></div></a>
<a href="/lol/aatrox/build/?lane=middle" class="h-[37px] w-[37px] border">
<img width="27" src="https://cdn5.lolalytics.com/lane27/middle.webp" alt="middle lane" class="m-auto">
<div class="mt-[8px] text-center text-[9px]"><!--qv q:key=w2_1-->2.4%<!--/qv--></div></a>
<a href="/lol/aatrox/build/?lane=bottom" class="h-[37px] w-[37px] border">
<img width="27" src="https://cdn5.lolalytics.com/lane27/bottom.webp" alt="bottom lane" class="m-auto">
<div class="mt-[8px] text-center text-[9px]"><!--qv q:key=w2_1-->0.3%<!--/qv--></div></a>
<a href="/lol/aatrox/build/?lane=support" class="h-[37px] w-[37px] border">
<img width="27" src="https://cdn5.lolalytics.com/lane27/support.webp" alt="support lane" class="m-auto">
<div class="mt-[8px] text-center text-[9px]"><!--qv q:key=w2_1-->0.2%<!--/qv--></div></a>
</div>
"""


class TestParseLaneDistribution:
    def test_parses_all_five_lanes(self):
        distribution = parse_lane_distribution(LANE_PICKER_HTML)
        assert distribution == {
            "top": 75.1,
            "jungle": 22.0,
            "middle": 2.4,
            "bottom": 0.3,
            "support": 0.2,
        }

    def test_empty_html_returns_empty_dict(self):
        assert parse_lane_distribution("<html><body>nothing</body></html>") == {}

    def test_first_occurrence_wins(self):
        """The lane picker is the first lane-icon block; later blocks are ignored."""
        html = LANE_PICKER_HTML + LANE_PICKER_HTML.replace("75.1%", "1.0%")
        distribution = parse_lane_distribution(html)
        assert distribution["top"] == 75.1


class TestSelectLanes:
    def test_keeps_lanes_above_threshold_sorted_desc(self):
        distribution = {"top": 75.1, "jungle": 22.0, "middle": 2.4}
        assert select_lanes(distribution, threshold=10.0) == ["top", "jungle"]

    def test_single_lane_champion(self):
        distribution = {"top": 1.2, "jungle": 96.0, "middle": 1.0}
        assert select_lanes(distribution, threshold=10.0) == ["jungle"]

    def test_degenerate_distribution_falls_back_to_best_lane(self):
        """Never return zero lanes for a champion that has data."""
        distribution = {"top": 8.0, "jungle": 5.0}
        assert select_lanes(distribution, threshold=10.0) == ["top"]

    def test_empty_distribution_returns_empty(self):
        assert select_lanes({}, threshold=10.0) == []

    def test_default_threshold_from_config(self):
        distribution = {"top": 50.0, "jungle": 10.0}  # 10.0 is NOT > 10.0
        assert select_lanes(distribution) == ["top"]


class TestFetchLaneDistribution:
    def _mock_session(self, status_code=200, text=LANE_PICKER_HTML):
        session = MagicMock()
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        session.get.return_value = response
        return session

    def test_success(self):
        session = self._mock_session()
        distribution = fetch_lane_distribution("aatrox", "14", session)
        assert distribution["top"] == 75.1

        url = session.get.call_args[0][0]
        assert url == "https://lolalytics.com/lol/aatrox/build/?tier=diamond_plus&patch=14"

    def test_http_error_raises(self):
        session = self._mock_session(status_code=403)
        with pytest.raises(LaneDiscoveryError, match="HTTP 403"):
            fetch_lane_distribution.__wrapped__("aatrox", "14", session)

    def test_dom_change_raises_loudly(self):
        """If LoLalytics changes the DOM, fail with a runbook pointer (not silently)."""
        session = self._mock_session(text="<html>new design</html>")
        with pytest.raises(LaneDiscoveryError, match="runbook_scraping"):
            fetch_lane_distribution.__wrapped__("aatrox", "14", session)


class TestDiscoverLanesForChampions:
    def test_discovery_with_failures_maps_to_empty(self):
        def fake_fetch(champion, patch, session=None):
            if champion == "brokenchamp":
                raise LaneDiscoveryError("DOM changed")
            return {"top": 60.0, "middle": 35.0, "support": 5.0}

        with patch("src.lane_discovery.fetch_lane_distribution", side_effect=fake_fetch):
            results = discover_lanes_for_champions(
                ["Aatrox", "BrokenChamp"], "14", normalize_func=str.lower, max_workers=2
            )

        assert results["Aatrox"] == ["top", "middle"]
        assert results["BrokenChamp"] == []
