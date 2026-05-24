"""
Tests for Parser headless mode (Playwright version).

Validates that:
- headless=True prints an info message to stdout.
- headless=False (GUI) produces no such message.
- Both modes use the same Playwright-based cookie strategies.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.parser import Parser


# ---------------------------------------------------------------------------
# Fixture: a factory for Parser instances with mocked Playwright
# ---------------------------------------------------------------------------


def make_parser(headless: bool):
    """Create a Parser with mocked Playwright, return (parser, mock_page)."""
    mock_pw_ctx = MagicMock()
    mock_pw = MagicMock()
    mock_browser = MagicMock()
    mock_context = MagicMock()
    mock_page = MagicMock()

    mock_pw_ctx.start.return_value = mock_pw
    mock_pw.chromium.launch.return_value = mock_browser
    mock_browser.new_context.return_value = mock_context
    mock_context.new_page.return_value = mock_page

    with patch("src.parser.sync_playwright", return_value=mock_pw_ctx):
        with patch("src.parser.Stealth"):
            parser = Parser(headless=headless)

    return parser, mock_page


# ---------------------------------------------------------------------------
# Headless flag behaviour
# ---------------------------------------------------------------------------


class TestParserHeadlessMode:
    """Test Parser headless mode behaviour."""

    def test_headless_true_prints_info_message(self, capsys):
        """headless=True must print a message indicating headless mode is active."""
        parser, _ = make_parser(headless=True)
        out, _ = capsys.readouterr()
        assert "headless" in out.lower()

    def test_headless_false_no_headless_message(self, capsys):
        """headless=False (GUI mode) must not print a headless-mode message."""
        parser, _ = make_parser(headless=False)
        out, _ = capsys.readouterr()
        assert "headless mode enabled" not in out.lower()

    def test_headless_attribute_stored(self):
        """Parser must expose the headless attribute for introspection."""
        parser, _ = make_parser(headless=True)
        assert parser.headless is True

        parser2, _ = make_parser(headless=False)
        assert parser2.headless is False

    def test_chromium_launched_with_correct_headless_flag(self):
        """Playwright chromium.launch() must be called with the headless argument."""
        mock_pw_ctx = MagicMock()
        mock_pw = MagicMock()
        mock_browser = MagicMock()
        mock_context = MagicMock()
        mock_page = MagicMock()

        mock_pw_ctx.start.return_value = mock_pw
        mock_pw.chromium.launch.return_value = mock_browser
        mock_browser.new_context.return_value = mock_context
        mock_context.new_page.return_value = mock_page

        with patch("src.parser.sync_playwright", return_value=mock_pw_ctx):
            with patch("src.parser.Stealth"):
                Parser(headless=True)

        launch_kwargs = mock_pw.chromium.launch.call_args
        assert launch_kwargs.kwargs.get("headless") is True or (
            launch_kwargs.args and launch_kwargs.args[0] is True
        )


# ---------------------------------------------------------------------------
# Cookie strategies: same in both modes
# ---------------------------------------------------------------------------


class TestParserHeadlessCookies:
    """In both headless and GUI mode, cookie strategies are identical."""

    def test_headless_uses_query_selector_for_cookies(self):
        """Headless mode must use page.query_selector (not coordinate-based click)."""
        parser, mock_page = make_parser(headless=True)
        mock_page.query_selector.return_value = None

        parser._accept_cookies()

        mock_page.query_selector.assert_called()

    def test_gui_uses_query_selector_for_cookies(self):
        """GUI mode must also use page.query_selector (no special coordinate path)."""
        parser, mock_page = make_parser(headless=False)
        mock_page.query_selector.return_value = None

        parser._accept_cookies()

        mock_page.query_selector.assert_called()
