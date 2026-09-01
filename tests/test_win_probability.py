"""Tests for src/analysis/scoring.py:estimate_win_probability (SPEC-05 B7)."""

import pytest

from src.analysis.scoring import estimate_win_probability


class TestEstimateWinProbability:
    def test_balanced_draft_is_fifty_percent(self):
        """Every champion at a neutral 50% winrate -> perfectly even draft."""
        result = estimate_win_probability([50.0, 50.0, 50.0, 50.0, 50.0])
        assert result == pytest.approx(0.5, abs=1e-9)

    def test_empty_list_is_fifty_percent(self):
        assert estimate_win_probability([]) == pytest.approx(0.5)

    def test_advantage_gives_more_than_half(self):
        result = estimate_win_probability([53.0, 50.0, 50.0, 50.0, 50.0])
        assert result > 0.5

    def test_disadvantage_gives_less_than_half(self):
        result = estimate_win_probability([47.0, 50.0, 50.0, 50.0, 50.0])
        assert result < 0.5

    def test_symmetry(self):
        """Mirroring every winrate around 50 (100 - wr) must invert the probability
        (SPEC-05 §3.1: the model has no arbitrary asymmetry baked in)."""
        winrates = [53.0, 48.0, 61.0, 44.0, 50.0]
        mirrored = [100.0 - wr for wr in winrates]

        p = estimate_win_probability(winrates)
        p_mirrored = estimate_win_probability(mirrored)

        assert p_mirrored == pytest.approx(1.0 - p, abs=1e-9)

    def test_saturation_two_advantages_sum_to_less_than_double(self):
        """SPEC-05 §5 acceptance criterion: two +3-point advantages stacked
        together must add up to LESS than twice a single +3-point advantage,
        because the log-odds sum saturates through sigmoid instead of
        producing a linear probability delta."""
        single = estimate_win_probability([53.0])
        single_delta = single - 0.5

        combined = estimate_win_probability([53.0, 53.0])
        combined_delta = combined - 0.5

        assert combined_delta > single_delta  # still more probability than one alone
        assert combined_delta < 2 * single_delta  # but saturating, not linear

    def test_never_exactly_zero_or_one_even_on_extreme_draft(self):
        """5 extreme counter-picks stacked on both directions must stay in ]0, 1[
        (SPEC-05 §5: 'estimate_win_probability renvoie toujours une valeur
        dans ]0 ; 1[ sans clamp')."""
        extreme_advantage = estimate_win_probability([100.0, 100.0, 100.0, 100.0, 100.0])
        extreme_disadvantage = estimate_win_probability([0.0, 0.0, 0.0, 0.0, 0.0])

        assert 0.0 < extreme_advantage < 1.0
        assert 0.0 < extreme_disadvantage < 1.0
        assert extreme_advantage > 0.99
        assert extreme_disadvantage < 0.01
