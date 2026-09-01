"""Characterization tests for the draft lifecycle of ``DraftMonitor``
(SPEC TODO E10 safety net).

Scope:
- ``_handle_ready_check`` (queue found / auto-accept / phase transitions)
- ``_analyze_complete_draft``
- ``_reset_for_next_game``

Behavior is pinned exactly as it is today, including the fact that
``_handle_ready_check`` never consults ``self.auto_accept_queue`` itself.
"""

from unittest.mock import Mock, patch

import pytest

from src.config_constants import draft_config
from src.draft_monitor import DraftMonitor, DraftState

COOLDOWN = draft_config.READY_CHECK_COOLDOWN * 2.5  # 5.0s by default


@pytest.fixture
def monitor():
    """DraftMonitor with mocked Assistant/LCUClient."""
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            return DraftMonitor(verbose=False, auto_hover=False, auto_accept_queue=True)


class TestHandleReadyCheckAccept:
    """``_handle_ready_check()`` — entering a ready check."""

    def test_accepts_and_records_the_timestamp(self, monitor, capsys):
        # Arrange
        monitor.lcu.get_gameflow_session.return_value = {"phase": "ReadyCheck"}
        monitor.lcu.get_ready_check_state.return_value = {"timer": 8}
        monitor.lcu.accept_ready_check.return_value = True

        # Act
        with patch("src.draft_monitor.time.time", return_value=1000.0):
            monitor._handle_ready_check()

        # Assert
        monitor.lcu.accept_ready_check.assert_called_once_with()
        assert monitor.ready_check_accepted_time == 1000.0
        assert monitor.last_gameflow_phase == "ReadyCheck"

        out = capsys.readouterr().out
        assert "[QUEUE] PARTIE TROUVÉE !" in out
        assert "[OK] [AUTO-ACCEPT] Queue acceptée automatiquement !" in out
        assert "En attente des autres joueurs..." in out

    def test_failed_accept_does_not_record_a_timestamp(self, monitor, capsys):
        monitor.lcu.get_gameflow_session.return_value = {"phase": "ReadyCheck"}
        monitor.lcu.get_ready_check_state.return_value = None
        monitor.lcu.accept_ready_check.return_value = False

        monitor._handle_ready_check()

        assert monitor.ready_check_accepted_time == 0
        out = capsys.readouterr().out
        assert "[ALERTE] [AUTO-ACCEPT] Échec de l'acceptation de la queue" in out
        assert "Queue acceptée automatiquement" not in out

    def test_auto_accept_flag_is_not_checked_by_this_method(self, monitor):
        """FROZEN CONTRACT: the ``auto_accept_queue`` gate lives in the caller
        (``_monitor_loop``), NOT here. Calling this method with the flag off
        still accepts the queue — do not "fix" that during the extraction."""
        monitor.auto_accept_queue = False
        monitor.lcu.get_gameflow_session.return_value = {"phase": "ReadyCheck"}
        monitor.lcu.get_ready_check_state.return_value = None
        monitor.lcu.accept_ready_check.return_value = True

        monitor._handle_ready_check()

        monitor.lcu.accept_ready_check.assert_called_once_with()

    def test_ready_check_timer_is_logged_only_in_verbose(self, monitor, capsys):
        monitor.verbose = True
        monitor.lcu.get_gameflow_session.return_value = {"phase": "ReadyCheck"}
        monitor.lcu.get_ready_check_state.return_value = {"timer": 8}
        monitor.lcu.accept_ready_check.return_value = True

        monitor._handle_ready_check()

        assert "[DEBUG] Ready check timer: 8s" in capsys.readouterr().out


class TestHandleReadyCheckCooldown:
    """``_handle_ready_check()`` — anti-spam cooldown on repeated ticks."""

    def _stay_in_ready_check(self, monitor):
        monitor.lcu.get_gameflow_session.return_value = {"phase": "ReadyCheck"}
        monitor.lcu.get_ready_check_state.return_value = None
        monitor.lcu.accept_ready_check.return_value = True

    def test_second_tick_within_cooldown_does_not_re_accept(self, monitor, capsys):
        self._stay_in_ready_check(monitor)
        monitor.last_gameflow_phase = "ReadyCheck"
        monitor.ready_check_accepted_time = 1000.0

        with patch("src.draft_monitor.time.time", return_value=1000.0 + COOLDOWN - 0.1):
            monitor._handle_ready_check()

        monitor.lcu.accept_ready_check.assert_not_called()
        assert "PARTIE TROUVÉE" not in capsys.readouterr().out

    def test_tick_after_cooldown_re_accepts(self, monitor, capsys):
        """A ready check that failed and came back is accepted again."""
        self._stay_in_ready_check(monitor)
        monitor.last_gameflow_phase = "ReadyCheck"
        monitor.ready_check_accepted_time = 1000.0

        with patch("src.draft_monitor.time.time", return_value=1000.0 + COOLDOWN + 0.1):
            monitor._handle_ready_check()

        monitor.lcu.accept_ready_check.assert_called_once_with()
        assert "[QUEUE] PARTIE TROUVÉE !" in capsys.readouterr().out

    def test_cooldown_boundary_is_strictly_greater_than(self, monitor):
        """Exactly at the cooldown, the condition ``> cooldown`` is False."""
        self._stay_in_ready_check(monitor)
        monitor.last_gameflow_phase = "ReadyCheck"
        monitor.ready_check_accepted_time = 1000.0

        with patch("src.draft_monitor.time.time", return_value=1000.0 + COOLDOWN):
            monitor._handle_ready_check()

        monitor.lcu.accept_ready_check.assert_not_called()

    def test_no_recorded_acceptance_never_re_accepts_in_the_same_phase(self, monitor):
        """``ready_check_accepted_time == 0`` disables the cooldown branch, so
        a still-ongoing ReadyCheck is not re-accepted."""
        self._stay_in_ready_check(monitor)
        monitor.last_gameflow_phase = "ReadyCheck"
        monitor.ready_check_accepted_time = 0

        monitor._handle_ready_check()

        monitor.lcu.accept_ready_check.assert_not_called()


class TestHandleReadyCheckTransitions:
    """``_handle_ready_check()`` — leaving the ready check."""

    def test_transition_to_champ_select_is_a_success(self, monitor, capsys):
        monitor.last_gameflow_phase = "ReadyCheck"
        monitor.ready_check_accepted_time = 1000.0
        monitor.lcu.get_gameflow_session.return_value = {"phase": "ChampSelect"}

        monitor._handle_ready_check()

        out = capsys.readouterr().out
        assert "[OK] [SUCCESS] Tous les joueurs ont accepté" in out
        assert monitor.last_gameflow_phase == "ChampSelect"
        # A success does NOT reset the timestamp
        assert monitor.ready_check_accepted_time == 1000.0

    @pytest.mark.parametrize("phase", ["Lobby", "Matchmaking"])
    def test_transition_back_to_queue_is_a_failure_and_resets_the_timer(
        self, monitor, capsys, phase
    ):
        monitor.last_gameflow_phase = "ReadyCheck"
        monitor.ready_check_accepted_time = 1000.0
        monitor.lcu.get_gameflow_session.return_value = {"phase": phase}

        monitor._handle_ready_check()

        out = capsys.readouterr().out
        assert "[ALERTE] [FAILED] Échec du ready check" in out
        assert "[RETRY] Retour en file d'attente..." in out
        assert monitor.ready_check_accepted_time == 0
        assert monitor.last_gameflow_phase == phase

    def test_unhandled_transition_only_updates_the_phase(self, monitor, capsys):
        """e.g. straight to InProgress: no message, but the phase is tracked."""
        monitor.last_gameflow_phase = "ReadyCheck"
        monitor.ready_check_accepted_time = 1000.0
        monitor.lcu.get_gameflow_session.return_value = {"phase": "InProgress"}

        monitor._handle_ready_check()

        assert capsys.readouterr().out == ""
        assert monitor.last_gameflow_phase == "InProgress"
        assert monitor.ready_check_accepted_time == 1000.0


class TestHandleReadyCheckRobustness:
    """``_handle_ready_check()`` — degraded LCU conditions."""

    def test_no_gameflow_session_returns_without_touching_state(self, monitor, capsys):
        monitor.last_gameflow_phase = "ReadyCheck"
        monitor.lcu.get_gameflow_session.return_value = None

        monitor._handle_ready_check()

        # Early return: the phase is NOT updated
        assert monitor.last_gameflow_phase == "ReadyCheck"
        assert capsys.readouterr().out == ""

    def test_missing_phase_key_is_treated_as_empty_string(self, monitor):
        monitor.lcu.get_gameflow_session.return_value = {}

        monitor._handle_ready_check()

        assert monitor.last_gameflow_phase == ""

    def test_lcu_exception_is_swallowed(self, monitor, capsys):
        monitor.lcu.get_gameflow_session.side_effect = Exception("lcu disconnected")

        monitor._handle_ready_check()  # must not raise

        assert capsys.readouterr().out == ""

    def test_lcu_exception_is_reported_in_verbose(self, monitor, capsys):
        monitor.verbose = True
        monitor.lcu.get_gameflow_session.side_effect = Exception("lcu disconnected")

        monitor._handle_ready_check()

        out = capsys.readouterr().out
        assert "[WARNING] Error handling ready check: lcu disconnected" in out


class TestAnalyzeCompleteDraft:
    """``_analyze_complete_draft(state)``."""

    @staticmethod
    def _full_state():
        return DraftState(
            ally_picks=[1, 2, 3, 4, 5],
            enemy_picks=[6, 7, 8, 9, 10],
            inferred_roles={1: "top"},
        )

    def test_full_draft_triggers_the_final_analysis(self, monitor, capsys):
        state = self._full_state()
        monitor.open_onetricks = False

        with patch.object(monitor, "_calculate_final_scores") as final:
            monitor._analyze_complete_draft(state)

        final.assert_called_once_with([1, 2, 3, 4, 5], [6, 7, 8, 9, 10], ally_lanes={1: "top"})
        assert monitor.has_analyzed_final_draft is True
        assert "[DRAFT TERMINÉ] Tous les champions verrouillés - Analyse finale !" in (
            capsys.readouterr().out
        )

    def test_onetricks_page_opens_when_enabled(self, monitor):
        monitor.open_onetricks = True

        with patch.object(monitor, "_calculate_final_scores"):
            with patch.object(monitor, "_open_champion_page_on_onetricks") as onetricks:
                monitor._analyze_complete_draft(self._full_state())

        onetricks.assert_called_once_with()

    def test_onetricks_page_stays_closed_when_disabled(self, monitor):
        monitor.open_onetricks = False

        with patch.object(monitor, "_calculate_final_scores"):
            with patch.object(monitor, "_open_champion_page_on_onetricks") as onetricks:
                monitor._analyze_complete_draft(self._full_state())

        onetricks.assert_not_called()

    def test_incomplete_draft_is_a_silent_no_op(self, monitor, capsys):
        """Fewer than 5 picks per side: nothing runs, nothing is flagged."""
        state = DraftState(ally_picks=[1, 2], enemy_picks=[6, 7, 8, 9, 10])

        with patch.object(monitor, "_calculate_final_scores") as final:
            monitor._analyze_complete_draft(state)

        final.assert_not_called()
        assert monitor.has_analyzed_final_draft is False
        assert capsys.readouterr().out == ""

    def test_final_scores_failure_is_caught_and_leaves_the_flag_unset(self, monitor, capsys):
        """The draft is NOT marked as analyzed when the analysis crashed."""
        with patch.object(
            monitor, "_calculate_final_scores", side_effect=Exception("scoring crashed")
        ):
            monitor._analyze_complete_draft(self._full_state())

        assert monitor.has_analyzed_final_draft is False
        out = capsys.readouterr().out
        assert "[ERREUR] Échec de l'analyse du draft complet: scoring crashed" in out


class TestResetForNextGame:
    """``_reset_for_next_game()`` — every attribute must return to its
    ``__init__`` value so the next draft starts from a clean slate."""

    @staticmethod
    def _dirty(monitor):
        """Move every reset attribute away from its initial value."""
        monitor.last_draft_state = DraftState(phase="BAN_PICK", ally_picks=[1, 2])
        monitor.has_done_initial_hover = True
        monitor.has_analyzed_final_draft = True
        monitor.last_recommendation = "Darius"
        monitor.last_ban_recommendation = "Teemo"
        monitor.last_gameflow_phase = "ChampSelect"
        monitor.ready_check_accepted_time = 1234.5
        monitor.player_champion = "Aatrox"
        monitor.forced_roles = {266: "top"}
        monitor._last_prediction_id = 42

    def test_every_attribute_returns_to_its_initial_value(self, monitor):
        # Arrange
        self._dirty(monitor)

        # Act
        with patch("src.draft.lifecycle.clear_console"):
            monitor._reset_for_next_game()

        # Assert
        assert monitor.last_draft_state == DraftState()
        assert monitor.has_done_initial_hover is False
        assert monitor.has_analyzed_final_draft is False
        assert monitor.last_recommendation is None
        assert monitor.last_ban_recommendation is None
        assert monitor.last_gameflow_phase == ""
        assert monitor.ready_check_accepted_time == 0
        assert monitor.player_champion is None
        assert monitor.forced_roles == {}
        assert monitor._last_prediction_id is None

    def test_console_is_cleared(self, monitor):
        with patch("src.draft.lifecycle.clear_console") as clear:
            monitor._reset_for_next_game()

        clear.assert_called_once_with()

    def test_shown_ready_message_attribute_is_deleted_when_present(self, monitor):
        # Arrange
        monitor._shown_ready_message = True

        # Act
        with patch("src.draft.lifecycle.clear_console"):
            monitor._reset_for_next_game()

        # Assert
        assert not hasattr(monitor, "_shown_ready_message")

    def test_missing_shown_ready_message_attribute_is_not_an_error(self, monitor):
        """The ``hasattr`` guard protects the ``delattr`` — no AttributeError."""
        # Arrange
        assert not hasattr(monitor, "_shown_ready_message")

        # Act
        with patch("src.draft.lifecycle.clear_console"):
            monitor._reset_for_next_game()  # must not raise

        # Assert
        assert not hasattr(monitor, "_shown_ready_message")

    def test_pool_settings_are_deliberately_preserved(self, monitor):
        """FROZEN SCOPE: the selected pool survives the reset — only the
        per-game state is cleared."""
        monitor.current_pool = ["Aatrox", "Darius"]
        monitor.pool_name = "Alpha Pool"
        monitor.champion_id_to_name = {1: "Aatrox"}

        with patch("src.draft.lifecycle.clear_console"):
            monitor._reset_for_next_game()

        assert monitor.current_pool == ["Aatrox", "Darius"]
        assert monitor.pool_name == "Alpha Pool"
        assert monitor.champion_id_to_name == {1: "Aatrox"}

    def test_debug_message_is_verbose_only(self, monitor, capsys):
        monitor.verbose = True

        with patch("src.draft.lifecycle.clear_console"):
            monitor._reset_for_next_game()

        assert "[DEBUG] State reset for next game" in capsys.readouterr().out

    def test_reset_is_idempotent(self, monitor):
        self._dirty(monitor)

        with patch("src.draft.lifecycle.clear_console"):
            monitor._reset_for_next_game()
            monitor._reset_for_next_game()

        assert monitor.last_draft_state == DraftState()
        assert monitor.forced_roles == {}
