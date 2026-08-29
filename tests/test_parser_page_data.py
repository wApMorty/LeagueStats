"""Tests for Parser.get_champion_page_data() (SPEC-02 — single page visit).

Before SPEC-02, matchups and synergies were scraped via two independent page
loads (get_champion_data_on_patch / get_champion_synergies_on_patch), each
re-doing the URL load, cookie banner and lazy-load scroll. get_champion_page_data()
loads the page once and reads both carousels off it.

These tests mock _load_champion_page() and _extract_carousel_rows() (the two
building blocks introduced by the refactor) rather than the raw Selenium DOM:
the DOM-walking logic itself is unchanged line-for-line from the pre-SPEC-02
methods and isn't covered by a dedicated unit test in this codebase either.
What matters here is the new orchestration: one page load, up to two
extractions, and the fallback behavior when the synergies tab is missing.

Author: @pj35 - LeagueStats Coach
"""

from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import NoSuchElementException

from src.parser import Parser


@pytest.fixture
def parser():
    """Create Parser with a mocked WebDriver (no real Firefox)."""
    with patch("src.parser.webdriver.Firefox") as mock_firefox:
        mock_firefox.return_value = MagicMock()
        p = Parser(headless=True)
        p.webdriver = MagicMock()
        yield p


class TestGetChampionPageData:
    def test_returns_matchups_and_synergies_from_one_page_load(self, parser):
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]
        synergies = [("malphite", 55.0, 180.0, 220.0, 15.0, 1200)]

        with (
            patch.object(parser, "_load_champion_page") as mock_load,
            patch.object(
                parser, "_extract_carousel_rows", side_effect=[matchups, synergies]
            ) as mock_extract,
        ):
            result = parser.get_champion_page_data("14.23", "yasuo", "middle")

        mock_load.assert_called_once_with("14.23", "yasuo", "middle")
        assert result == (matchups, synergies)

        # First extraction is matchups (5 tiers), second is synergies (4 tiers)
        assert mock_extract.call_count == 2
        first_call, second_call = mock_extract.call_args_list
        assert first_call.args[1] == range(2, 7)
        assert first_call.args[2] == "Matchup"
        assert second_call.args[1] == range(2, 6)
        assert second_call.args[2] == "Synergy"

        parser.webdriver.find_element.assert_called_once()

    def test_synergies_button_missing_keeps_matchups(self, parser):
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with (
            patch.object(parser, "_load_champion_page"),
            patch.object(parser, "_extract_carousel_rows", return_value=matchups) as mock_extract,
        ):
            parser.webdriver.find_element.side_effect = NoSuchElementException()

            result = parser.get_champion_page_data("14.23", "yasuo")

        # Matchups extracted once; synergies tab never found -> no second extraction
        assert result == (matchups, [])
        assert mock_extract.call_count == 1

    def test_synergies_section_never_renders_keeps_matchups(self, parser):
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with (
            patch.object(parser, "_load_champion_page"),
            patch.object(parser, "_extract_carousel_rows", side_effect=[matchups, []]),
        ):
            # Button found and clicked, but the synergies carousel never renders
            result = parser.get_champion_page_data("14.23", "yasuo")

        assert result == (matchups, [])

    def test_empty_matchups_returns_both_empty_without_trying_synergies(self, parser):
        with (
            patch.object(parser, "_load_champion_page"),
            patch.object(parser, "_extract_carousel_rows", return_value=[]) as mock_extract,
        ):
            result = parser.get_champion_page_data("14.23", "yasuo")

        assert result == ([], [])
        # Matchups section never rendered -> don't even attempt the synergies tab
        assert mock_extract.call_count == 1
        parser.webdriver.find_element.assert_not_called()

    def test_include_synergies_false_skips_synergies_tab(self, parser):
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with (
            patch.object(parser, "_load_champion_page"),
            patch.object(parser, "_extract_carousel_rows", return_value=matchups) as mock_extract,
        ):
            result = parser.get_champion_page_data("14.23", "yasuo", include_synergies=False)

        assert result == (matchups, [])
        assert mock_extract.call_count == 1
        parser.webdriver.find_element.assert_not_called()


class TestLegacyWrappersDelegateToPageData:
    """get_champion_data_on_patch / get_champion_synergies_on_patch must stay
    thin wrappers around get_champion_page_data() (SPEC-02 §3.1 point 4):
    scripts/repair_data.py still calls them directly."""

    def test_get_champion_data_on_patch_returns_matchups_only(self, parser):
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with patch.object(
            parser, "get_champion_page_data", return_value=(matchups, [])
        ) as mock_page_data:
            result = parser.get_champion_data_on_patch("14.23", "yasuo", "middle")

        mock_page_data.assert_called_once_with("14.23", "yasuo", "middle", include_synergies=False)
        assert result == matchups

    def test_get_champion_synergies_on_patch_returns_synergies_only(self, parser):
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]
        synergies = [("malphite", 55.0, 180.0, 220.0, 15.0, 1200)]

        with patch.object(
            parser, "get_champion_page_data", return_value=(matchups, synergies)
        ) as mock_page_data:
            result = parser.get_champion_synergies_on_patch("14.23", "yasuo", "middle")

        mock_page_data.assert_called_once_with("14.23", "yasuo", "middle", include_synergies=True)
        assert result == synergies
