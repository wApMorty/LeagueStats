"""
Unit tests for src/utils/console.py module.

Tests cover:
- Global state management for console clearing (set_clear_enabled, is_clear_enabled)
- clear_console() behavior with enabled/disabled state
- clear_and_banner() functionality
- Cross-platform console clearing (Windows cls vs Unix clear)
"""

import sys
import pytest
from unittest.mock import patch, MagicMock

# Import module under test
from src.utils.console import (
    clear_console,
    set_clear_enabled,
    is_clear_enabled,
    clear_and_banner,
)


class TestClearEnabled:
    """Tests for set_clear_enabled() and is_clear_enabled() functions."""

    def test_default_state_is_enabled(self):
        """Test that console clearing is enabled by default."""
        # Reset to default state
        set_clear_enabled(True)
        assert is_clear_enabled() is True

    def test_set_clear_enabled_false(self):
        """Test disabling console clearing."""
        set_clear_enabled(False)
        assert is_clear_enabled() is False

    def test_set_clear_enabled_true(self):
        """Test enabling console clearing."""
        set_clear_enabled(True)
        assert is_clear_enabled() is True

    def test_set_clear_enabled_toggle(self):
        """Test toggling console clearing state multiple times."""
        set_clear_enabled(True)
        assert is_clear_enabled() is True

        set_clear_enabled(False)
        assert is_clear_enabled() is False

        set_clear_enabled(True)
        assert is_clear_enabled() is True


class TestClearConsole:
    """Tests for clear_console() function."""

    @patch("src.utils.console.os.system")
    @patch("src.utils.console.sys.platform", "win32")
    def test_clear_console_windows_enabled(self, mock_system):
        """Test clear_console() calls 'cls' on Windows when enabled."""
        set_clear_enabled(True)
        clear_console()
        mock_system.assert_called_once_with("cls")

    @patch("src.utils.console.os.system")
    @patch("src.utils.console.sys.platform", "linux")
    def test_clear_console_unix_enabled(self, mock_system):
        """Test clear_console() calls 'clear' on Unix/Linux when enabled."""
        set_clear_enabled(True)
        clear_console()
        mock_system.assert_called_once_with("clear")

    @patch("src.utils.console.os.system")
    @patch("src.utils.console.sys.platform", "darwin")
    def test_clear_console_macos_enabled(self, mock_system):
        """Test clear_console() calls 'clear' on macOS when enabled."""
        set_clear_enabled(True)
        clear_console()
        mock_system.assert_called_once_with("clear")

    @patch("src.utils.console.os.system")
    def test_clear_console_disabled(self, mock_system):
        """Test clear_console() does nothing when disabled."""
        set_clear_enabled(False)
        clear_console()
        mock_system.assert_not_called()

    @patch("src.utils.console.os.system")
    def test_clear_console_respects_state_changes(self, mock_system):
        """Test clear_console() respects state changes during execution."""
        # Enable -> should clear
        set_clear_enabled(True)
        clear_console()
        assert mock_system.call_count == 1

        # Disable -> should not clear
        set_clear_enabled(False)
        clear_console()
        assert mock_system.call_count == 1  # Still 1, no new call

        # Enable again -> should clear
        set_clear_enabled(True)
        clear_console()
        assert mock_system.call_count == 2


class TestClearAndBanner:
    """Tests for clear_and_banner() function."""

    @patch("src.utils.console.clear_console")
    def test_clear_and_banner_no_function(self, mock_clear):
        """Test clear_and_banner() with no banner function."""
        set_clear_enabled(True)
        clear_and_banner(banner_func=None)
        mock_clear.assert_called_once()

    @patch("src.utils.console.clear_console")
    def test_clear_and_banner_with_function(self, mock_clear):
        """Test clear_and_banner() calls banner function after clearing."""
        set_clear_enabled(True)
        banner_mock = MagicMock()

        clear_and_banner(banner_func=banner_mock)

        mock_clear.assert_called_once()
        banner_mock.assert_called_once()

    @patch("src.utils.console.clear_console")
    def test_clear_and_banner_calls_in_order(self, mock_clear):
        """Test clear_and_banner() calls clear BEFORE banner function."""
        set_clear_enabled(True)
        call_order = []

        def mock_clear_side_effect():
            call_order.append("clear")

        def mock_banner_side_effect():
            call_order.append("banner")

        mock_clear.side_effect = mock_clear_side_effect
        banner_mock = MagicMock(side_effect=mock_banner_side_effect)

        clear_and_banner(banner_func=banner_mock)

        assert call_order == ["clear", "banner"]

    @patch("src.utils.console.clear_console")
    def test_clear_and_banner_when_disabled(self, mock_clear):
        """Test clear_and_banner() respects disabled state."""
        set_clear_enabled(False)
        banner_mock = MagicMock()

        clear_and_banner(banner_func=banner_mock)

        # clear_console() is called but does nothing internally when disabled
        mock_clear.assert_called_once()
        # Banner function should still be called even if clearing is disabled
        banner_mock.assert_called_once()

    @patch("src.utils.console.clear_console")
    def test_clear_and_banner_with_complex_banner(self, mock_clear):
        """Test clear_and_banner() with a banner function that prints multiple lines."""
        set_clear_enabled(True)

        def complex_banner():
            print("=" * 60)
            print("LEAGUE STATS COACH")
            print("=" * 60)

        # Should not raise any exceptions
        clear_and_banner(banner_func=complex_banner)
        mock_clear.assert_called_once()


class TestCrossPlatformBehavior:
    """Tests for cross-platform console clearing behavior."""

    @patch("src.utils.console.os.system")
    def test_windows_platform_detection(self, mock_system):
        """Test correct command is used on Windows."""
        set_clear_enabled(True)
        with patch("src.utils.console.sys.platform", "win32"):
            clear_console()
            mock_system.assert_called_with("cls")

    @patch("src.utils.console.os.system")
    def test_linux_platform_detection(self, mock_system):
        """Test correct command is used on Linux."""
        set_clear_enabled(True)
        with patch("src.utils.console.sys.platform", "linux"):
            clear_console()
            mock_system.assert_called_with("clear")

    @patch("src.utils.console.os.system")
    def test_macos_platform_detection(self, mock_system):
        """Test correct command is used on macOS."""
        set_clear_enabled(True)
        with patch("src.utils.console.sys.platform", "darwin"):
            clear_console()
            mock_system.assert_called_with("clear")

    @patch("src.utils.console.os.system")
    def test_cygwin_platform_detection(self, mock_system):
        """Test correct command is used on Cygwin (should use 'clear' not 'cls')."""
        set_clear_enabled(True)
        with patch("src.utils.console.sys.platform", "cygwin"):
            clear_console()
            mock_system.assert_called_with("clear")


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @patch("src.utils.console.os.system")
    def test_multiple_rapid_clears(self, mock_system):
        """Test multiple rapid clear_console() calls work correctly."""
        set_clear_enabled(True)
        for _ in range(10):
            clear_console()
        assert mock_system.call_count == 10

    @patch("src.utils.console.clear_console")
    def test_banner_function_exception_handling(self, mock_clear):
        """Test that exceptions in banner function don't break clear_and_banner()."""
        set_clear_enabled(True)

        def failing_banner():
            raise ValueError("Banner function failed")

        # Should raise the exception from banner function
        with pytest.raises(ValueError, match="Banner function failed"):
            clear_and_banner(banner_func=failing_banner)

        # But clear_console() should have been called before the exception
        mock_clear.assert_called_once()

    @patch("src.utils.console.os.system")
    def test_state_persistence_across_calls(self, mock_system):
        """Test that enabled state persists across multiple function calls."""
        # Set to False once
        set_clear_enabled(False)

        # Multiple clear_console() calls should all respect the False state
        for _ in range(5):
            clear_console()

        # os.system should never have been called
        mock_system.assert_not_called()

        # Now enable and verify it works
        set_clear_enabled(True)
        clear_console()
        mock_system.assert_called_once()


class TestIntegration:
    """Integration tests for typical usage patterns."""

    @patch("src.utils.console.os.system")
    def test_typical_main_loop_pattern(self, mock_system):
        """Test typical usage pattern: clear at start of main loop."""
        set_clear_enabled(True)

        # Simulate main loop iterations
        for iteration in range(3):
            clear_console()
            # User would see menu here
            # User selects option
            # Submenu runs and clears again
            clear_console()

        # Should have cleared 6 times (2 per iteration)
        assert mock_system.call_count == 6

    @patch("src.utils.console.os.system")
    def test_debug_mode_pattern(self, mock_system):
        """Test typical usage pattern: debug mode with --no-clear flag."""
        # Simulate --no-clear flag
        set_clear_enabled(False)

        # Run through several menu cycles
        for _ in range(5):
            clear_console()

        # Should never have cleared
        mock_system.assert_not_called()

    @patch("src.utils.console.os.system")
    def test_banner_redisplay_pattern(self, mock_system):
        """Test typical usage pattern: clear and re-display banner each loop."""
        set_clear_enabled(True)

        def print_banner():
            print("=" * 60)
            print("LEAGUE STATS COACH v1.1.0")
            print("=" * 60)

        # Simulate 3 menu loop iterations
        for _ in range(3):
            clear_and_banner(banner_func=print_banner)

        # Should have cleared 3 times (once per iteration)
        assert mock_system.call_count == 3
