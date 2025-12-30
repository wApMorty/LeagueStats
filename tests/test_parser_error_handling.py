"""
Tests for Parser Exception Handling.

Validates that _accept_cookies() handles exceptions properly:
- Catches specific exceptions (NoSuchElementException, ElementNotInteractableException)
- Logs unexpected exceptions with error IDs
- Continues to next strategy when expected exceptions occur
- Reports unexpected errors without crashing

Author: @pj35 - LeagueStats Coach
"""

import pytest
import logging
from unittest.mock import MagicMock, patch
from selenium.common.exceptions import (
    NoSuchElementException,
    ElementNotInteractableException,
    InvalidSessionIdException,
    WebDriverException,
)

from src.parser import Parser


class TestCookieBannerExceptionHandling:
    """Test cookie banner exception handling strategies."""

    @pytest.fixture
    def mock_parser(self, mocker):
        """Create Parser with mocked WebDriver."""
        with patch('src.parser.webdriver.Firefox') as mock_firefox:
            mock_driver = MagicMock()
            mock_firefox.return_value = mock_driver

            parser = Parser(headless=False)
            parser.webdriver = mock_driver

            yield parser

    def test_strategy1_handles_no_such_element_gracefully(self, mock_parser, caplog):
        """Test that NoSuchElementException in Strategy 1 doesn't crash."""
        caplog.set_level(logging.INFO)

        # Mock ID selector to raise NoSuchElementException
        mock_parser.webdriver.find_element.side_effect = NoSuchElementException()

        # Should not raise, should try other strategies
        mock_parser._accept_cookies()

        # Should not log error (expected exception)
        assert "[ERR_COOKIE_001]" not in caplog.text

    def test_strategy1_logs_element_not_interactable(self, mock_parser, caplog):
        """Test that ElementNotInteractableException is logged with error ID."""
        caplog.set_level(logging.WARNING)

        # Mock element that exists but is not clickable
        mock_element = MagicMock()
        mock_element.click.side_effect = ElementNotInteractableException()
        mock_parser.webdriver.find_element.return_value = mock_element

        mock_parser._accept_cookies()

        # Should log warning with error ID
        assert "[ERR_COOKIE_004]" in caplog.text
        assert "not clickable" in caplog.text

    def test_strategy1_logs_unexpected_exceptions(self, mock_parser, caplog):
        """Test that unexpected exceptions are logged with error ID."""
        caplog.set_level(logging.ERROR)

        # Mock unexpected exception
        mock_parser.webdriver.find_element.side_effect = RuntimeError("Unexpected error")

        mock_parser._accept_cookies()

        # Should log error with error ID
        assert "[ERR_COOKIE_001]" in caplog.text
        assert "RuntimeError" in caplog.text

    def test_strategy2_css_continues_on_no_such_element(self, mock_parser, caplog):
        """Test that CSS strategy continues through all selectors."""
        caplog.set_level(logging.INFO)

        # All CSS selectors fail with NoSuchElementException
        mock_parser.webdriver.find_element.side_effect = NoSuchElementException()

        mock_parser._accept_cookies()

        # Should try multiple selectors (no crash)
        assert mock_parser.webdriver.find_element.call_count >= 4  # ID + CSS selectors

    def test_strategy2_css_logs_unexpected_error(self, mock_parser, caplog):
        """Test that CSS strategy logs unexpected errors."""
        caplog.set_level(logging.ERROR)

        # First call (ID) fails, then CSS raises unexpected error
        mock_parser.webdriver.find_element.side_effect = [
            NoSuchElementException(),  # ID fails
            ValueError("Unexpected CSS error"),  # First CSS selector fails unexpectedly
        ]

        mock_parser._accept_cookies()

        # Should log with ERR_COOKIE_002
        assert "[ERR_COOKIE_002]" in caplog.text
        assert "ValueError" in caplog.text

    def test_strategy3_xpath_continues_on_failure(self, mock_parser, caplog):
        """Test that XPath strategy continues through patterns."""
        caplog.set_level(logging.INFO)

        # All XPath patterns fail
        mock_parser.webdriver.find_element.side_effect = NoSuchElementException()

        mock_parser._accept_cookies()

        # Should try multiple XPath patterns (no crash)
        # ID + CSS (4) + XPath (3) = at least 8 calls
        assert mock_parser.webdriver.find_element.call_count >= 8

    def test_strategy3_xpath_logs_unexpected_error(self, mock_parser, caplog):
        """Test that XPath strategy logs unexpected errors."""
        caplog.set_level(logging.ERROR)

        # Make all ID/CSS fail normally, then XPath raises unexpected
        call_count = 0
        def side_effect_func(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 5:  # ID + CSS selectors
                raise NoSuchElementException()
            else:  # XPath
                raise AttributeError("Unexpected XPath error")

        mock_parser.webdriver.find_element.side_effect = side_effect_func

        mock_parser._accept_cookies()

        # Should log with ERR_COOKIE_003
        assert "[ERR_COOKIE_003]" in caplog.text
        assert "AttributeError" in caplog.text

    def test_strategy4_coordinate_logs_javascript_failure(self, mock_parser, caplog):
        """Test that coordinate strategy logs JavaScript execution failures."""
        caplog.set_level(logging.ERROR)

        # All DOM strategies fail
        mock_parser.webdriver.find_element.side_effect = NoSuchElementException()

        # JavaScript execution fails
        mock_parser.webdriver.execute_script.side_effect = RuntimeError("JS failed")

        # ActionChains also fails
        with patch('src.parser.ActionChains') as mock_actions:
            mock_chain = MagicMock()
            mock_chain.move_by_offset.return_value = mock_chain
            mock_chain.click.return_value = mock_chain
            mock_chain.perform.side_effect = RuntimeError("ActionChains failed")
            mock_actions.return_value = mock_chain

            mock_parser._accept_cookies()

        # Should log with ERR_COOKIE_006
        assert "[ERR_COOKIE_006]" in caplog.text

    def test_success_logs_info_message(self, mock_parser, caplog):
        """Test that successful cookie dismissal logs info message."""
        caplog.set_level(logging.INFO)

        # Mock successful ID selector click
        mock_element = MagicMock()
        mock_parser.webdriver.find_element.return_value = mock_element

        mock_parser._accept_cookies()

        # Should log success
        assert "Cookie banner dismissed" in caplog.text
        assert "ID selector" in caplog.text

    def test_headless_mode_skips_coordinates(self, mocker, caplog):
        """Test that headless mode skips coordinate-based fallback."""
        caplog.set_level(logging.INFO)

        with patch('src.parser.webdriver.Firefox') as mock_firefox:
            mock_driver = MagicMock()
            mock_firefox.return_value = mock_driver

            parser = Parser(headless=True)
            parser.webdriver = mock_driver

            # All DOM strategies fail
            parser.webdriver.find_element.side_effect = NoSuchElementException()

            parser._accept_cookies()

            # Should NOT call execute_script (coordinate strategy)
            parser.webdriver.execute_script.assert_not_called()


class TestWebDriverCrashHandling:
    """Regression tests for WebDriver crash handling (Problem A)."""

    @pytest.fixture
    def mock_parser(self, mocker):
        """Create Parser with mocked WebDriver."""
        with patch('src.parser.webdriver.Firefox') as mock_firefox:
            mock_driver = MagicMock()
            mock_firefox.return_value = mock_driver

            parser = Parser(headless=True)
            parser.webdriver = mock_driver

            yield parser

    def test_accept_cookies_webdriver_crash_id_strategy_raises(self, mock_parser, caplog):
        """Regression test: WebDriver crash in ID strategy raises exception."""
        caplog.set_level(logging.CRITICAL)

        # Mock find_element to raise InvalidSessionIdException
        mock_parser.webdriver.find_element.side_effect = InvalidSessionIdException("Session not found")

        # Should raise exception (not continue silently)
        with pytest.raises(InvalidSessionIdException):
            mock_parser._accept_cookies()

        # Should log ERR_COOKIE_007
        assert "[ERR_COOKIE_007]" in caplog.text
        assert "FATAL: WebDriver session lost" in caplog.text

    def test_accept_cookies_webdriver_exception_css_strategy_raises(self, mock_parser, caplog):
        """Regression test: WebDriverException in CSS strategy raises exception."""
        caplog.set_level(logging.CRITICAL)

        # ID strategy fails (expected), then CSS crashes
        mock_parser.webdriver.find_element.side_effect = [
            NoSuchElementException(),  # ID fails (expected)
            WebDriverException("Browser crashed"),  # CSS crashes
        ]

        # Should raise exception (not continue silently)
        with pytest.raises(WebDriverException):
            mock_parser._accept_cookies()

        # Should log ERR_COOKIE_007
        assert "[ERR_COOKIE_007]" in caplog.text
        assert "FATAL: WebDriver session lost" in caplog.text

    def test_accept_cookies_webdriver_crash_xpath_strategy_raises(self, mock_parser, caplog):
        """Regression test: WebDriver crash in XPath strategy raises exception."""
        caplog.set_level(logging.CRITICAL)

        # ID and CSS fail (expected), XPath crashes
        call_count = [0]

        def side_effect_fn(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] <= 5:  # ID + 4 CSS selectors
                raise NoSuchElementException()
            else:  # XPath crashes
                raise InvalidSessionIdException("Session lost")

        mock_parser.webdriver.find_element.side_effect = side_effect_fn

        # Should raise exception
        with pytest.raises(InvalidSessionIdException):
            mock_parser._accept_cookies()

        # Should log ERR_COOKIE_007
        assert "[ERR_COOKIE_007]" in caplog.text
        assert "FATAL: WebDriver session lost" in caplog.text
