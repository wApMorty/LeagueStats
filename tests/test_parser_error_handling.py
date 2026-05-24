"""
Tests for Parser._accept_cookies() — Playwright version.

Validates cookie banner dismissal strategies:
1. ID selector (#didomi-notice-agree-button)
2. CSS selectors (button[aria-label*='agree' i], etc.)
3. XPath patterns (text-based)
All exceptions in each strategy are silently caught (debug-logged) and fall through.
"""

import logging
import pytest
from unittest.mock import MagicMock, patch, call

from src.parser import Parser


# ---------------------------------------------------------------------------
# Fixture: Parser with mocked Playwright
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_parser():
    """Create Parser instance with mocked Playwright browser/context/page."""
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
            parser = Parser(headless=False)

    yield parser, mock_page


# ---------------------------------------------------------------------------
# Strategy 1 — ID selector
# ---------------------------------------------------------------------------


class TestAcceptCookiesStrategy1:
    """Tests for Strategy 1: #didomi-notice-agree-button ID selector."""

    def test_strategy1_clicks_when_element_found(self, mock_parser):
        """When ID selector returns an element, it should be clicked and method returns."""
        parser, page = mock_parser
        mock_btn = MagicMock()
        page.query_selector.return_value = mock_btn

        parser._accept_cookies()

        mock_btn.click.assert_called_once()

    def test_strategy1_falls_through_when_none(self, mock_parser, caplog):
        """When ID selector returns None, strategy 2 must be tried."""
        caplog.set_level(logging.DEBUG)
        parser, page = mock_parser
        # All selectors return None → falls through all strategies
        page.query_selector.return_value = None

        parser._accept_cookies()

        # Multiple query_selector calls attempted (ID + CSS + XPath)
        assert page.query_selector.call_count >= 2

    def test_strategy1_exception_silenced(self, mock_parser, caplog):
        """Exception in ID strategy must be silently caught and fall through."""
        caplog.set_level(logging.DEBUG)
        parser, page = mock_parser

        # ID raises, CSS and XPath return None
        def qsel_side_effect(selector):
            if selector == "#didomi-notice-agree-button":
                raise RuntimeError("selector failed")
            return None

        page.query_selector.side_effect = qsel_side_effect

        # Must not raise
        parser._accept_cookies()


# ---------------------------------------------------------------------------
# Strategy 2 — CSS selectors
# ---------------------------------------------------------------------------


class TestAcceptCookiesStrategy2:
    """Tests for Strategy 2: CSS-based cookie selectors."""

    def test_strategy2_clicks_first_matching_selector(self, mock_parser):
        """When first CSS selector matches, element is clicked and method returns."""
        parser, page = mock_parser
        mock_btn = MagicMock()

        def qsel_side_effect(selector):
            if "aria-label*='agree'" in selector or "aria-label*='accept'" in selector:
                return mock_btn
            return None

        page.query_selector.side_effect = qsel_side_effect

        parser._accept_cookies()

        mock_btn.click.assert_called_once()

    def test_strategy2_tries_all_selectors_on_failure(self, mock_parser):
        """When all CSS selectors fail (None), all must be tried before XPath fallback."""
        parser, page = mock_parser
        page.query_selector.return_value = None

        parser._accept_cookies()

        # At least ID + 4 CSS selectors + XPath patterns tried
        assert page.query_selector.call_count >= 5

    def test_strategy2_exception_silenced(self, mock_parser):
        """Exception in CSS strategy must not crash — falls through."""
        parser, page = mock_parser

        call_count = [0]

        def qsel_side_effect(selector):
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # ID fails
            raise RuntimeError("CSS failed")

        page.query_selector.side_effect = qsel_side_effect

        # Must not raise
        parser._accept_cookies()


# ---------------------------------------------------------------------------
# Strategy 3 — XPath
# ---------------------------------------------------------------------------


class TestAcceptCookiesStrategy3:
    """Tests for Strategy 3: XPath text-based patterns."""

    def test_strategy3_clicks_matching_xpath(self, mock_parser):
        """When XPath pattern matches, element is clicked and method returns."""
        parser, page = mock_parser
        mock_btn = MagicMock()

        call_count = [0]

        def qsel_side_effect(selector):
            call_count[0] += 1
            if "xpath=" in selector and "accept" in selector.lower():
                return mock_btn
            if call_count[0] == 1:
                return None  # ID selector returns None
            return None

        page.query_selector.side_effect = qsel_side_effect

        parser._accept_cookies()

        mock_btn.click.assert_called_once()

    def test_all_strategies_exhausted_logs_info(self, mock_parser, caplog):
        """When all strategies fail, an info log must be emitted."""
        caplog.set_level(logging.INFO)
        parser, page = mock_parser
        page.query_selector.return_value = None

        parser._accept_cookies()

        assert "no cookie banner" in caplog.text.lower() or "exhausted" in caplog.text.lower()

    def test_strategy3_exception_silenced(self, mock_parser):
        """Exception in XPath strategy must be silently caught."""
        parser, page = mock_parser

        call_count = [0]

        def qsel_side_effect(selector):
            call_count[0] += 1
            if call_count[0] <= 5:
                return None  # ID + CSS fail
            raise AttributeError("XPath failed")

        page.query_selector.side_effect = qsel_side_effect

        # Must not raise
        parser._accept_cookies()


# ---------------------------------------------------------------------------
# Success logging
# ---------------------------------------------------------------------------


class TestAcceptCookiesSuccess:
    """Verify correct log output on successful cookie dismissal."""

    def test_success_logs_via_id_selector(self, mock_parser, caplog):
        """Successful Strategy 1 dismissal must log an info message."""
        caplog.set_level(logging.INFO)
        parser, page = mock_parser
        page.query_selector.return_value = MagicMock()

        parser._accept_cookies()

        assert "cookie banner dismissed" in caplog.text.lower()
        assert "id selector" in caplog.text.lower()
