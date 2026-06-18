"""Regression tests for OneTricks browser window recycling (memory leak fix).

Bug context:
    On a long Draft Monitor session, every completed draft called
    ``subprocess.Popen([brave, url])`` and never reaped it, opening a NEW Brave
    tab per game. Over many games Brave accumulated tabs and consumed several GB,
    putting the whole system under memory pressure (observed as YASB crashing).

Fix:
    The monitor now keeps a single ``_onetricks_proc`` handle, launches a dedicated
    killable Brave app window, and terminates the previous window before opening a
    new one. At most one OneTricks window is alive at a time.
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor


@pytest.fixture
def draft_monitor():
    """Create a DraftMonitor with mocked LCU/Assistant dependencies."""
    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=Mock()):
            monitor = DraftMonitor(verbose=False)
            monitor.player_champion = "Aatrox"
            return monitor


class TestOneTricksWindowRecycling:
    """The monitor must not stack OneTricks browser windows across games."""

    def test_previous_window_is_closed_before_opening_new_one(self, draft_monitor):
        """Second open() must terminate the first window (no accumulation)."""
        first_proc = Mock()
        first_proc.poll.return_value = None  # still running
        second_proc = Mock()
        second_proc.poll.return_value = None

        with patch("src.draft_monitor.config.get_brave_path", return_value="brave.exe"):
            with patch(
                "src.draft_monitor.subprocess.Popen", side_effect=[first_proc, second_proc]
            ) as mock_popen:
                # Game 1: opens the first window
                draft_monitor._open_champion_page_on_onetricks()
                assert draft_monitor._onetricks_proc is first_proc
                first_proc.terminate.assert_not_called()

                # Game 2: must close the first window before opening the second
                draft_monitor.player_champion = "Darius"
                draft_monitor._open_champion_page_on_onetricks()

                first_proc.terminate.assert_called_once()
                assert draft_monitor._onetricks_proc is second_proc
                assert mock_popen.call_count == 2

    def test_launch_uses_dedicated_killable_app_window(self, draft_monitor):
        """Brave must be launched with --app and a dedicated --user-data-dir.

        Without a dedicated user-data-dir, Brave merges into the main instance and
        our handle cannot terminate the tab — defeating the recycling.
        """
        with patch("src.draft_monitor.config.get_brave_path", return_value="brave.exe"):
            with patch("src.draft_monitor.subprocess.Popen") as mock_popen:
                mock_popen.return_value = Mock(poll=Mock(return_value=None))
                draft_monitor._open_champion_page_on_onetricks()

        args = mock_popen.call_args[0][0]
        assert any(a.startswith("--app=") for a in args)
        assert any(a.startswith("--user-data-dir=") for a in args)

    def test_cleanup_closes_window(self, draft_monitor):
        """cleanup() must close any open OneTricks window."""
        proc = Mock()
        proc.poll.return_value = None
        draft_monitor._onetricks_proc = proc

        draft_monitor.cleanup()

        proc.terminate.assert_called_once()
        assert draft_monitor._onetricks_proc is None

    def test_close_is_safe_when_no_window_open(self, draft_monitor):
        """Closing with no window open must be a no-op (no exception)."""
        draft_monitor._onetricks_proc = None
        draft_monitor._close_onetricks_window()  # must not raise
        assert draft_monitor._onetricks_proc is None

    def test_already_exited_window_is_not_terminated(self, draft_monitor):
        """A window that already exited must not be terminated again."""
        proc = Mock()
        proc.poll.return_value = 0  # already exited
        draft_monitor._onetricks_proc = proc

        draft_monitor._close_onetricks_window()

        proc.terminate.assert_not_called()
        assert draft_monitor._onetricks_proc is None

    def test_kill_when_terminate_times_out(self, draft_monitor):
        """If terminate() doesn't stop the window in time, kill() is used."""
        proc = Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired(cmd="brave", timeout=5), None]
        draft_monitor._onetricks_proc = proc

        draft_monitor._close_onetricks_window()

        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
