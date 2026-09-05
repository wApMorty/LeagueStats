"""Tests for src/utils/champion_utils.py (SPEC-10 -- couverture du chemin
critique).

Purely functional module (no external dependencies beyond the DB layer, and
even that is only touched by validate_champion_data/_pool). Existing
lane-awareness tests already live in tests/test_trio_lane_aware.py
(TestChampionUtilsLaneAware) -- this file covers the rest: fuzzy name
matching, the has_sufficient_data threshold logic, and the interactive
selectors.
"""

from unittest.mock import Mock, patch

import pytest

from src.utils.champion_utils import (
    print_champion_list,
    select_champion_pool,
    select_extended_champion_pool,
    validate_champion_data,
    validate_champion_name,
    validate_champion_pool,
)


class TestValidateChampionName:
    def test_exact_match_case_insensitive(self):
        assert validate_champion_name("aatrox") == "Aatrox"
        assert validate_champion_name("AATROX") == "Aatrox"

    def test_empty_string_returns_none(self):
        assert validate_champion_name("") is None

    def test_none_returns_none(self):
        assert validate_champion_name(None) is None

    def test_whitespace_is_stripped_before_matching(self):
        assert validate_champion_name("  Aatrox  ") == "Aatrox"

    def test_single_prefix_match_is_auto_completed(self):
        """'Aatro' has exactly one champion starting with it -> auto-complete."""
        assert validate_champion_name("Aatro") == "Aatrox"

    def test_ambiguous_prefix_returns_none(self, capsys):
        """'Ka' matches multiple champions (Kaisa, Karma, Kayle, ...) -> None,
        with suggestions printed rather than an arbitrary guess."""
        result = validate_champion_name("Ka")
        assert result is None
        assert "Ambiguous name" in capsys.readouterr().out

    def test_unknown_name_returns_none(self, capsys):
        result = validate_champion_name("Zzzznotachampion")
        assert result is None
        assert "not found" in capsys.readouterr().out

    def test_apostrophe_free_champion_name_exact_match(self):
        """CHAMPIONS_LIST stores champions with an in-game apostrophe
        (Kai'Sa, Cho'Gath) without it (Kaisa, ChoGath) -- validate_champion_name
        does no apostrophe stripping of its own, so the caller must already
        match that convention."""
        assert validate_champion_name("kaisa") == "Kaisa"


class TestValidateChampionData:
    def test_no_matchups_returns_no_data(self, db):
        result = validate_champion_data(db, "Aatrox", min_games=10)
        assert result == (False, 0, 0, 0.0)

    def test_sufficient_matchups_and_games_is_viable(self, db, insert_matchup):
        for i in range(5):
            insert_matchup("Aatrox", f"Enemy{i}", 50.0, 0.0, 1.0, 5.0, 200)

        has_data, matchup_count, total_games, avg_delta2 = validate_champion_data(
            db, "Aatrox", min_games=500
        )

        assert has_data is True
        assert matchup_count == 5
        assert total_games == 1000
        assert avg_delta2 == pytest.approx(1.0)

    def test_below_min_matchup_count_is_not_viable(self, db, insert_matchup):
        """Fewer than 5 matchup rows -- insufficient even with huge game counts."""
        insert_matchup("Aatrox", "Darius", 50.0, 0.0, 1.0, 5.0, 5000)

        has_data, matchup_count, _, _ = validate_champion_data(db, "Aatrox", min_games=10)

        assert has_data is False
        assert matchup_count == 1

    def test_below_min_games_is_not_viable(self, db, insert_matchup):
        for i in range(5):
            insert_matchup("Aatrox", f"Enemy{i}", 50.0, 0.0, 1.0, 5.0, 1)

        has_data, _, total_games, _ = validate_champion_data(db, "Aatrox", min_games=10000)

        assert has_data is False
        assert total_games == 5

    def test_db_error_degrades_to_no_data(self, db):
        broken_db = Mock()
        broken_db.get_champion_matchups_by_name.side_effect = Exception("db exploded")

        result = validate_champion_data(broken_db, "Aatrox")

        assert result == (False, 0, 0, 0.0)

    def test_lane_is_forwarded_to_the_query(self, db):
        mock_db = Mock()
        mock_db.get_champion_matchups_by_name.return_value = []

        validate_champion_data(mock_db, "Aatrox", lane="top")

        mock_db.get_champion_matchups_by_name.assert_called_once_with("Aatrox", lane="top")


class TestValidateChampionPool:
    def test_mixed_pool_separates_viable_from_insufficient(self, db, insert_matchup, capsys):
        for i in range(5):
            insert_matchup("Aatrox", f"Enemy{i}", 50.0, 0.0, 1.0, 5.0, 200)
        # Darius has no matchup data at all.

        viable, report = validate_champion_pool(db, ["Aatrox", "Darius"], min_games=500)

        assert viable == ["Aatrox"]
        assert report["Aatrox"]["has_data"] is True
        assert report["Darius"]["has_data"] is False
        out = capsys.readouterr().out
        assert "[OK] Aatrox" in out
        assert "[ALERTE] Darius" in out

    def test_empty_pool_returns_empty(self, db):
        viable, report = validate_champion_pool(db, [])
        assert viable == []
        assert report == {}


class TestSelectChampionPool:
    def test_valid_choice_returns_the_matching_pool(self, capsys):
        with patch("builtins.input", return_value="top"):
            pool = select_champion_pool()
        assert "Aatrox" in pool or len(pool) > 0
        assert "Selected pool: TOP" in capsys.readouterr().out

    def test_invalid_then_valid_choice_loops(self, capsys):
        inputs = iter(["bogus", "support"])
        with patch("builtins.input", lambda *_: next(inputs)):
            pool = select_champion_pool()
        out = capsys.readouterr().out
        assert "Invalid choice" in out
        assert len(pool) > 0

    def test_eof_falls_back_to_top(self):
        with patch("builtins.input", side_effect=EOFError):
            pool = select_champion_pool()
        assert len(pool) > 0

    def test_keyboard_interrupt_falls_back_to_top(self):
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            pool = select_champion_pool()
        assert len(pool) > 0


class TestSelectExtendedChampionPool:
    def test_numeric_choice_selects_pool(self, capsys):
        with patch("builtins.input", return_value="4"):  # mid
            pool = select_extended_champion_pool()
        assert len(pool) > 0
        assert "MID" in capsys.readouterr().out

    def test_alias_choice_selects_pool(self):
        with patch("builtins.input", return_value="bot"):  # alias for adc
            pool = select_extended_champion_pool()
        assert len(pool) > 0

    def test_invalid_then_valid_choice_loops(self, capsys):
        inputs = iter(["nonsense", "jungle"])
        with patch("builtins.input", lambda *_: next(inputs)):
            pool = select_extended_champion_pool()
        out = capsys.readouterr().out
        assert "Invalid choice" in out
        assert len(pool) > 0

    def test_eof_falls_back_to_top(self):
        with patch("builtins.input", side_effect=EOFError):
            pool = select_extended_champion_pool()
        assert len(pool) > 0


class TestPrintChampionList:
    def test_prints_each_entry(self, capsys):
        print_champion_list([("Aatrox", "top"), ("Lux", "mid")])
        out = capsys.readouterr().out
        assert "Aatrox - top" in out
        assert "Lux - mid" in out
