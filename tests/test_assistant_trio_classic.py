"""Characterization tests for the "classic" trio/duo search of ``Assistant``.

Scope (SPEC TODO E10 — safety net before the extraction refactor):
- ``optimal_trio_from_pool``
- ``optimal_duo_for_champion``
- ``_find_optimal_counterpick_duo``
- ``_analyze_trio_tactics`` / ``_analyze_trio_coverage`` (console output)

These tests pin the CURRENT behavior of the code, not the desired one. Where
the code has a latent bug, the bug is asserted as-is and documented — the point
is to detect an accidental behavior change while the methods are moved to a new
module, NOT to fix anything.
"""

from unittest.mock import patch

import pytest

from src.assistant import Assistant

# Deterministic 6-champion universe. Every champion has a matchup against every
# other one (5 matchups, 5000 games total) so that validate_champion_data()
# considers them all viable (>= 5 matchups and >= 2000 games).
CHAMPIONS = ["Aatrox", "Darius", "Garen", "Teemo", "Malphite", "Sett"]

DELTAS = {
    ("Aatrox", "Darius"): 3.0,
    ("Aatrox", "Garen"): 2.0,
    ("Aatrox", "Teemo"): -3.5,
    ("Aatrox", "Malphite"): 1.0,
    ("Aatrox", "Sett"): 0.5,
    ("Darius", "Aatrox"): -3.0,
    ("Darius", "Garen"): 2.5,
    ("Darius", "Teemo"): -4.0,
    ("Darius", "Malphite"): -1.0,
    ("Darius", "Sett"): 1.5,
    ("Garen", "Aatrox"): -2.0,
    ("Garen", "Darius"): -2.5,
    ("Garen", "Teemo"): 3.0,
    ("Garen", "Malphite"): 0.5,
    ("Garen", "Sett"): -0.5,
    ("Teemo", "Aatrox"): 3.5,
    ("Teemo", "Darius"): 4.0,
    ("Teemo", "Garen"): -3.0,
    ("Teemo", "Malphite"): 2.0,
    ("Teemo", "Sett"): 1.0,
    ("Malphite", "Aatrox"): -1.0,
    ("Malphite", "Darius"): 1.0,
    ("Malphite", "Garen"): -0.5,
    ("Malphite", "Teemo"): -2.0,
    ("Malphite", "Sett"): 2.5,
    ("Sett", "Aatrox"): -0.5,
    ("Sett", "Darius"): -1.5,
    ("Sett", "Garen"): 0.5,
    ("Sett", "Teemo"): -1.0,
    ("Sett", "Malphite"): -2.5,
}


@pytest.fixture
def trio_assistant(db, insert_matchup):
    """Assistant wired on the temp DB, populated with the DELTAS universe."""
    for (champion, enemy), delta2 in DELTAS.items():
        insert_matchup(
            champion,
            enemy,
            winrate=50.0 + delta2,
            delta1=delta2 * 10,
            delta2=delta2,
            pickrate=5.0,
            games=1000,
        )
    return Assistant(db=db, verbose=False)


@pytest.fixture
def empty_assistant(db):
    """Assistant on an empty temp DB (no champion has any data)."""
    return Assistant(db=db, verbose=False)


class TestOptimalTrioFromPool:
    """Characterization of ``optimal_trio_from_pool()``."""

    def test_nominal_returns_blind_pick_duo_and_score(self, trio_assistant):
        """Nominal run over a 4-champion pool of the fixture universe.

        Pinned values follow directly from DELTAS:
        - best blind pick = highest avg delta2 = Teemo (+1.50)
        - best counterpick duo from the rest = (Darius, Garen), duo score 16.5
        - total = blind avg delta2 (1.5) + duo score (16.5) = 18.0
        """
        # Arrange
        pool = ["Aatrox", "Darius", "Garen", "Teemo"]

        # Act
        result = trio_assistant.optimal_trio_from_pool(pool)

        # Assert
        assert result == ("Teemo", "Darius", "Garen", pytest.approx(18.0))

    def test_nominal_prints_blind_pick_ranking(self, trio_assistant, capsys):
        """The blind-pick ranking block is printed, sorted by avg delta2."""
        # Act
        trio_assistant.optimal_trio_from_pool(["Aatrox", "Darius", "Garen", "Teemo"])
        out = capsys.readouterr().out

        # Assert
        assert "BLIND PICK RANKINGS:" in out
        assert "[OK] Selected blind pick: Teemo (avg delta2: 1.50)" in out
        assert "TOP DUO RANKINGS:" in out
        assert "[OK] Optimal trio: Teemo (blind) + Darius + Garen (counterpicks)" in out

    def test_pool_smaller_than_three_raises(self, trio_assistant):
        """Fewer than 3 champions is rejected before any DB access."""
        with pytest.raises(ValueError, match="at least 3 champions"):
            trio_assistant.optimal_trio_from_pool(["Aatrox", "Darius"])

    def test_pool_without_data_raises_insufficient_data(self, empty_assistant, capsys):
        """A pool of 3 unknown champions yields 0 viable champions."""
        with pytest.raises(ValueError, match=r"Insufficient data: only 0/3 champions viable"):
            empty_assistant.optimal_trio_from_pool(["Aatrox", "Darius", "Garen"])

        out = capsys.readouterr().out
        assert "[ERREUR] Only 0 champions have sufficient data." in out

    def test_partially_viable_pool_warns_and_still_runs(self, trio_assistant, capsys):
        """An unknown champion is dropped with an [ALERTE], the run continues."""
        # Arrange: "Nobody" has no data at all
        pool = ["Aatrox", "Darius", "Garen", "Teemo", "Nobody"]

        # Act
        result = trio_assistant.optimal_trio_from_pool(pool)
        out = capsys.readouterr().out

        # Assert
        assert "[ALERTE] Using 4 viable champions out of 5 requested" in out
        assert result[0] == "Teemo"


class TestOptimalDuoForChampion:
    """Characterization of ``optimal_duo_for_champion()``."""

    def test_nominal_returns_fixed_champion_first(self, trio_assistant):
        """The fixed champion is always index 0 of the returned trio."""
        # Act
        result = trio_assistant.optimal_duo_for_champion("Aatrox", CHAMPIONS)

        # Assert
        assert result[0] == "Aatrox"
        assert len(result) == 4
        assert isinstance(result[3], float)
        # The two companions come from the pool, minus the fixed champion.
        assert set(result[1:3]).issubset(set(CHAMPIONS) - {"Aatrox"})

    def test_nominal_total_score_is_fixed_avg_delta2_plus_duo_score(self, trio_assistant, capsys):
        """total_score = avg delta2 of the fixed champion + duo score.

        Aatrox avg delta2 over the fixture universe is +0.60, and the printed
        duo total score is the second term.
        """
        # Act
        result = trio_assistant.optimal_duo_for_champion("Aatrox", CHAMPIONS)
        out = capsys.readouterr().out

        # Assert
        assert "[OK] Fixed champion validated: 5 matchups, 5000 total games, 0.60 avg delta2" in out
        assert f"[OK] Optimal trio: Aatrox + {result[1]} + {result[2]}" in out

    def test_fixed_champion_without_data_raises(self, trio_assistant, capsys):
        """An unknown fixed champion aborts before the companion search."""
        with pytest.raises(ValueError, match="has insufficient data in database"):
            trio_assistant.optimal_duo_for_champion("Nobody", CHAMPIONS)

        out = capsys.readouterr().out
        assert "[ERREUR] Fixed champion 'Nobody' has insufficient data" in out

    def test_pool_with_less_than_two_companions_raises(self, trio_assistant):
        """The fixed champion is removed from the pool before counting."""
        with pytest.raises(ValueError, match="at least 2 champions besides the fixed one"):
            trio_assistant.optimal_duo_for_champion("Aatrox", ["Aatrox", "Darius"])

    def test_companions_without_data_raise_insufficient_companion_data(
        self, trio_assistant, capsys
    ):
        """Companions with no DB data are all filtered out."""
        with pytest.raises(ValueError, match=r"Insufficient companion data: only 0/2"):
            trio_assistant.optimal_duo_for_champion("Aatrox", ["Nobody1", "Nobody2", "Nobody3"])

        out = capsys.readouterr().out
        assert "[ERREUR] Only 0 companions have sufficient data." in out


class TestFindOptimalCounterpickDuo:
    """Characterization of ``_find_optimal_counterpick_duo()``."""

    def test_nominal_returns_best_duo_and_score(self, trio_assistant):
        """Best duo alongside blind pick Teemo is (Darius, Garen) at 16.5.

        Score = for each of the 6 known enemies, the best delta2 available in
        the trio {Teemo, Darius, Garen} (see DELTAS).
        """
        # Act
        duo, score = trio_assistant._find_optimal_counterpick_duo(
            ["Aatrox", "Darius", "Garen"], "Teemo"
        )

        # Assert
        assert duo == ("Darius", "Garen")
        assert score == pytest.approx(16.5)

    def test_remaining_pool_smaller_than_two_raises(self, trio_assistant):
        """Fewer than 2 candidates cannot form a duo."""
        with pytest.raises(ValueError, match="Need at least 2 champions in pool, got 1"):
            trio_assistant._find_optimal_counterpick_duo(["Aatrox"], "Teemo")

    def test_all_duos_filtered_by_coverage_raises(self, trio_assistant):
        """A duo covering < 10% of the champion roster is discarded.

        Simulating a 100-champion roster while the fixture only knows 6 makes
        every duo fall to 6% coverage, so none survives the filter.
        """
        # Arrange: pretend the DB knows 100 champions
        fake_roster = {i: f"Fake{i}" for i in range(100)}

        with patch.object(trio_assistant.db, "get_all_champion_names", return_value=fake_roster):
            # Act / Assert
            with pytest.raises(ValueError, match="No valid duo combinations could be evaluated"):
                trio_assistant._find_optimal_counterpick_duo(["Aatrox", "Darius", "Garen"], "Teemo")

    def test_show_ranking_prints_top_duos(self, trio_assistant, capsys):
        """``show_ranking=True`` adds the TOP DUO RANKINGS block."""
        # Act
        trio_assistant._find_optimal_counterpick_duo(
            ["Aatrox", "Darius", "Garen"], "Teemo", show_ranking=True
        )
        out = capsys.readouterr().out

        # Assert
        assert "TOP DUO RANKINGS:" in out
        assert "1. Darius + Garen" in out
        assert "Evaluated 3 valid combinations" in out

    def test_without_show_ranking_omits_top_duo_rankings(self, trio_assistant, capsys):
        """Default (``show_ranking=False``) prints no ranking block."""
        # Act
        trio_assistant._find_optimal_counterpick_duo(["Aatrox", "Darius", "Garen"], "Teemo")
        out = capsys.readouterr().out

        # Assert
        assert "TOP DUO RANKINGS:" not in out
        assert "[OK] Evaluation complete: 3/3 tested, 3 viable" in out


class TestAnalyzeTrioTactics:
    """Characterization of the console output of ``_analyze_trio_tactics()``."""

    TRIO = ("Teemo", "Darius", "Garen")

    def test_prints_header_and_roles(self, trio_assistant, capsys):
        """Header + one section per champion, with its BLIND/COUNTERPICK role."""
        # Act
        trio_assistant._analyze_trio_tactics(self.TRIO)
        out = capsys.readouterr().out

        # Assert
        assert "TACTICAL ANALYSIS:" in out
        assert "Your optimal trio: Teemo (Blind) + Darius + Garen (Counterpicks)" in out
        assert "Teemo (BLIND PICK):" in out
        assert "Darius (COUNTERPICK #1):" in out
        assert "Garen (COUNTERPICK #2):" in out

    def test_strong_against_lists_top_five_matchups_by_delta2(self, trio_assistant, capsys):
        """STRONG AGAINST shows the top 5 matchups sorted by delta2 desc.

        Note (frozen behavior): the list is simply ``valid_matchups[:5]`` with
        no positivity filter, so negative deltas appear in it as soon as the
        champion has fewer than 5 favourable matchups.
        """
        # Act
        trio_assistant._analyze_trio_tactics(self.TRIO)
        out = capsys.readouterr().out

        # Assert
        assert "  STRONG AGAINST:" in out
        assert "    - Darius (+4.00 delta2)" in out
        assert "    - Aatrox (+3.50 delta2)" in out
        # Negative delta still listed under "STRONG AGAINST" (no filter).
        assert "    - Garen (-3.00 delta2)" in out

    def test_weak_against_section_is_never_printed_latent_bug(self, trio_assistant, capsys):
        """FROZEN BUG (src/assistant.py ~line 952) — DO NOT FIX HERE.

        ``worst_matchups = [m for m in valid_matchups[-10:] if m.winrate < 0]``
        iterates over ``valid_matchups``, which holds ``(enemy_name, delta2)``
        TUPLES, not ``Matchup`` objects. ``m.winrate`` therefore raises
        ``AttributeError``, swallowed by the enclosing ``except Exception``.

        Observable consequences, pinned here so the extraction refactor cannot
        change them silently:
        - the "WEAK AGAINST" section NEVER appears, for any champion;
        - "NEUTRAL MATCHUPS" (printed after it) never appears either;
        - an "Error analyzing <champion>" line is printed instead.

        This test documents the bug as-is. Fixing it is a separate decision
        and would legitimately require updating this test.
        """
        # Act
        trio_assistant._analyze_trio_tactics(self.TRIO)
        out = capsys.readouterr().out

        # Assert: the section is absent for every champion of the trio
        assert "WEAK AGAINST" not in out
        # Collateral of the same exception: the section that follows is lost too
        assert "NEUTRAL MATCHUPS" not in out
        # ... and the swallowed AttributeError surfaces as an error line
        assert "Error analyzing Teemo: 'tuple' object has no attribute 'winrate'" in out
        assert "Error analyzing Darius: 'tuple' object has no attribute 'winrate'" in out
        assert "Error analyzing Garen: 'tuple' object has no attribute 'winrate'" in out

    def test_champion_without_matchups_is_skipped_silently(self, trio_assistant, capsys):
        """A champion with no DB row produces no section and no error line."""
        # Act
        trio_assistant._analyze_trio_tactics(("Nobody", "Darius", "Garen"))
        out = capsys.readouterr().out

        # Assert
        assert "Nobody (BLIND PICK):" not in out
        assert "Error analyzing Nobody" not in out
        assert "Darius (COUNTERPICK #1):" in out

    def test_delegates_to_coverage_analysis(self, trio_assistant, capsys):
        """``_analyze_trio_tactics`` always ends with the coverage analysis."""
        # Act
        trio_assistant._analyze_trio_tactics(self.TRIO)
        out = capsys.readouterr().out

        # Assert
        assert "COVERAGE ANALYSIS:" in out


class TestAnalyzeTrioCoverage:
    """Characterization of the console output of ``_analyze_trio_coverage()``."""

    def test_full_coverage_output(self, trio_assistant, capsys):
        """The trio covers all 6 known champions of the fixture universe.

        Best delta2 per enemy (trio = Teemo/Darius/Garen):
        Aatrox +3.5, Darius +4.0, Garen +2.5, Teemo +3.0, Malphite +2.0,
        Sett +1.5 -> 5 "excellent" (>= 2.0) and 1 "good" ([1.0, 2.0)).
        """
        # Act
        trio_assistant._analyze_trio_coverage(["Teemo", "Darius", "Garen"])
        out = capsys.readouterr().out

        # Assert
        assert "COVERAGE ANALYSIS:" in out
        assert "  - Covered: 6/6 champions (100.0%)" in out
        assert "  EXCELLENT counters: 5 (83.3%)" in out
        assert "  GOOD counters: 1 (16.7%)" in out
        assert "  Excellent pool! Very few gaps." in out
        assert "  Pool favors aggressive counterpicking." in out

    def test_no_difficult_matchups_block_when_nothing_struggles(self, trio_assistant, capsys):
        """DIFFICULT MATCHUPS is only printed when some delta2 is negative."""
        # Act
        trio_assistant._analyze_trio_coverage(["Teemo", "Darius", "Garen"])
        out = capsys.readouterr().out

        # Assert
        assert "DIFFICULT MATCHUPS:" not in out
        assert "STRUGGLING against:" not in out

    def test_uncovered_champions_are_reported(self, trio_assistant, capsys):
        """Enemies with no matchup at all in the trio land in the UNCOVERED list."""
        # Arrange: 3 extra roster entries the trio has no data against
        fake_roster = {
            1: "Aatrox",
            2: "Darius",
            3: "Garen",
            4: "Teemo",
            5: "Ghost1",
            6: "Ghost2",
        }

        with patch.object(trio_assistant.db, "get_all_champion_names", return_value=fake_roster):
            # Act
            trio_assistant._analyze_trio_coverage(["Teemo", "Darius", "Garen"])
            out = capsys.readouterr().out

        # Assert
        assert "  - Covered: 4/6 champions (66.7%)" in out
        assert "[ALERTE] UNCOVERED CHAMPIONS (2):" in out
        assert "    - Ghost1" in out
        assert "    - Ghost2" in out
        # 66.7% coverage falls in the [50, 70) bracket
        assert "  Decent pool but consider expanding." in out

    def test_struggling_matchups_block(self, trio_assistant, capsys):
        """A trio whose best answers are negative prints STRUGGLING/DIFFICULT."""
        # Arrange: Sett/Malphite/Garen have negative best answers vs some enemies
        # Act
        trio_assistant._analyze_trio_coverage(["Sett", "Malphite"])
        out = capsys.readouterr().out

        # Assert
        assert "STRUGGLING against:" in out
        assert "DIFFICULT MATCHUPS:" in out
        assert "  Pool requires careful champion selection." in out
