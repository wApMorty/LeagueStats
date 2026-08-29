"""Tests for ParallelParser.parse_page_by_role() (SPEC-02 — single page visit).

Before SPEC-02, matchups and synergies were scraped in two sequential passes
(parse_champions_by_role then parse_synergies_by_role), each loading every
page again. parse_page_by_role() replaces both with one pass: one call to
_scrape_champion_page_with_retry() per champion, which loads the page once
and returns (champion, matchups, synergies).

All tests patch src.parallel_parser.Parser so no real Firefox/geckodriver is
spawned, and stub _scrape_champion_page_with_retry directly (its own retry
behavior is covered by tests/regression/test_regression_parallel_parser_fixes.py).

Author: @pj35 - LeagueStats Coach
"""

from unittest.mock import MagicMock, patch

import pytest

from src.parallel_parser import ParallelParser


@pytest.fixture
def pp():
    with patch("src.parallel_parser.Parser") as mock_parser_class:
        mock_parser_class.return_value = MagicMock()
        instance = ParallelParser(max_workers=2)
        yield instance
        instance.close()


def _make_db():
    db = MagicMock()
    db.build_champion_cache.return_value = {}
    return db


class TestParsePageByRole:
    def test_one_page_load_per_champion(self, pp):
        """The whole point of SPEC-02: one scrape call per champion, not two."""
        db = _make_db()
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]
        synergies = [("malphite", 55.0, 180.0, 220.0, 15.0, 1200)]

        with patch.object(
            pp,
            "_scrape_champion_page_with_retry",
            side_effect=lambda champ, lane, nf, inc_syn: (champ, matchups, synergies),
        ) as mock_scrape:
            stats = pp.parse_page_by_role(db, ["Aatrox", "Caitlyn"], "top", str.lower)

        assert mock_scrape.call_count == 2
        assert stats["success"] == 2
        assert stats["failed"] == 0
        assert stats["total"] == 2
        assert stats["synergies_missing"] == []

    def test_matchups_and_synergies_written_when_both_present(self, pp):
        db = _make_db()
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]
        synergies = [("malphite", 55.0, 180.0, 220.0, 15.0, 1200)]

        with patch.object(
            pp,
            "_scrape_champion_page_with_retry",
            return_value=("Aatrox", matchups, synergies),
        ):
            pp.parse_page_by_role(db, ["Aatrox"], "top", str.lower)

        db.add_matchups_batch.assert_called_once()
        db.add_synergies_batch.assert_called_once()

    def test_synergies_missing_keeps_matchups_written(self, pp):
        """SPEC-02 §3.4: a champion whose synergies tab failed must still have
        its matchups persisted, and be flagged in synergies_missing."""
        db = _make_db()
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with patch.object(
            pp,
            "_scrape_champion_page_with_retry",
            return_value=("Aatrox", matchups, []),
        ):
            stats = pp.parse_page_by_role(db, ["Aatrox"], "top", str.lower)

        db.add_matchups_batch.assert_called_once()
        db.add_synergies_batch.assert_not_called()
        assert stats["success"] == 1
        assert stats["failed"] == 0
        assert stats["synergies_missing"] == ["Aatrox"]

    def test_empty_matchups_marks_champion_failed(self, pp):
        """Matchups empty (page never rendered) -> failed, nothing written."""
        db = _make_db()

        with patch.object(pp, "_scrape_champion_page_with_retry", return_value=("Aatrox", [], [])):
            stats = pp.parse_page_by_role(db, ["Aatrox"], "top", str.lower)

        db.add_matchups_batch.assert_not_called()
        db.add_synergies_batch.assert_not_called()
        assert stats["success"] == 0
        assert stats["failed"] == 1
        assert stats["synergies_missing"] == []

    def test_include_matchups_false_skips_matchup_write_only(self, pp):
        """Matchups are still fetched (free on this page visit, and gate
        success/failure) but not persisted when the caller only wants
        synergies (mirrors the legacy 'Synergy statistics' menu option)."""
        db = _make_db()
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]
        synergies = [("malphite", 55.0, 180.0, 220.0, 15.0, 1200)]

        with patch.object(
            pp,
            "_scrape_champion_page_with_retry",
            return_value=("Aatrox", matchups, synergies),
        ):
            stats = pp.parse_page_by_role(db, ["Aatrox"], "top", str.lower, include_matchups=False)

        db.add_matchups_batch.assert_not_called()
        db.add_synergies_batch.assert_called_once()
        assert stats["success"] == 1

    def test_include_synergies_false_skips_synergies_entirely(self, pp):
        db = _make_db()
        matchups = [("zed", 52.0, 10.0, 20.0, 15.0, 500)]

        with patch.object(
            pp,
            "_scrape_champion_page_with_retry",
            side_effect=lambda champ, lane, nf, inc_syn: (champ, matchups, []),
        ) as mock_scrape:
            stats = pp.parse_page_by_role(db, ["Aatrox"], "top", str.lower, include_synergies=False)

        # include_synergies=False is threaded through to the scrape call
        assert mock_scrape.call_args.args[3] is False
        db.add_synergies_batch.assert_not_called()
        # A champion never asked for synergies isn't flagged as missing them
        assert stats["synergies_missing"] == []

    def test_init_tables_true_refreshes_roster_and_resets_tables(self, pp):
        db = _make_db()

        with patch.object(pp, "_scrape_champion_page_with_retry", return_value=("Aatrox", [], [])):
            pp.parse_page_by_role(db, ["Aatrox"], "top", str.lower, init_tables=True)

        db.update_champions_from_riot_api.assert_called_once()
        db.init_matchups_table.assert_called_once()
        db.init_synergies_table.assert_called_once()

    def test_init_tables_false_never_touches_schema(self, pp):
        db = _make_db()

        with patch.object(pp, "_scrape_champion_page_with_retry", return_value=("Aatrox", [], [])):
            pp.parse_page_by_role(db, ["Aatrox"], "top", str.lower, init_tables=False)

        db.update_champions_from_riot_api.assert_not_called()
        db.init_matchups_table.assert_not_called()
        db.init_synergies_table.assert_not_called()
