"""Characterization tests for the individual trio metric calculators of
``Assistant`` (SPEC TODO E10 safety net).

Scope:
- ``_calculate_coverage_score``
- ``_calculate_balance_score`` / ``_calculate_balance_score_reverse``
- ``_calculate_consistency_score`` / ``_calculate_consistency_score_reverse``
- ``_calculate_enemy_coverage``
- ``_calculate_meta_score`` (the only one that needs a real DB)

All expected values are hand-computed from the formulas as they exist TODAY.
These tests freeze the current behavior — including the quirks noted inline —
so the upcoming extraction refactor cannot change a number silently.
"""

from unittest.mock import Mock

import pytest

from src.assistant import Assistant
from src.config_constants import analysis_config
from src.models import Matchup


def matchup(enemy, delta2, pickrate=5.0, games=1000, winrate=50.0):
    """Build a Matchup that passes the MIN_PICKRATE / MIN_MATCHUP_GAMES filters."""
    return Matchup(enemy, winrate, delta2 * 10, delta2, pickrate, games)


@pytest.fixture
def assistant():
    """Assistant with a fully mocked DB — these metrics are pure computations."""
    return Assistant(db=Mock(), verbose=False)


class TestCalculateCoverageScore:
    """``_calculate_coverage_score(enemy_coverage, all_enemies)``."""

    def test_empty_enemy_set_returns_zero(self, assistant):
        assert assistant._calculate_coverage_score({}, set()) == 0.0

    def test_negative_deltas_are_clamped_to_zero(self, assistant):
        """Only positive delta2 contributes: max(0, delta2).

        total = 3.0 + 0 + 2.0 = 5.0 ; max_possible = 3 enemies * 10 = 30
        -> 5/30 * 100 = 16.666...
        """
        coverage = {"A": (3.0, "X"), "B": (-1.0, "X"), "C": (2.0, "Y")}

        score = assistant._calculate_coverage_score(coverage, {"A", "B", "C"})

        assert score == pytest.approx(16.6666, abs=1e-3)

    def test_score_is_capped_at_100(self, assistant):
        """Delta2 above the theoretical max of 10 saturates the score."""
        coverage = {"A": (50.0, "X")}

        assert assistant._calculate_coverage_score(coverage, {"A"}) == 100.0

    def test_all_enemies_bigger_than_coverage_dilutes_score(self, assistant):
        """``all_enemies`` is the denominator, even for uncovered enemies."""
        coverage = {"A": (10.0, "X")}

        score = assistant._calculate_coverage_score(coverage, {"A", "B", "C", "D"})

        assert score == pytest.approx(25.0)  # 10 / (4 * 10) * 100


class TestCalculateBalanceScoreReverse:
    """``_calculate_balance_score_reverse(trio_list, enemy_coverage, cache)``."""

    TRIO = ["Aatrox", "Darius", "Garen"]

    def test_no_weakness_returns_100(self, assistant):
        """No champion below -2.0 delta2 -> no weakness at all -> 100.0."""
        coverage = {"Teemo": (1.0, "Aatrox")}
        cache = {
            ("aatrox", "teemo"): 1.0,
            ("darius", "teemo"): 0.0,
            ("garen", "teemo"): -1.9,
        }

        assert assistant._calculate_balance_score_reverse(self.TRIO, coverage, cache) == 100.0

    def test_fully_shared_weakness_returns_zero(self, assistant):
        """All 3 champions weak vs the same (and only) enemy -> balance 0."""
        coverage = {"Teemo": (-2.5, "Aatrox")}
        cache = {
            ("aatrox", "teemo"): -2.5,
            ("darius", "teemo"): -3.0,
            ("garen", "teemo"): -4.0,
        }

        assert assistant._calculate_balance_score_reverse(self.TRIO, coverage, cache) == 0.0

    def test_partially_shared_weakness(self, assistant):
        """union = {Teemo, Vayne}, intersection = {Teemo} -> 1 - 1/2 = 50.0."""
        coverage = {"Teemo": (-2.5, "Aatrox"), "Vayne": (-1.0, "Darius")}
        cache = {
            ("aatrox", "teemo"): -2.5,
            ("darius", "teemo"): -3.0,
            ("garen", "teemo"): -4.0,
            ("aatrox", "vayne"): -3.0,
            ("darius", "vayne"): -1.0,
            ("garen", "vayne"): 0.0,
        }

        assert assistant._calculate_balance_score_reverse(self.TRIO, coverage, cache) == 50.0

    def test_threshold_is_strictly_below_minus_two(self, assistant):
        """Exactly -2.0 is NOT a weakness (``delta2 < -2.0``)."""
        coverage = {"Teemo": (-2.0, "Aatrox")}
        cache = {
            ("aatrox", "teemo"): -2.0,
            ("darius", "teemo"): -2.0,
            ("garen", "teemo"): -2.0,
        }

        assert assistant._calculate_balance_score_reverse(self.TRIO, coverage, cache) == 100.0

    def test_single_champion_trio_returns_neutral_50(self, assistant):
        """Fewer than 2 weakness sets short-circuits to the neutral 50.0."""
        assert assistant._calculate_balance_score_reverse(["Aatrox"], {}, {}) == 50.0

    def test_missing_cache_entries_are_ignored(self, assistant):
        """A cache miss (None) never counts as a weakness."""
        coverage = {"Teemo": (0.0, "Aatrox")}

        assert assistant._calculate_balance_score_reverse(self.TRIO, coverage, {}) == 100.0


class TestCalculateConsistencyScoreReverse:
    """``_calculate_consistency_score_reverse(trio_list, enemy_coverage)``."""

    TRIO = ["Aatrox", "Darius", "Garen"]

    def test_empty_coverage_returns_zero(self, assistant):
        assert assistant._calculate_consistency_score_reverse(self.TRIO, {}) == 0.0

    def test_identical_deltas_give_maximum_consistency(self, assistant):
        """variance 0 -> consistency 100 ; mean 1.0 -> perf (1+5)*10 = 60.

        total = 100 * 0.6 + 60 * 0.4 = 84.0
        """
        coverage = {"A": (1.0, "X"), "B": (1.0, "Y"), "C": (1.0, "Z")}

        score = assistant._calculate_consistency_score_reverse(self.TRIO, coverage)

        assert score == pytest.approx(84.0)

    def test_single_entry_uses_neutral_consistency_of_50(self, assistant):
        """One score -> consistency forced to 50 ; mean 2.0 -> perf 70.

        total = 50 * 0.6 + 70 * 0.4 = 58.0
        """
        score = assistant._calculate_consistency_score_reverse(self.TRIO, {"A": (2.0, "X")})

        assert score == pytest.approx(58.0)

    def test_high_variance_floors_consistency_at_zero(self, assistant):
        """variance * 5 > 100 -> ``max(0, ...)`` clamps consistency to 0.

        scores [-10, 10] -> variance 200 -> consistency 0 ; mean 0 -> perf 50.
        total = 0 * 0.6 + 50 * 0.4 = 20.0
        """
        coverage = {"A": (-10.0, "X"), "B": (10.0, "Y")}

        score = assistant._calculate_consistency_score_reverse(self.TRIO, coverage)

        assert score == pytest.approx(20.0)

    def test_very_negative_mean_floors_performance_at_zero(self, assistant):
        """``max(0, mean + 5)`` clamps the performance term at mean <= -5.

        scores [-8, -8] -> variance 0 -> consistency 100 ; perf 0.
        total = 100 * 0.6 = 60.0
        """
        coverage = {"A": (-8.0, "X"), "B": (-8.0, "Y")}

        assert assistant._calculate_consistency_score_reverse(self.TRIO, coverage) == pytest.approx(
            60.0
        )


class TestCalculateBalanceScore:
    """``_calculate_balance_score(trio, all_matchups)`` (classic, non-reverse)."""

    TRIO = ("Aatrox", "Darius", "Garen")

    def test_no_weakness_returns_100(self, assistant):
        all_matchups = [
            [matchup("Teemo", 1.0)],
            [matchup("Teemo", 0.0)],
            [matchup("Teemo", -1.0)],
        ]

        assert assistant._calculate_balance_score(self.TRIO, all_matchups) == 100.0

    def test_fully_shared_weakness_returns_zero(self, assistant):
        all_matchups = [
            [matchup("Teemo", -3.0)],
            [matchup("Teemo", -4.0)],
            [matchup("Teemo", -5.0)],
        ]

        assert assistant._calculate_balance_score(self.TRIO, all_matchups) == 0.0

    def test_partially_shared_weakness(self, assistant):
        """union = {Teemo, Vayne}, intersection = {Teemo} -> 50.0."""
        all_matchups = [
            [matchup("Teemo", -3.0), matchup("Vayne", -3.0)],
            [matchup("Teemo", -3.0), matchup("Vayne", 1.0)],
            [matchup("Teemo", -3.0), matchup("Vayne", 1.0)],
        ]

        assert assistant._calculate_balance_score(self.TRIO, all_matchups) == 50.0

    def test_matchups_below_thresholds_are_ignored(self, assistant):
        """Low pickrate / low games matchups never count as weaknesses."""
        all_matchups = [
            [matchup("Teemo", -5.0, pickrate=analysis_config.MIN_PICKRATE - 0.1)],
            [matchup("Teemo", -5.0, games=analysis_config.MIN_MATCHUP_GAMES - 1)],
            [matchup("Teemo", -5.0, pickrate=0.0, games=0)],
        ]

        assert assistant._calculate_balance_score(self.TRIO, all_matchups) == 100.0

    def test_single_matchup_list_returns_neutral_50(self, assistant):
        """Fewer than 2 lists short-circuits before the hardcoded [0][1][2]."""
        assert assistant._calculate_balance_score(self.TRIO, [[matchup("Teemo", -3.0)]]) == 50.0

    def test_exactly_two_matchup_lists_errors_out_to_50(self, assistant, capsys):
        """FROZEN QUIRK — DO NOT FIX HERE.

        The guard is ``len(champion_weaknesses) < 2`` but the body indexes
        ``[0] | [1] | [2]``. With exactly 2 lists this raises IndexError, which
        the ``except`` turns into a logged error and the neutral score 50.0.
        Pinned so the refactor keeps the same (surprising) contract.
        """
        all_matchups = [[matchup("Teemo", -3.0)], [matchup("Teemo", -3.0)]]

        score = assistant._calculate_balance_score(self.TRIO, all_matchups)

        assert score == 50.0
        out = capsys.readouterr().out
        assert "[ERROR] Balance score calculation failed for trio" in out


class TestCalculateConsistencyScore:
    """``_calculate_consistency_score(trio, all_matchups)`` (classic)."""

    TRIO = ("Aatrox", "Darius", "Garen")

    def test_no_valid_matchup_returns_zero(self, assistant):
        """Everything filtered out by pickrate/games -> 0.0."""
        all_matchups = [[matchup("Teemo", 1.0, pickrate=0.0, games=0)]]

        assert assistant._calculate_consistency_score(self.TRIO, all_matchups) == 0.0

    def test_identical_deltas_give_the_same_84_as_reverse_variant(self, assistant):
        """Same formula as the _reverse variant: 100 * 0.6 + 60 * 0.4 = 84.0."""
        all_matchups = [
            [matchup("Teemo", 1.0)],
            [matchup("Vayne", 1.0)],
            [matchup("Zed", 1.0)],
        ]

        assert assistant._calculate_consistency_score(self.TRIO, all_matchups) == pytest.approx(
            84.0
        )

    def test_single_score_uses_neutral_consistency_of_50(self, assistant):
        """One valid matchup -> consistency 50, mean 2.0 -> perf 70 -> 58.0."""
        all_matchups = [[matchup("Teemo", 2.0)]]

        assert assistant._calculate_consistency_score(self.TRIO, all_matchups) == pytest.approx(
            58.0
        )

    def test_high_variance_floors_consistency_at_zero(self, assistant):
        """scores [-10, 10] -> variance 200 -> consistency 0, perf 50 -> 20.0."""
        all_matchups = [[matchup("Teemo", -10.0)], [matchup("Vayne", 10.0)]]

        assert assistant._calculate_consistency_score(self.TRIO, all_matchups) == pytest.approx(
            20.0
        )


class TestCalculateEnemyCoverage:
    """``_calculate_enemy_coverage(matchups_list)``."""

    def test_keeps_the_best_delta2_per_enemy(self, assistant):
        matchups_list = [
            [matchup("Teemo", 1.0), matchup("Vayne", -2.0)],
            [matchup("Teemo", 3.0)],
        ]

        coverage = assistant._calculate_enemy_coverage(matchups_list)

        assert coverage["Teemo"][0] == 3.0
        assert coverage["Vayne"][0] == -2.0

    def test_champion_name_is_a_positional_placeholder(self, assistant):
        """FROZEN QUIRK: the real champion name is never passed in, so the
        method stores ``Champion<index+1>`` (see the inline "should be passed
        properly" comment in the source)."""
        matchups_list = [
            [matchup("Teemo", 1.0)],
            [matchup("Vayne", 2.0)],
            [matchup("Zed", 3.0)],
        ]

        coverage = assistant._calculate_enemy_coverage(matchups_list)

        assert coverage["Teemo"] == (1.0, "Champion1")
        assert coverage["Vayne"] == (2.0, "Champion2")
        assert coverage["Zed"] == (3.0, "Champion3")

    def test_matchups_below_thresholds_are_excluded(self, assistant):
        matchups_list = [
            [
                matchup("Teemo", 1.0, pickrate=analysis_config.MIN_PICKRATE - 0.1),
                matchup("Vayne", 1.0, games=analysis_config.MIN_MATCHUP_GAMES - 1),
                matchup("Zed", 1.0),
            ]
        ]

        coverage = assistant._calculate_enemy_coverage(matchups_list)

        assert set(coverage) == {"Zed"}

    def test_empty_input_returns_empty_dict(self, assistant):
        assert assistant._calculate_enemy_coverage([]) == {}


class TestCalculateMetaScore:
    """``_calculate_meta_score(enemy_coverage)`` — needs real DB pickrates."""

    @pytest.fixture
    def meta_assistant(self, db, insert_matchup):
        """Two enemies with different pickrates, to exercise the weighting."""
        # Aatrox: average pickrate 10.0
        insert_matchup("Aatrox", "Darius", 52.0, 20.0, 2.0, 10.0, 1000)
        insert_matchup("Aatrox", "Garen", 52.0, 20.0, 2.0, 10.0, 1000)
        # Teemo: average pickrate 1.0 (barely played -> low meta weight)
        insert_matchup("Teemo", "Darius", 52.0, 20.0, 2.0, 1.0, 1000)
        insert_matchup("Teemo", "Garen", 52.0, 20.0, 2.0, 1.0, 1000)
        return Assistant(db=db, verbose=False)

    def test_empty_coverage_returns_neutral_50(self, meta_assistant):
        assert meta_assistant._calculate_meta_score({}) == 50.0

    def test_unknown_enemy_has_no_pickrate_data_returns_neutral_50(self, meta_assistant):
        """No matchup row -> no weight at all -> the neutral fallback."""
        assert meta_assistant._calculate_meta_score({"Nobody": (3.0, "X")}) == 50.0

    def test_single_enemy_scales_delta2_to_0_100(self, meta_assistant):
        """weighted_avg = delta2 = 3.0 -> (3 + 5) * 10 = 80.0."""
        assert meta_assistant._calculate_meta_score({"Aatrox": (3.0, "X")}) == pytest.approx(80.0)

    def test_negative_delta2_is_clamped_to_zero_before_weighting(self, meta_assistant):
        """``max(0, delta2)`` -> weighted_avg 0 -> (0 + 5) * 10 = 50.0."""
        assert meta_assistant._calculate_meta_score({"Aatrox": (-4.0, "X")}) == pytest.approx(50.0)

    def test_high_pickrate_enemy_dominates_the_weighted_average(self, meta_assistant):
        """Aatrox (pickrate 10) weighs 10x more than Teemo (pickrate 1).

        weighted_avg = (4.0 * 10 + 0.0 * 1) / 11 = 3.6363...
        score = (3.6363 + 5) * 10 = 86.36...
        """
        coverage = {"Aatrox": (4.0, "X"), "Teemo": (0.0, "Y")}

        assert meta_assistant._calculate_meta_score(coverage) == pytest.approx(86.3636, abs=1e-3)

    def test_score_is_capped_at_100(self, meta_assistant):
        assert meta_assistant._calculate_meta_score({"Aatrox": (50.0, "X")}) == 100.0
