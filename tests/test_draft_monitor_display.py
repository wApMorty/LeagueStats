"""Tests for SPEC-04 B5 — role display, recommendation lane/volume tags, and
manual role correction ("r <champion> <lane>").
"""

from unittest.mock import Mock, patch

import pytest

from src.config_constants import role_inference_config
from src.draft_monitor import DraftMonitor, DraftState
from src.lcu_client import LCUClient
from src.models import Matchup

CHAMPION_IDS = {2350: "Ornn", 412: "Thresh", 84: "Akali"}


@pytest.fixture
def monitor():
    """DraftMonitor with a mocked Assistant and a real (network-free)
    LCUClient — get_assigned_positions() is pure dict processing, and
    _parse_draft_state needs a real dict back from it, not a Mock."""
    assistant = Mock()
    assistant.db = Mock()

    with patch("src.draft_monitor.Assistant", return_value=assistant):
        monitor = DraftMonitor(verbose=False, auto_hover=False)
    monitor.lcu = LCUClient()

    monitor.champion_id_to_name = dict(CHAMPION_IDS)
    return monitor


class TestFormatRoleTag:
    def test_lcu_source(self, monitor):
        state = DraftState(inferred_roles={2350: "top"}, role_source={2350: "lcu"})
        assert monitor._format_role_tag(2350, state) == " (top·LCU)"

    def test_user_forced_source(self, monitor):
        state = DraftState(inferred_roles={2350: "jungle"}, role_source={2350: "user"})
        assert monitor._format_role_tag(2350, state) == " (jungle·forced)"

    def test_inferred_high_confidence_no_warning(self, monitor):
        state = DraftState(
            inferred_roles={412: "support"},
            role_source={412: "inferred"},
            role_confidence={412: 0.92},
        )
        assert monitor._format_role_tag(412, state) == " (support·92%)"

    def test_inferred_low_confidence_gets_warning_mark(self, monitor):
        state = DraftState(
            inferred_roles={412: "top"},
            role_source={412: "inferred"},
            role_confidence={412: 0.4},
        )
        tag = monitor._format_role_tag(412, state)
        assert tag == " (top·40%?)"
        assert 0.4 < role_inference_config.ROLE_CONFIDENCE_WARN

    def test_confidence_exactly_at_threshold_is_not_flagged(self, monitor):
        state = DraftState(
            inferred_roles={412: "top"},
            role_source={412: "inferred"},
            role_confidence={412: role_inference_config.ROLE_CONFIDENCE_WARN},
        )
        assert "?" not in monitor._format_role_tag(412, state)

    def test_no_known_role_returns_empty_string(self, monitor):
        state = DraftState()
        assert monitor._format_role_tag(2350, state) == ""


class TestDisplayDraftStateShowsRoles:
    def test_role_tag_appears_next_to_champion(self, monitor, capsys):
        state = DraftState(
            ally_picks=[2350],
            enemy_picks=[412],
            inferred_roles={2350: "top", 412: "support"},
            role_source={2350: "lcu", 412: "inferred"},
            role_confidence={412: 0.85},
        )

        monitor._display_draft_state(state)

        output = capsys.readouterr().out
        assert "Ornn (top·LCU)" in output
        assert "Thresh (support·85%)" in output


class TestRecommendationLaneAndVolumeTags:
    @pytest.fixture
    def scoring_monitor(self):
        assistant = Mock()
        assistant.db = Mock()
        assistant.get_matchups_for_draft.return_value = [
            Matchup(
                enemy_name="Thresh",
                winrate=52.0,
                delta1=10.0,
                delta2=15.0,
                pickrate=5.0,
                games=1234,
            )
        ]

        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            with patch("src.draft_monitor.Assistant", return_value=assistant):
                monitor = DraftMonitor(verbose=False, auto_hover=False)

        monitor.current_pool = ["Ornn"]
        monitor.champion_id_to_name = {2350: "Ornn", 412: "Thresh"}
        return monitor

    def test_lane_and_direct_counter_and_volume_shown(self, scoring_monitor, capsys):
        state = DraftState(
            phase="BAN_PICK", enemy_picks=[412], ally_picks=[], local_player_cell_id=0
        )
        state.ally_positions = {0: "top"}
        state.inferred_roles = {412: "support"}

        with patch.object(scoring_monitor, "_calculate_score_against_team", return_value=10.0):
            with patch.object(scoring_monitor, "_calculate_synergy_score", return_value=0.0):
                scoring_monitor._provide_recommendations(state)

        output = capsys.readouterr().out
        assert "Ornn (top)" in output
        assert "1 234 games" in output

    def test_direct_counter_shown_when_enemy_shares_our_lane(self, scoring_monitor, capsys):
        state = DraftState(
            phase="BAN_PICK", enemy_picks=[412], ally_picks=[], local_player_cell_id=0
        )
        state.ally_positions = {0: "support"}
        state.inferred_roles = {412: "support"}

        with patch.object(scoring_monitor, "_calculate_score_against_team", return_value=10.0):
            with patch.object(scoring_monitor, "_calculate_synergy_score", return_value=0.0):
                scoring_monitor._provide_recommendations(state)

        output = capsys.readouterr().out
        assert "(support vs Thresh)" in output

    def test_no_lane_tag_without_player_lane(self, scoring_monitor, capsys):
        state = DraftState(
            phase="BAN_PICK", enemy_picks=[412], ally_picks=[], local_player_cell_id=0
        )

        with patch.object(scoring_monitor, "_calculate_score_against_team", return_value=10.0):
            with patch.object(scoring_monitor, "_calculate_synergy_score", return_value=0.0):
                scoring_monitor._provide_recommendations(state)

        output = capsys.readouterr().out
        assert "Ornn (" not in output
        assert "1 234 games" in output


class TestManualCorrectionCommand:
    def test_valid_command_forces_role(self, monitor):
        state = DraftState(ally_picks=[2350], enemy_picks=[])

        applied = monitor._handle_correction_command("r Ornn support", state)

        assert applied is True
        assert state.inferred_roles[2350] == "support"
        assert state.role_confidence[2350] == 1.0
        assert state.role_source[2350] == "user"
        assert monitor.forced_roles[2350] == "support"

    def test_champion_not_in_draft_is_rejected(self, monitor):
        state = DraftState(ally_picks=[], enemy_picks=[])

        applied = monitor._handle_correction_command("r Ornn support", state)

        assert applied is False
        assert 2350 not in monitor.forced_roles

    def test_unknown_champion_is_rejected(self, monitor):
        state = DraftState(ally_picks=[2350], enemy_picks=[])

        applied = monitor._handle_correction_command("r NotAChampion support", state)

        assert applied is False

    def test_unknown_lane_is_rejected(self, monitor):
        state = DraftState(ally_picks=[2350], enemy_picks=[])

        applied = monitor._handle_correction_command("r Ornn midlane", state)

        assert applied is False
        assert 2350 not in monitor.forced_roles

    def test_malformed_command_is_rejected(self, monitor):
        state = DraftState(ally_picks=[2350], enemy_picks=[])

        assert monitor._handle_correction_command("Ornn support", state) is False
        assert monitor._handle_correction_command("r Ornn", state) is False

    def test_command_is_case_insensitive(self, monitor):
        state = DraftState(ally_picks=[2350], enemy_picks=[])

        applied = monitor._handle_correction_command("R ornn SUPPORT", state)

        assert applied is True
        assert monitor.forced_roles[2350] == "support"


class TestApplyPendingCommands:
    def test_drains_queue_and_reports_whether_anything_applied(self, monitor):
        state = DraftState(ally_picks=[2350], enemy_picks=[])
        monitor._command_queue.put("r Ornn support")

        assert monitor._apply_pending_commands(state) is True
        assert monitor._command_queue.empty()

    def test_returns_false_when_queue_empty(self, monitor):
        state = DraftState(ally_picks=[2350], enemy_picks=[])
        assert monitor._apply_pending_commands(state) is False

    def test_invalid_command_does_not_count_as_applied(self, monitor):
        state = DraftState(ally_picks=[2350], enemy_picks=[])
        monitor._command_queue.put("garbage")

        assert monitor._apply_pending_commands(state) is False


class TestForcedRoleSurvivesRecalculation:
    def test_forced_role_persists_across_parse_draft_state(self, monitor):
        monitor.lane_distributions = {
            2350: {"top": 90.0, "jungle": 5.0, "middle": 2.0, "bottom": 1.0, "support": 2.0}
        }
        monitor.forced_roles[2350] = "support"

        champ_select_data = {
            "timer": {"phase": "BAN_PICK"},
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "championId": 2350, "assignedPosition": ""}],
            "theirTeam": [],
            "actions": [],
        }

        state = monitor._parse_draft_state(champ_select_data)

        # Ornn's own distribution strongly favors top, but the forced role wins.
        assert state.inferred_roles[2350] == "support"
        assert state.role_confidence[2350] == 1.0
        assert state.role_source[2350] == "user"

    def test_forced_role_cleared_once_champion_leaves_draft(self, monitor):
        monitor.forced_roles[2350] = "support"

        champ_select_data = {
            "timer": {"phase": "BAN_PICK"},
            "localPlayerCellId": 0,
            "myTeam": [],
            "theirTeam": [],
            "actions": [],
        }

        monitor._parse_draft_state(champ_select_data)

        assert 2350 not in monitor.forced_roles


class TestResetClearsForcedRoles:
    def test_reset_for_next_game_clears_forced_roles(self, monitor):
        monitor.forced_roles[2350] = "support"

        monitor._reset_for_next_game()

        assert monitor.forced_roles == {}


class TestCommandListenerThread:
    def test_start_command_listener_is_idempotent(self, monitor):
        monitor.is_monitoring = False  # loop condition false: the thread returns immediately
        monitor._start_command_listener()
        first_thread = monitor._command_listener_thread

        monitor._start_command_listener()

        assert monitor._command_listener_thread is first_thread


class TestMonitorLoopAppliesCommands:
    def test_redisplays_on_command_even_without_draft_change(self, monitor):
        champ_select_data = {
            "timer": {"phase": "BAN_PICK"},
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "championId": 2350, "assignedPosition": ""}],
            "theirTeam": [],
            "actions": [],
        }
        monitor.lcu.is_in_champion_select = Mock(return_value=True)
        monitor.lcu.get_champion_select_session = Mock(return_value=champ_select_data)
        monitor.last_draft_state = monitor._parse_draft_state(champ_select_data)
        monitor._command_queue.put("r Ornn support")

        with patch.object(monitor, "_handle_draft_change") as mock_handle:
            monitor._monitor_loop()

        mock_handle.assert_called_once()
        applied_state = mock_handle.call_args.args[0]
        assert applied_state.role_source[2350] == "user"

    def test_no_redisplay_when_no_command_and_no_draft_change(self, monitor):
        champ_select_data = {
            "timer": {"phase": "BAN_PICK"},
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "championId": 2350, "assignedPosition": ""}],
            "theirTeam": [],
            "actions": [],
        }
        monitor.lcu.is_in_champion_select = Mock(return_value=True)
        monitor.lcu.get_champion_select_session = Mock(return_value=champ_select_data)
        monitor.last_draft_state = monitor._parse_draft_state(champ_select_data)

        with patch.object(monitor, "_handle_draft_change") as mock_handle:
            monitor._monitor_loop()

        mock_handle.assert_not_called()
