"""Tests for the configurable matchup/synergy weight blend.

Feature: DraftMonitor._final_score(matchup_score, synergy_score) blends the two
scores using self.synergy_weight (0.0=matchup only, 1.0=synergy only, 0.5=legacy
balanced behavior). The weight is collected via an interactive prompt in
src/ui/draft_coach_ui.py before monitor.start_monitoring() is called.
"""

import pytest
from unittest.mock import Mock, patch

from src.draft_monitor import DraftMonitor
from src.config_constants import draft_config
from src.ui.draft_coach_ui import _prompt_synergy_weight


@pytest.fixture
def mock_lcu_client():
    mock_lcu = Mock()
    mock_lcu.connect.return_value = True
    return mock_lcu


@pytest.fixture
def mock_assistant():
    mock_assistant = Mock()
    mock_assistant.db = Mock()
    return mock_assistant


def make_monitor(mock_lcu_client, mock_assistant, synergy_weight=None):
    with patch("src.draft_monitor.LCUClient", return_value=mock_lcu_client):
        with patch("src.draft_monitor.Assistant", return_value=mock_assistant):
            return DraftMonitor(verbose=False, synergy_weight=synergy_weight)


class TestFinalScoreBlend:
    """DraftMonitor._final_score at the three pinned weights + default wiring."""

    def test_default_weight_is_config_default(self, mock_lcu_client, mock_assistant):
        monitor = make_monitor(mock_lcu_client, mock_assistant)
        assert monitor.synergy_weight == draft_config.DEFAULT_SYNERGY_WEIGHT

    def test_synergy_weight_half_matches_legacy_sum(self, mock_lcu_client, mock_assistant):
        """synergy_weight=0.5 must exactly reproduce matchup_score + synergy_score."""
        monitor = make_monitor(mock_lcu_client, mock_assistant, synergy_weight=0.5)
        matchup_score, synergy_score = 12.3, -4.5
        assert monitor._final_score(matchup_score, synergy_score) == pytest.approx(
            matchup_score + synergy_score
        )

    def test_synergy_weight_zero_ignores_synergy(self, mock_lcu_client, mock_assistant):
        """synergy_weight=0.0 -> final_score == matchup_score, exactly (AC requirement).

        DraftMonitor._final_score clamps each coefficient to at most 1 (see its
        docstring): matchup coeff = min(1, 2*(1-w)), synergy coeff = min(1, 2*w).
        At w=0 that's matchup coeff=1, synergy coeff=0, so the result is
        matchup_score verbatim -- NOT matchup_score * 2. (A naive, unclamped
        matchup_score*(1-w)*2 + synergy_score*w*2 would double-count matchup_score
        here, which is why the implementation clamps instead.)
        """
        monitor = make_monitor(mock_lcu_client, mock_assistant, synergy_weight=0.0)
        matchup_score, synergy_score = 20.0, 999.0
        assert monitor._final_score(matchup_score, synergy_score) == pytest.approx(matchup_score)
        # Synergy has zero influence at this weight, whatever its value.
        assert monitor._final_score(matchup_score, 0.0) == monitor._final_score(
            matchup_score, synergy_score
        )

    def test_synergy_weight_one_ignores_matchup(self, mock_lcu_client, mock_assistant):
        """synergy_weight=1.0 -> final_score == synergy_score, exactly (AC requirement).

        Mirrors the zero-weight case: matchup coeff=0, synergy coeff=1, so the
        result is synergy_score verbatim -- not synergy_score * 2.
        """
        monitor = make_monitor(mock_lcu_client, mock_assistant, synergy_weight=1.0)
        matchup_score, synergy_score = 999.0, 7.5
        assert monitor._final_score(matchup_score, synergy_score) == pytest.approx(synergy_score)
        # Matchup has zero influence at this weight, whatever its value.
        assert monitor._final_score(0.0, synergy_score) == monitor._final_score(
            matchup_score, synergy_score
        )

    def test_intermediate_weight_quarter_blends_proportionally(
        self, mock_lcu_client, mock_assistant
    ):
        monitor = make_monitor(mock_lcu_client, mock_assistant, synergy_weight=0.25)
        matchup_score, synergy_score = 10.0, 10.0
        # matchup coeff = min(1, 2*0.75) = 1 ; synergy coeff = min(1, 2*0.25) = 0.5
        # (10 * 1) + (10 * 0.5) = 10 + 5 = 15
        assert monitor._final_score(matchup_score, synergy_score) == pytest.approx(15.0)

    def test_intermediate_weight_three_quarters_blends_proportionally(
        self, mock_lcu_client, mock_assistant
    ):
        monitor = make_monitor(mock_lcu_client, mock_assistant, synergy_weight=0.75)
        matchup_score, synergy_score = 10.0, 10.0
        # matchup coeff = min(1, 2*0.25) = 0.5 ; synergy coeff = min(1, 2*0.75) = 1
        # (10 * 0.5) + (10 * 1) = 5 + 10 = 15
        assert monitor._final_score(matchup_score, synergy_score) == pytest.approx(15.0)

    def test_intermediate_weights_with_asymmetric_scores(self, mock_lcu_client, mock_assistant):
        """0.25 and 0.75 must weight matchup/synergy asymmetrically when scores differ."""
        matchup_score, synergy_score = 8.0, 2.0
        monitor_25 = make_monitor(mock_lcu_client, mock_assistant, synergy_weight=0.25)
        # matchup coeff = 1, synergy coeff = 0.5 -> (8 * 1) + (2 * 0.5) = 8 + 1 = 9
        assert monitor_25._final_score(matchup_score, synergy_score) == pytest.approx(9.0)

        monitor_75 = make_monitor(mock_lcu_client, mock_assistant, synergy_weight=0.75)
        # matchup coeff = 0.5, synergy coeff = 1 -> (8 * 0.5) + (2 * 1) = 4 + 2 = 6
        assert monitor_75._final_score(matchup_score, synergy_score) == pytest.approx(6.0)


class TestSynergyWeightPrompt:
    """_prompt_synergy_weight() input validation."""

    def test_empty_input_returns_default(self):
        with patch("builtins.input", return_value=""):
            assert _prompt_synergy_weight() == draft_config.DEFAULT_SYNERGY_WEIGHT

    def test_valid_input_is_parsed(self):
        with patch("builtins.input", return_value="0.75"):
            assert _prompt_synergy_weight() == pytest.approx(0.75)

    def test_invalid_then_valid_input_reprompts(self, capsys):
        with patch("builtins.input", side_effect=["not-a-float", "0.3"]):
            assert _prompt_synergy_weight() == pytest.approx(0.3)
        assert "invalide" in capsys.readouterr().out.lower()

    def test_out_of_range_then_valid_input_reprompts(self, capsys):
        with patch("builtins.input", side_effect=["1.5", "-0.2", "0.6"]):
            assert _prompt_synergy_weight() == pytest.approx(0.6)
        out = capsys.readouterr().out.lower()
        assert out.count("doit etre") == 2 or out.count("entre 0.0 et 1.0") >= 2

    def test_boundary_values_accepted(self):
        with patch("builtins.input", return_value="0.0"):
            assert _prompt_synergy_weight() == pytest.approx(0.0)
        with patch("builtins.input", return_value="1.0"):
            assert _prompt_synergy_weight() == pytest.approx(1.0)
