"""
Regression test for parser.py list index out of range bug.

Bug Description:
    When scraping champion matchups from LoLalytics, the parser accessed
    indices [4], [5], [6] of the "my-1" elements list without checking
    if the list had enough elements. This caused "list index out of range"
    errors for some champions (Aatrox, Amumu, Ahri, etc.) when LoLalytics
    HTML structure changed or had missing elements.

Root Cause:
    Lines 328-336 in src/parser.py directly accessed list indices:
        delta1 = float(elem.find_elements(By.CLASS_NAME, "my-1")[4]...)
        delta2 = float(elem.find_elements(By.CLASS_NAME, "my-1")[5]...)
        pickrate = float(elem.find_elements(By.CLASS_NAME, "my-1")[6]...)

Fix:
    - Store "my-1" elements in a variable
    - Check list length >= 7 before accessing indices
    - Log warning and skip matchup if insufficient elements
    - Wrap in try-except to catch any parsing errors

Impact:
    10 champions failed to parse completely (0 matchups inserted):
    Aatrox, Ahri, Akali, Alistar, Ambessa, Amumu, Anivia, Aphelios,
    Aurora, Heimerdinger

Date: 2026-01-06
Fixed by: hotfix/parser-list-index-fix
"""

import logging
import pytest
from unittest.mock import Mock, MagicMock, patch
from selenium.common.exceptions import NoSuchElementException

from src.parser import Parser


class TestParserListIndexFix:
    """Test suite for parser list index validation fix."""

    @pytest.fixture
    def mock_parser(self):
        """Create a Parser instance with mocked WebDriver."""
        with patch("src.parser.webdriver.Firefox") as mock_firefox:
            mock_driver = MagicMock()
            mock_firefox.return_value = mock_driver

            parser = Parser(headless=True)
            parser.webdriver = mock_driver
            return parser

    def test_insufficient_my1_elements_logs_warning_and_skips(self, mock_parser, caplog):
        """
        Test that parser logs warning and skips matchup when
        'my-1' elements list has < 7 items.

        This is the core regression test for the bug fix.
        """
        # Setup mock element with insufficient "my-1" elements (only 3 instead of 7)
        mock_elem = MagicMock()
        mock_link = MagicMock()
        mock_link.get_dom_attribute.return_value = (
            "https://lolalytics.com/lol/aatrox/vs/darius/build"
        )
        mock_elem.find_element.side_effect = lambda by, value: (
            mock_link
            if value == "a"
            else MagicMock(get_attribute=MagicMock(return_value="51.2%"))  # winrate span
        )

        # CRITICAL: Return only 3 "my-1" elements (bug scenario)
        mock_my1_elements = [MagicMock() for _ in range(3)]
        mock_elem.find_elements.return_value = mock_my1_elements

        # Setup mock row
        mock_parser.webdriver.find_elements.return_value = [mock_elem]

        # Mock move_to_element to prevent errors
        with patch("src.parser.ActionChains") as mock_actions:
            mock_actions.return_value = MagicMock(
                move_to_element_with_offset=MagicMock(return_value=MagicMock(perform=MagicMock())),
                click_and_hold=MagicMock(
                    return_value=MagicMock(
                        move_by_offset=MagicMock(
                            return_value=MagicMock(
                                release=MagicMock(
                                    return_value=MagicMock(
                                        move_by_offset=MagicMock(
                                            return_value=MagicMock(perform=MagicMock())
                                        )
                                    )
                                )
                            )
                        )
                    )
                ),
            )

            # Execute with logging enabled
            with caplog.at_level(logging.WARNING):
                result = mock_parser.parse_matchups_from_dom()

            # Verify warning was logged
            assert any(
                "Insufficient 'my-1' elements" in record.message
                and "found 3, expected ≥7" in record.message
                for record in caplog.records
            ), "Expected warning about insufficient elements not found in logs"

            # Verify matchup was skipped (empty result)
            assert len(result) == 0, "Matchup should be skipped when my-1 elements insufficient"

    def test_index_error_caught_and_logged(self, mock_parser, caplog):
        """
        Test that any IndexError during parsing is caught and logged.
        """
        # Setup mock element that raises IndexError when accessing my-1 elements
        mock_elem = MagicMock()
        mock_link = MagicMock()
        mock_link.get_dom_attribute.return_value = (
            "https://lolalytics.com/lol/amumu/vs/rammus/build"
        )
        mock_elem.find_element.side_effect = lambda by, value: (
            mock_link
            if value == "a"
            else MagicMock(get_attribute=MagicMock(return_value="48.7%"))  # winrate span
        )

        # Simulate IndexError when accessing elements
        mock_elem.find_elements.side_effect = IndexError("list index out of range")

        # Setup mock row
        mock_parser.webdriver.find_elements.return_value = [mock_elem]

        # Mock move_to_element to prevent errors
        with patch("src.parser.ActionChains") as mock_actions:
            mock_actions.return_value = MagicMock(
                move_to_element_with_offset=MagicMock(return_value=MagicMock(perform=MagicMock())),
                click_and_hold=MagicMock(
                    return_value=MagicMock(
                        move_by_offset=MagicMock(
                            return_value=MagicMock(
                                release=MagicMock(
                                    return_value=MagicMock(
                                        move_by_offset=MagicMock(
                                            return_value=MagicMock(perform=MagicMock())
                                        )
                                    )
                                )
                            )
                        )
                    )
                ),
            )

            # Execute with logging enabled
            with caplog.at_level(logging.WARNING):
                result = mock_parser.parse_matchups_from_dom()

            # Verify error was logged (not raised)
            assert any(
                "Failed to parse matchup element" in record.message
                and "IndexError" in record.message
                for record in caplog.records
            ), "Expected IndexError to be caught and logged"

            # Verify parsing continued (didn't crash)
            assert isinstance(result, list), "Parser should return list even after error"

    def test_valid_my1_elements_parsed_correctly(self, mock_parser):
        """
        Test that parser correctly extracts data when my-1 elements
        list has sufficient items (≥7).
        """
        # Setup mock element with valid "my-1" elements (7 items)
        mock_elem = MagicMock()
        mock_link = MagicMock()
        mock_link.get_dom_attribute.return_value = "https://lolalytics.com/lol/yasuo/vs/yone/build"

        # Setup winrate span
        mock_winrate_span = MagicMock()
        mock_winrate_span.get_attribute.return_value = "52.3%"

        # Setup games element
        mock_games_elem = MagicMock()
        mock_games_elem.get_attribute.return_value = "1,234"

        # Setup find_element to return appropriate mocks
        def mock_find_element(by, value):
            if value == "a":
                return mock_link
            elif "span" in str(value) or "div[1]" in str(value):
                return mock_winrate_span
            elif "text-" in value or r"text-\[9px\]" in value:
                return mock_games_elem
            return MagicMock()

        mock_elem.find_element.side_effect = mock_find_element

        # VALID: Return 7 "my-1" elements with proper values
        mock_my1_elements = []
        for i, value in enumerate(["val0", "val1", "val2", "val3", "2.5", "-1.8", "10.5"]):
            mock_el = MagicMock()
            mock_el.get_attribute.return_value = value
            mock_my1_elements.append(mock_el)

        mock_elem.find_elements.return_value = mock_my1_elements

        # Setup mock row
        mock_parser.webdriver.find_elements.return_value = [mock_elem]

        # Mock move_to_element to prevent errors
        with patch("src.parser.ActionChains") as mock_actions:
            mock_actions.return_value = MagicMock(
                move_to_element_with_offset=MagicMock(return_value=MagicMock(perform=MagicMock())),
                click_and_hold=MagicMock(
                    return_value=MagicMock(
                        move_by_offset=MagicMock(
                            return_value=MagicMock(
                                release=MagicMock(
                                    return_value=MagicMock(
                                        move_by_offset=MagicMock(
                                            return_value=MagicMock(perform=MagicMock())
                                        )
                                    )
                                )
                            )
                        )
                    )
                ),
            )

            # Execute
            result = mock_parser.parse_matchups_from_dom()

            # Verify matchup was parsed (not skipped)
            assert len(result) > 0, "Valid matchup should be parsed when my-1 elements sufficient"

            # Verify data extracted correctly
            champ, winrate, delta1, delta2, pickrate, games = result[0]
            assert champ == "yone", f"Expected 'yone', got '{champ}'"
            assert winrate == 52.3, f"Expected winrate 52.3, got {winrate}"
            assert delta1 == 2.5, f"Expected delta1 2.5, got {delta1}"
            assert delta2 == -1.8, f"Expected delta2 -1.8, got {delta2}"
            assert pickrate == 10.5, f"Expected pickrate 10.5, got {pickrate}"
            assert games == 1234, f"Expected games 1234, got {games}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
