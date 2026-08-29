"""Regression test for the risk introduced by SPEC-02 (single page visit).

Before SPEC-02, matchups and synergies were scraped via two fully independent
page loads: a failure reading synergies had zero effect on matchups, because
they never shared any state.

SPEC-02 merges both extractions into one page visit (Parser.get_champion_page_data
-> ParallelParser.parse_page_by_role), which introduces a new failure mode: a
bug in the "click Synergies tab" step could, in principle, wipe out or skip
the matchups that were already successfully extracted moments earlier on the
same page.

This is exactly the risk SPEC-02 §3.4 calls out as the reason the task is
difficulty 8 rather than 5, and its acceptance criteria requires a dedicated
test for it: "Un champion dont l'onglet synergies échoue conserve ses
matchups en base et apparaît dans synergies_missing."

Author: @pj35 - LeagueStats Coach
"""

from unittest.mock import MagicMock, patch

from selenium.common.exceptions import NoSuchElementException, TimeoutException

from src.parallel_parser import ParallelParser
from src.parser import Parser


class TestParserKeepsMatchupsWhenSynergiesTabFails:
    """Parser.get_champion_page_data() must never let a synergies failure
    drop matchups already read off the same page."""

    def _parser(self):
        with patch("src.parser.webdriver.Firefox") as mock_firefox:
            mock_firefox.return_value = MagicMock()
            p = Parser(headless=True)
            p.webdriver = MagicMock()
            return p

    def test_synergies_button_not_found_keeps_matchups(self):
        parser = self._parser()
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with (
            patch.object(parser, "_load_champion_page"),
            patch.object(parser, "_extract_carousel_rows", return_value=matchups),
        ):
            parser.webdriver.find_element.side_effect = NoSuchElementException()
            result_matchups, result_synergies = parser.get_champion_page_data(
                "14.23", "yasuo", "middle"
            )

        assert result_matchups == matchups, "Matchups must survive a missing synergies tab"
        assert result_synergies == []

    def test_synergies_section_timeout_keeps_matchups(self):
        parser = self._parser()
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with (
            patch.object(parser, "_load_champion_page"),
            patch.object(
                parser,
                "_extract_carousel_rows",
                side_effect=[matchups, []],  # matchups ok, synergies section never renders
            ),
        ):
            result_matchups, result_synergies = parser.get_champion_page_data(
                "14.23", "yasuo", "middle"
            )

        assert result_matchups == matchups
        assert result_synergies == []

    def test_synergies_click_raises_unexpected_error_keeps_matchups(self):
        parser = self._parser()
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with (
            patch.object(parser, "_load_champion_page"),
            patch.object(parser, "_extract_carousel_rows", return_value=matchups),
        ):
            button = MagicMock()
            button.click.side_effect = TimeoutException("stale button")
            parser.webdriver.find_element.return_value = button

            result_matchups, result_synergies = parser.get_champion_page_data(
                "14.23", "yasuo", "middle"
            )

        assert result_matchups == matchups
        assert result_synergies == []


class TestPipelineKeepsMatchupsWhenSynergiesTabFails:
    """ParallelParser.parse_page_by_role() must write the matchups and flag
    the champion in synergies_missing, never drop the champion entirely."""

    def test_partial_failure_writes_matchups_and_flags_champion(self):
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with patch("src.parallel_parser.Parser") as mock_parser_class:
            mock_parser_class.return_value = MagicMock()
            pp = ParallelParser(max_workers=1)

            db = MagicMock()
            db.build_champion_cache.return_value = {}

            with patch.object(
                pp,
                "_scrape_champion_page_with_retry",
                return_value=("Aatrox", matchups, []),
            ):
                stats = pp.parse_page_by_role(db, ["Aatrox"], "top", str.lower)

            pp.close()

        db.add_matchups_batch.assert_called_once()
        db.add_synergies_batch.assert_not_called()
        assert stats["failed"] == 0
        assert stats["success"] == 1
        assert stats["synergies_missing"] == ["Aatrox"]
