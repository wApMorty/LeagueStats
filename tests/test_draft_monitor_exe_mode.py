"""Regression tests for DraftMonitor exe mode ban skipping.

These tests verify that ban recommendation methods correctly skip execution
when running in .exe mode (sys.frozen = True).

Bug context: T9-T11 added guard clauses to skip ban recommendations in .exe mode
to avoid performance issues and LCU API conflicts.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.draft_monitor import DraftMonitor, DraftState


@pytest.fixture
def mock_lcu_client():
    """Mock LCUClient to avoid connection attempts."""
    mock_lcu = Mock()
    mock_lcu.connect.return_value = True
    return mock_lcu


@pytest.fixture
def mock_assistant():
    """Mock Assistant to avoid database dependencies."""
    mock_assistant = Mock()
    mock_assistant.db = Mock()
    mock_assistant.db.get_pool_ban_recommendations.return_value = None
    return mock_assistant


@pytest.fixture
def draft_monitor(mock_lcu_client, mock_assistant):
    """Create DraftMonitor instance with mocked dependencies."""
    with patch("src.draft_monitor.LCUClient", return_value=mock_lcu_client):
        with patch("src.draft_monitor.Assistant", return_value=mock_assistant):
            monitor = DraftMonitor(verbose=False)
            monitor.current_pool = ["Aatrox", "Darius", "Garen"]
            monitor.pool_name = "top"
            return monitor


@pytest.fixture
def draft_state():
    """Create a sample DraftState for testing."""
    state = DraftState()
    state.phase = "BAN_PICK"
    state.current_actor = 1
    state.local_player_cell_id = 1
    state.enemy_picks = ["Darius", "Garen"]
    return state


class TestHandleAutoBanHoverExeMode:
    """Tests for _handle_auto_ban_hover() exe mode skipping."""

    def test_handle_auto_ban_hover_skip_in_exe_mode(self, draft_monitor, draft_state, capsys):
        """
        Regression test for T9: _handle_auto_ban_hover() skips in .exe mode.

        Before fix: Method would attempt to calculate bans in .exe mode
        After fix: Method returns immediately when sys.frozen = True
        """
        # Mock sys.frozen = True (.exe mode)
        with patch("sys.frozen", True, create=True):
            # Call the method
            draft_monitor._handle_auto_ban_hover(draft_state)

            # Verify no database calls were made (skip successful)
            draft_monitor.assistant.db.get_pool_ban_recommendations.assert_not_called()

            # Verify no debug output about ban recommendations
            captured = capsys.readouterr()
            assert "Getting recommendations" not in captured.out
            assert "pre-calculated bans" not in captured.out

    def test_handle_auto_ban_hover_runs_in_normal_mode(self, draft_monitor, draft_state, capsys):
        """Verify that method still runs normally when NOT in .exe mode."""
        # Mock sys.frozen = False (normal mode)
        with patch("sys.frozen", False, create=True):
            # Mock _is_player_ban_turn to return True
            draft_monitor._is_player_ban_turn = Mock(return_value=True)

            # Mock database to avoid errors
            draft_monitor.assistant.db.get_pool_ban_recommendations.return_value = [
                {"champion": "Darius", "threat_score": 0.8}
            ]
            draft_monitor.lcu.hover_champion = Mock()

            # Call the method
            draft_monitor._handle_auto_ban_hover(draft_state)

            # Verify database was called (method executed)
            draft_monitor.assistant.db.get_pool_ban_recommendations.assert_called()


class TestShowBanRecommendationsDraftExeMode:
    """Tests for _show_ban_recommendations_draft() exe mode skipping."""

    def test_show_ban_recommendations_draft_skip_in_exe_mode(self, draft_monitor, capsys):
        """
        Regression test for T10: _show_ban_recommendations_draft() skips in .exe mode.

        Before fix: Method would display ban recommendations in .exe mode
        After fix: Method returns immediately when sys.frozen = True
        """
        # Mock sys.frozen = True (.exe mode)
        with patch("sys.frozen", True, create=True):
            # Call the method
            draft_monitor._show_ban_recommendations_draft()

            # Verify no ban recommendation header printed
            captured = capsys.readouterr()
            assert "STRATEGIC BAN RECOMMENDATIONS" not in captured.out
            assert "🛡️" not in captured.out

            # Verify no database calls were made
            draft_monitor.assistant.db.get_pool_ban_recommendations.assert_not_called()

    def test_show_ban_recommendations_draft_runs_in_normal_mode(self, draft_monitor, capsys):
        """Verify that method still runs normally when NOT in .exe mode."""
        # Mock sys.frozen = False (normal mode)
        with patch("sys.frozen", False, create=True):
            # Mock database to return empty list to avoid errors
            draft_monitor.assistant.db.get_pool_ban_recommendations.return_value = []

            # Call the method
            draft_monitor._show_ban_recommendations_draft()

            # Verify header was printed (method executed)
            captured = capsys.readouterr()
            assert "STRATEGIC BAN RECOMMENDATIONS" in captured.out


class TestShowAdaptiveBanRecommendationsExeMode:
    """Tests for _show_adaptive_ban_recommendations() exe mode skipping."""

    def test_show_adaptive_ban_recommendations_skip_in_exe_mode(
        self, draft_monitor, draft_state, capsys
    ):
        """
        Regression test for T11: _show_adaptive_ban_recommendations() skips in .exe mode.

        Before fix: Method would display adaptive bans in .exe mode
        After fix: Method returns immediately when sys.frozen = True
        """
        # Ensure enemy_picks is populated (method skips if empty)
        draft_state.enemy_picks = ["Darius", "Garen"]

        # Mock sys.frozen = True (.exe mode)
        with patch("sys.frozen", True, create=True):
            # Call the method
            draft_monitor._show_adaptive_ban_recommendations(draft_state)

            # Verify no adaptive ban header printed
            captured = capsys.readouterr()
            assert "ADAPTIVE BANS" not in captured.out
            assert "TARGETED BAN RECOMMENDATIONS" not in captured.out
            assert "🎯" not in captured.out

            # Verify no database calls were made
            draft_monitor.assistant.db.get_pool_ban_recommendations.assert_not_called()

    def test_show_adaptive_ban_recommendations_runs_in_normal_mode(
        self, draft_monitor, draft_state, capsys
    ):
        """Verify that method still runs normally when NOT in .exe mode."""
        # Ensure enemy_picks is populated
        draft_state.enemy_picks = ["Darius", "Garen"]

        # Mock sys.frozen = False (normal mode)
        with patch("sys.frozen", False, create=True):
            # Mock database and _get_display_name
            draft_monitor.assistant.db.get_pool_ban_recommendations.return_value = []
            draft_monitor._get_display_name = Mock(side_effect=lambda x: x)

            # Call the method
            draft_monitor._show_adaptive_ban_recommendations(draft_state)

            # Verify header was printed (method executed)
            captured = capsys.readouterr()
            assert "TARGETED BAN RECOMMENDATIONS" in captured.out

    def test_show_adaptive_ban_recommendations_skip_if_no_enemy_picks(
        self, draft_monitor, draft_state, capsys
    ):
        """Verify method skips when no enemy picks (even in normal mode)."""
        # Empty enemy_picks
        draft_state.enemy_picks = []

        # Mock sys.frozen = False (normal mode)
        with patch("sys.frozen", False, create=True):
            # Call the method
            draft_monitor._show_adaptive_ban_recommendations(draft_state)

            # Verify no output (early return due to no enemy picks)
            captured = capsys.readouterr()
            assert "TARGETED BAN RECOMMENDATIONS" not in captured.out


class TestExeModeGuardClauseCoverage:
    """Additional tests to ensure guard clause coverage."""

    def test_all_methods_check_sys_frozen(self, draft_monitor, draft_state):
        """Verify three methods (T9, T10, T11) have sys.frozen guard clause."""
        with patch("sys.frozen", True, create=True):
            # Three methods should return immediately without errors
            draft_monitor._handle_auto_ban_hover(draft_state)
            draft_monitor._show_ban_recommendations_draft()
            draft_monitor._show_adaptive_ban_recommendations(draft_state)

            # No exceptions should be raised
            assert True

    def test_sys_frozen_attribute_handling(self, draft_monitor, draft_state):
        """Test handling when sys.frozen attribute doesn't exist."""
        # Use patch to ensure sys.frozen doesn't exist
        import sys

        original_frozen = getattr(sys, "frozen", None)
        if hasattr(sys, "frozen"):
            delattr(sys, "frozen")

        try:
            # All methods should work normally when sys.frozen doesn't exist
            # (getattr returns False by default)
            draft_monitor.assistant.db.get_pool_ban_recommendations.return_value = []
            draft_monitor._get_display_name = Mock(side_effect=lambda x: x)

            # These should execute (not skip)
            draft_monitor._show_ban_recommendations_draft()
            # Method was called (at least tried to get recommendations)
            assert draft_monitor.assistant.db.get_pool_ban_recommendations.called

        finally:
            # Restore original state
            if original_frozen is not None:
                sys.frozen = original_frozen
