"""Tests for lane-aware OneTricks.gg URLs (SPEC-09 E3 lane resolution reused
to scope the champion page to the role actually being played, instead of the
unfiltered all-roles page)."""

from unittest.mock import Mock, patch

import pytest

from src.draft.state import DraftState
from src.draft_monitor import DraftMonitor


@pytest.fixture
def draft_monitor():
    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=Mock()):
            monitor = DraftMonitor(verbose=False)
            monitor.player_champion = "Ahri"
            return monitor


def _open_and_capture_url(draft_monitor) -> str:
    with patch("src.draft.onetricks.config.get_brave_path", return_value="brave.exe"):
        with patch("src.draft.onetricks.subprocess.Popen") as mock_popen:
            mock_popen.return_value = Mock(poll=Mock(return_value=None))
            draft_monitor._open_champion_page_on_onetricks()
    args = mock_popen.call_args[0][0]
    app_arg = next(a for a in args if a.startswith("--app="))
    return app_arg[len("--app=") :]


class TestOneTricksLaneAwareUrl:
    def test_no_lane_known_leaves_url_unfiltered(self, draft_monitor):
        """No pool lane and no draft state: unfiltered URL, unchanged behaviour."""
        url = _open_and_capture_url(draft_monitor)
        assert url == "https://www.onetricks.gg/champions/builds/Ahri"

    def test_pool_lane_takes_priority(self, draft_monitor):
        draft_monitor.pool_lane = "jungle"
        url = _open_and_capture_url(draft_monitor)
        assert url == "https://www.onetricks.gg/champions/builds/Ahri?role=jungle"

    def test_lcu_assigned_position_used_when_no_pool_lane(self, draft_monitor):
        state = DraftState()
        state.local_player_cell_id = 2
        state.ally_positions = {2: "support"}
        draft_monitor.last_draft_state = state

        url = _open_and_capture_url(draft_monitor)
        assert url == "https://www.onetricks.gg/champions/builds/Ahri?role=support"

    @pytest.mark.parametrize(
        "internal_lane,onetricks_role",
        [
            ("top", "top"),
            ("jungle", "jungle"),
            ("middle", "mid"),
            ("bottom", "bot"),
            ("support", "support"),
        ],
    )
    def test_lane_naming_translated_to_onetricks_role(
        self, draft_monitor, internal_lane, onetricks_role
    ):
        """Internal lane naming (matchups.lane) differs from onetricks.gg's own
        ?role= naming for mid/bot ("middle"/"bottom" vs "mid"/"bot")."""
        draft_monitor.pool_lane = internal_lane
        url = _open_and_capture_url(draft_monitor)
        assert url == f"https://www.onetricks.gg/champions/builds/Ahri?role={onetricks_role}"


class TestOneTricksMatchupUrl:
    """The end-of-draft page opens on the duel against the direct opponent."""

    def _state(self, enemies):
        state = DraftState()
        state.enemy_picks = list(enemies)
        state.inferred_roles = enemies
        return state

    def test_direct_opponent_opens_the_duel_page(self, draft_monitor):
        draft_monitor.pool_lane = "top"
        draft_monitor.champion_id_to_name = {121: "Kha'Zix", 122: "Darius"}
        draft_monitor.last_draft_state = self._state({121: "jungle", 122: "top"})
        url = _open_and_capture_url(draft_monitor)
        assert url == "https://www.onetricks.gg/champions/builds/Ahri?role=top&matchup=Darius"

    def test_opponent_name_is_normalized(self, draft_monitor):
        draft_monitor.pool_lane = "jungle"
        draft_monitor.champion_id_to_name = {121: "Kha'Zix"}
        draft_monitor.last_draft_state = self._state({121: "jungle"})
        url = _open_and_capture_url(draft_monitor)
        assert url.endswith("?role=jungle&matchup=Khazix")

    def test_ambiguous_lane_keeps_the_champion_page(self, draft_monitor):
        """Two enemies inferred on our lane: no single direct opponent."""
        draft_monitor.pool_lane = "top"
        draft_monitor.champion_id_to_name = {121: "Kha'Zix", 122: "Darius"}
        draft_monitor.last_draft_state = self._state({121: "top", 122: "top"})
        url = _open_and_capture_url(draft_monitor)
        assert url == "https://www.onetricks.gg/champions/builds/Ahri?role=top"
