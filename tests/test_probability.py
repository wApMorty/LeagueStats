"""Tests for src/analysis/probability.py (SPEC-05 B7 primitives)."""

import math

import pytest

from src.analysis.probability import logit, sigmoid, winrate_points_to_logit
from src.config_constants import analysis_config


class TestLogitSigmoidInverses:
    """logit and sigmoid must be exact inverses away from the clamped boundaries."""

    @pytest.mark.parametrize("x", [-10.0, -5.0, -1.0, -0.01, 0.0, 0.01, 1.0, 5.0, 10.0])
    def test_logit_of_sigmoid_is_identity(self, x):
        assert logit(sigmoid(x)) == pytest.approx(x, abs=1e-9)

    def test_sigmoid_of_logit_is_identity_for_mid_range_probabilities(self):
        for p in [0.001, 0.1, 0.3, 0.5, 0.7, 0.9, 0.999]:
            assert sigmoid(logit(p)) == pytest.approx(p, abs=1e-9)


class TestSigmoidBounds:
    def test_sigmoid_never_exactly_zero_or_one(self):
        # Larger magnitudes (e.g. +-50, let alone +-1000) would be
        # mathematically correct too, but 1.0 + exp(-|x|) stops being
        # distinguishable from 1.0 in IEEE 754 double precision once
        # exp(-|x|) drops below ~1.1e-16 (float64's rounding unit at 1.0) --
        # around |x| ~ 36.7 -- so sigmoid legitimately (not a bug) saturates
        # to exactly 0.0/1.0 there. +-30 stays comfortably under that
        # threshold (exp(-30) ~ 9.4e-14) while still being far more extreme
        # than any realistic log-odds sum in this app (SPEC-05: a delta2 at
        # the DB extreme, ~50, contributes only ~2.0 in log-odds).
        assert sigmoid(-30.0) > 0.0
        assert sigmoid(30.0) < 1.0

    def test_sigmoid_of_zero_is_half(self):
        assert sigmoid(0.0) == pytest.approx(0.5)

    def test_sigmoid_is_monotonic(self):
        xs = [-5.0, -1.0, 0.0, 1.0, 5.0]
        values = [sigmoid(x) for x in xs]
        assert values == sorted(values)


class TestLogitBounds:
    def test_logit_of_zero_does_not_raise(self):
        # Clamped to 1e-6 internally, so this must not raise ValueError/ZeroDivisionError.
        result = logit(0.0)
        assert math.isfinite(result)
        assert result < 0

    def test_logit_of_one_does_not_raise(self):
        result = logit(1.0)
        assert math.isfinite(result)
        assert result > 0

    def test_logit_of_half_is_zero(self):
        assert logit(0.5) == pytest.approx(0.0, abs=1e-9)

    def test_logit_is_monotonic(self):
        ps = [0.01, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99]
        values = [logit(p) for p in ps]
        assert values == sorted(values)

    def test_logit_clamps_out_of_range_values(self):
        # Values outside [0, 1] are not valid probabilities, but the clamp
        # must still keep the function from raising.
        assert math.isfinite(logit(-5.0))
        assert math.isfinite(logit(5.0))


class TestWinratePointsToLogit:
    def test_zero_points_gives_zero_logit(self):
        assert winrate_points_to_logit(0.0) == pytest.approx(0.0)

    def test_reads_coefficient_from_config_not_hardcoded(self):
        """Regression guard: the conversion must read
        analysis_config.LOGIT_PER_WINRATE_POINT rather than a hardcoded 0.04,
        so a config change actually takes effect."""
        original = analysis_config.LOGIT_PER_WINRATE_POINT
        try:
            analysis_config.LOGIT_PER_WINRATE_POINT = 0.1
            assert winrate_points_to_logit(10.0) == pytest.approx(1.0)
        finally:
            analysis_config.LOGIT_PER_WINRATE_POINT = original

    def test_matches_documented_default_value(self):
        # Default LOGIT_PER_WINRATE_POINT = 0.04 (SPEC-05 §3.2).
        assert winrate_points_to_logit(1.0) == pytest.approx(
            analysis_config.LOGIT_PER_WINRATE_POINT
        )
        assert winrate_points_to_logit(10.0) == pytest.approx(
            10.0 * analysis_config.LOGIT_PER_WINRATE_POINT
        )

    def test_linearity(self):
        a = winrate_points_to_logit(3.0)
        b = winrate_points_to_logit(6.0)
        assert b == pytest.approx(2 * a)

    def test_negative_points_give_negative_logit(self):
        assert winrate_points_to_logit(-5.0) < 0.0
