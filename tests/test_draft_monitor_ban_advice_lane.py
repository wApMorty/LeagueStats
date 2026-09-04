"""Regression (audit 2026-09-04): the Live Coach's 3 ban screens never
passed the selected pool's lane down to BanRecommender, blending every lane
a champion has ever played into the threat score -- same bug class as fix
#46 / the final_analysis.py lane fix, applied to bans instead of matchups.

``DraftMonitor.pool_lane`` (set by ``PoolSelector`` from
``pool_manager.pool_role_to_lane(pool.role)``) must reach the real-time
fallback call to ``Assistant.get_ban_recommendations`` in all 3
``BanAdvisor`` methods.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft.state import DraftState
from src.draft_monitor import DraftMonitor


@pytest.fixture
def monitor():
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            monitor = DraftMonitor(verbose=False, auto_hover=False)

    monitor.pool_name = "TopPool"
    monitor.pool_lane = "top"
    monitor.current_pool = ["Aatrox"]
    monitor._get_display_name = Mock(return_value="Enemy1")

    # No pre-calculated bans in DB -> forces the real-time fallback path.
    monitor.assistant.db.get_pool_ban_recommendations.return_value = []
    monitor.assistant.get_ban_recommendations.return_value = [("Darius", 5.0, -2.0, "Aatrox", 10)]
    return monitor


class TestBanAdvisorLaneWiring:
    def test_auto_ban_hover_passes_pool_lane(self, monitor):
        monitor._is_player_ban_turn = Mock(return_value=True)
        monitor._auto_hover_champion = Mock(return_value=True)

        monitor._handle_auto_ban_hover(DraftState())

        kwargs = monitor.assistant.get_ban_recommendations.call_args.kwargs
        assert kwargs["lane"] == "top"

    def test_show_ban_recommendations_draft_passes_pool_lane(self, monitor):
        monitor._show_ban_recommendations_draft()

        kwargs = monitor.assistant.get_ban_recommendations.call_args.kwargs
        assert kwargs["lane"] == "top"

    def test_adaptive_ban_recommendations_pass_pool_lane(self, monitor):
        monitor._show_adaptive_ban_recommendations(DraftState(enemy_picks=[100]))

        kwargs = monitor.assistant.get_ban_recommendations.call_args.kwargs
        assert kwargs["lane"] == "top"

    def test_missing_pool_lane_falls_back_to_unfiltered_behaviour(self, monitor):
        """No lane info (custom multi-role pool, or legacy pool selection)
        -> lane=None, identical to the pre-fix behaviour."""
        monitor.pool_lane = None

        monitor._show_ban_recommendations_draft()

        kwargs = monitor.assistant.get_ban_recommendations.call_args.kwargs
        assert kwargs["lane"] is None
