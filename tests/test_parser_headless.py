"""
Tests for Parser Headless Mode.

Validates that headless mode:
- Skips coordinate-based cookie fallback
- Verifies page structure after cookie handling
- Logs critical error if page fails to load
- Handles NoSuchElementException gracefully

Author: @pj35 - LeagueStats Coach
"""

import pytest
import logging
from unittest.mock import MagicMock, patch
from selenium.common.exceptions import NoSuchElementException

from src.parser import Parser


class TestParserHeadlessMode:
    """Test Parser headless mode behavior."""

    @pytest.fixture
    def headless_parser(self, mocker):
        """Create Parser in headless mode with mocked WebDriver."""
        with patch('src.parser.webdriver.Firefox') as mock_firefox:
            mock_driver = MagicMock()
            mock_firefox.return_value = mock_driver

            parser = Parser(headless=True)
            parser.webdriver = mock_driver

            yield parser

    def test_headless_mode_skips_coordinate_fallback(self, headless_parser):
        """Test that headless mode does NOT use coordinate-based fallback."""
        # All DOM strategies fail
        headless_parser.webdriver.find_element.side_effect = NoSuchElementException()

        headless_parser._accept_cookies()

        # Should NOT call execute_script (coordinate strategy is GUI-only)
        headless_parser.webdriver.execute_script.assert_not_called()

    def test_headless_mode_verifies_page_load_success(self, headless_parser, caplog):
        """Test that headless mode verifies page structure when loaded successfully."""
        caplog.set_level(logging.INFO)

        # Simulate all DOM strategies fail, but body element exists (page loaded)
        call_count = 0
        def find_element_side_effect(by, value):
            nonlocal call_count
            call_count += 1
            if value == "body":
                # Last call is verification - return mock body
                return MagicMock()
            else:
                # Cookie banner searches fail
                raise NoSuchElementException()

        headless_parser.webdriver.find_element.side_effect = find_element_side_effect

        headless_parser._accept_cookies()

        # Should log skip message and verification success
        assert "Skipping coordinate-based cookie fallback" in caplog.text
        assert "Page structure verified" in caplog.text
        assert "cookie banner handled successfully" in caplog.text

    def test_headless_mode_logs_page_load_failure(self, headless_parser, caplog):
        """Test that headless mode logs CRITICAL error if page fails to load."""
        caplog.set_level(logging.CRITICAL)

        # All elements fail (including body verification)
        headless_parser.webdriver.find_element.side_effect = NoSuchElementException()

        headless_parser._accept_cookies()

        # Should log critical error with error ID
        assert "[ERR_COOKIE_005]" in caplog.text
        assert "CRITICAL" in caplog.text
        assert "Page failed to load" in caplog.text

    def test_headless_mode_logs_skip_message(self, headless_parser, caplog):
        """Test that headless mode logs why coordinate fallback is skipped."""
        caplog.set_level(logging.INFO)

        # Make all cookie banner searches fail, but body verification succeeds
        def find_element_side_effect(by, value):
            if value == "body":
                # Body verification succeeds
                return MagicMock()
            else:
                # Cookie banner searches fail
                raise NoSuchElementException()

        headless_parser.webdriver.find_element.side_effect = find_element_side_effect

        headless_parser._accept_cookies()

        # Should explain why coordinates are skipped
        assert "Skipping coordinate-based cookie fallback in headless mode" in caplog.text
        assert "DOM strategies sufficient" in caplog.text

    def test_headless_mode_returns_after_skip(self, headless_parser):
        """Test that headless mode returns early (doesn't execute GUI strategies)."""
        # Body exists
        mock_body = MagicMock()
        headless_parser.webdriver.find_element.return_value = mock_body

        headless_parser._accept_cookies()

        # Should NOT attempt JavaScript or ActionChains (GUI strategies)
        headless_parser.webdriver.execute_script.assert_not_called()


class TestParserGUIMode:
    """Test Parser GUI mode still uses coordinates."""

    @pytest.fixture
    def gui_parser(self, mocker):
        """Create Parser in GUI mode with mocked WebDriver."""
        with patch('src.parser.webdriver.Firefox') as mock_firefox:
            mock_driver = MagicMock()
            mock_firefox.return_value = mock_driver

            parser = Parser(headless=False)
            parser.webdriver = mock_driver

            yield parser

    def test_gui_mode_attempts_coordinate_fallback(self, gui_parser, caplog):
        """Test that GUI mode still tries coordinate-based fallback."""
        caplog.set_level(logging.INFO)

        # All DOM strategies fail
        gui_parser.webdriver.find_element.side_effect = NoSuchElementException()

        # Mock successful JavaScript click
        gui_parser.webdriver.execute_script.return_value = None

        gui_parser._accept_cookies()

        # Should attempt JavaScript coordinate click (not skip it)
        gui_parser.webdriver.execute_script.assert_called_once()

        # Should NOT log headless skip message
        assert "Skipping coordinate-based cookie fallback" not in caplog.text

    def test_gui_mode_does_not_verify_body(self, gui_parser):
        """Test that GUI mode doesn't verify body element (only headless does)."""
        # All DOM strategies fail
        gui_parser.webdriver.find_element.side_effect = NoSuchElementException()

        # Mock successful JavaScript click
        gui_parser.webdriver.execute_script.return_value = None

        gui_parser._accept_cookies()

        # Should only call find_element for cookie banner searches + coordinate strategies
        # Should NOT call find_element with "body" argument
        find_element_calls = gui_parser.webdriver.find_element.call_args_list

        # Check that "body" was not searched for (only cookie banner elements)
        body_calls = [call for call in find_element_calls if len(call[0]) > 1 and call[0][1] == "body"]
        assert len(body_calls) == 0, "GUI mode should not verify body element"
