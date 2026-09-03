"""Regression test — Live Coach recommendations mixed a multi-lane champion's
off-role matchups into the score/volume shown for the lane actually played.

Bug report (2026-09-03): user saw implausibly high "games" counts on Live
Coach recommendations and suspected the tier filter (Master+) was broken.
Investigation showed the tier filter was correct; the real cause was
DraftRecommender.provide() calling get_matchups_for_draft(champion_name)
with no lane, so a multi-lane champion (e.g. Yasuo top/mid/bottom) had its
matchup games summed across every lane, not just the one being played.

Fix: thread the inferred player_lane through
Assistant.get_matchups_for_draft -> MatchupCache -> Database (which already
supported an optional lane filter, unused by this call site).
"""

from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor, DraftState
from src.models import Matchup

POOL = ["Yasuo"]
CHAMPION_IDS = {777: "Yasuo", 64: "LeeSin"}


@pytest.fixture
def monitor():
    assistant = Mock()
    assistant.db = Mock()
    assistant.get_matchups_for_draft.return_value = [
        Matchup(
            enemy_name="LeeSin",
            winrate=52.0,
            delta1=100.0,
            delta2=150.0,
            pickrate=5.0,
            games=1000,
        )
    ]

    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=assistant):
            monitor = DraftMonitor(verbose=False, auto_hover=False)

    monitor.current_pool = POOL
    monitor.champion_id_to_name = dict(CHAMPION_IDS)
    return monitor


@pytest.fixture
def state_with_known_lane():
    """Local player (cell 1) confirmed 'middle' by the LCU, one enemy picked."""
    return DraftState(
        phase="BAN_PICK",
        enemy_picks=[64],
        ally_picks=[],
        local_player_cell_id=1,
        ally_positions={1: "middle"},
    )


def test_recommendations_fetch_matchups_scoped_to_player_lane(monitor, state_with_known_lane):
    """Every candidate's matchups must be fetched for the lane being played,
    not aggregated across all lanes (the bug: lane was never passed)."""
    with (
        patch.object(monitor, "_calculate_score_against_team", return_value=10.0),
        patch.object(monitor, "_calculate_synergy_score", return_value=0.0),
    ):
        monitor._provide_recommendations(state_with_known_lane)

    monitor.assistant.get_matchups_for_draft.assert_called_with("Yasuo", lane="middle")


def test_recommendations_fall_back_to_all_lanes_when_unknown(monitor):
    """No LCU position yet (blind pick before role assignment): unchanged
    all-lanes behavior, not a crash or an empty result."""
    state_unknown_lane = DraftState(phase="BAN_PICK", enemy_picks=[64], ally_picks=[])

    with (
        patch.object(monitor, "_calculate_score_against_team", return_value=10.0),
        patch.object(monitor, "_calculate_synergy_score", return_value=0.0),
    ):
        monitor._provide_recommendations(state_unknown_lane)

    monitor.assistant.get_matchups_for_draft.assert_called_with("Yasuo", lane=None)
