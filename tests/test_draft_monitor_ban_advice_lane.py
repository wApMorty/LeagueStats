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

    def test_custom_pool_uses_the_lcu_assigned_position(self, monitor):
        """SPEC-18 §4 : pool sans rôle -> le poste assigné par le client."""
        monitor.pool_lane = None
        state = DraftState(local_player_cell_id=2, ally_positions={2: "top"})

        monitor.ban_advisor._recommendations(state)

        kwargs = monitor.assistant.get_ban_recommendations.call_args.kwargs
        assert kwargs["lane"] == "top"

    def test_custom_pool_without_position_uses_its_dominant_lane(self, monitor):
        """SPEC-18 §4 : ni rôle ni poste -> la lane où la pool est le plus
        jouée. Avant : toutes lanes agrégées, et un pool de tanks top se
        voyait conseiller de bannir des ADC."""
        monitor.pool_lane = None
        monitor.last_draft_state = None
        monitor.assistant.db.get_lane_distributions_by_name.return_value = {
            "aatrox": {"top": 0.9, "middle": 0.1}
        }

        monitor._show_ban_recommendations_draft()

        kwargs = monitor.assistant.get_ban_recommendations.call_args.kwargs
        assert kwargs["lane"] == "top"

    def test_precalculated_bans_ignored_for_a_pool_without_role(self, monitor):
        """Les bans précalculés d'un pool sans rôle ne connaissent pas la lane
        jouée : on recalcule."""
        monitor.pool_lane = None
        monitor.last_draft_state = None
        monitor.assistant.db.get_lane_distributions_by_name.return_value = {}
        monitor.assistant.db.get_pool_ban_recommendations.return_value = [
            ("Jinx", 9.0, -1.0, "Aatrox", 1)
        ]

        monitor._show_ban_recommendations_draft()

        monitor.assistant.db.get_pool_ban_recommendations.assert_not_called()
        monitor.assistant.get_ban_recommendations.assert_called_once()
