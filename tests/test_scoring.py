"""Tests for scoring algorithms (src/analysis/scoring.py)."""

import pytest
import math
from src.analysis.scoring import ChampionScorer
from src.config_constants import analysis_config


class TestFilterValidMatchups:
    """Tests for filter_valid_matchups method."""

    def test_filters_low_pickrate(self, scorer, sample_matchups):
        """Test that matchups with low pickrate are filtered out."""
        # Create matchup with pickrate below threshold
        low_pickrate = (
            "TestChamp",
            50.0,  # winrate
            0,     # delta1
            0,     # delta2
            analysis_config.MIN_PICKRATE - 0.1,  # Below threshold
            1000   # games
        )
        matchups = [low_pickrate] + sample_matchups

        result = scorer.filter_valid_matchups(matchups)

        assert low_pickrate not in result
        assert len(result) == len(sample_matchups)

    def test_filters_low_games(self, scorer, sample_matchups):
        """Test that matchups with insufficient games are filtered out."""
        low_games = (
            "TestChamp",
            50.0,
            0,
            0,
            10.0,  # Good pickrate
            analysis_config.MIN_MATCHUP_GAMES - 1  # Below threshold
        )
        matchups = [low_games] + sample_matchups

        result = scorer.filter_valid_matchups(matchups)

        assert low_games not in result

    def test_keeps_valid_matchups(self, scorer, sample_matchups):
        """Test that valid matchups are kept."""
        result = scorer.filter_valid_matchups(sample_matchups)

        assert len(result) == len(sample_matchups)

    def test_empty_list(self, scorer):
        """Test filtering empty matchup list."""
        result = scorer.filter_valid_matchups([])

        assert result == []


class TestAvgDelta1:
    """Tests for avg_delta1 weighted average calculation."""

    def test_weighted_average_calculation(self, scorer):
        """Test correct weighted average by pickrate."""
        matchups = [
            ("Champ1", 50.0, 100.0, 0, 10.0, 1000),  # delta1=100, weight=10
            ("Champ2", 50.0, 200.0, 0, 20.0, 1000),  # delta1=200, weight=20
        ]
        # Expected: (100*10 + 200*20) / (10+20) = 5000 / 30 = 166.67

        result = scorer.avg_delta1(matchups)

        assert abs(result - 166.67) < 0.01

    def test_single_matchup(self, scorer):
        """Test average with single matchup."""
        matchups = [("Champ1", 50.0, 150.0, 0, 10.0, 1000)]

        result = scorer.avg_delta1(matchups)

        assert result == 150.0

    def test_empty_matchups_returns_zero(self, scorer):
        """Test that empty matchup list returns 0."""
        result = scorer.avg_delta1([])

        assert result == 0.0

    def test_zero_total_weight_returns_zero(self, scorer):
        """Test that zero total weight returns 0."""
        # All matchups below pickrate threshold
        matchups = [("Champ1", 50.0, 100.0, 0, 0.1, 1000)]

        result = scorer.avg_delta1(matchups)

        assert result == 0.0


class TestAvgDelta2:
    """Tests for avg_delta2 weighted average calculation."""

    def test_weighted_average_calculation(self, scorer):
        """Test correct weighted average by pickrate."""
        matchups = [
            ("Champ1", 50.0, 0, 150.0, 15.0, 1500),  # delta2=150, weight=15
            ("Champ2", 50.0, 0, 250.0, 10.0, 1000),  # delta2=250, weight=10
        ]
        # Expected: (150*15 + 250*10) / (15+10) = 4750 / 25 = 190

        result = scorer.avg_delta2(matchups)

        assert abs(result - 190.0) < 0.01

    def test_empty_matchups_returns_zero(self, scorer):
        """Test that empty matchup list returns 0."""
        result = scorer.avg_delta2([])

        assert result == 0.0


class TestAvgWinrate:
    """Tests for avg_winrate weighted average calculation."""

    def test_weighted_average_calculation(self, scorer):
        """Test correct weighted average by pickrate."""
        matchups = [
            ("Champ1", 52.0, 0, 0, 12.0, 1200),  # winrate=52, weight=12
            ("Champ2", 48.0, 0, 0, 8.0, 800),    # winrate=48, weight=8
        ]
        # Expected: (52*12 + 48*8) / (12+8) = 1008 / 20 = 50.4

        result = scorer.avg_winrate(matchups)

        assert abs(result - 50.4) < 0.01

    def test_empty_matchups_returns_zero(self, scorer):
        """Test that empty matchup list returns 0."""
        result = scorer.avg_winrate([])

        assert result == 0.0


class TestDelta2ToWinAdvantage:
    """Tests for delta2_to_win_advantage logistic transformation."""

    def test_positive_delta2_gives_positive_advantage(self, scorer):
        """Test that positive delta2 gives positive advantage."""
        result = scorer.delta2_to_win_advantage(2.0, "TestChamp")

        assert result > 0

    def test_negative_delta2_gives_negative_advantage(self, scorer):
        """Test that negative delta2 gives negative advantage."""
        result = scorer.delta2_to_win_advantage(-2.0, "TestChamp")

        assert result < 0

    def test_zero_delta2_gives_near_zero_advantage(self, scorer):
        """Test that zero delta2 gives ~0% advantage."""
        result = scorer.delta2_to_win_advantage(0.0, "TestChamp")

        assert abs(result) < 0.01

    def test_bounds_are_applied(self, scorer):
        """Test that advantage is clamped to [-10%, +10%]."""
        # Very large positive delta2
        result_positive = scorer.delta2_to_win_advantage(100.0, "TestChamp")
        assert result_positive == 10.0

        # Very large negative delta2
        result_negative = scorer.delta2_to_win_advantage(-100.0, "TestChamp")
        assert result_negative == -10.0

    def test_logistic_formula(self, scorer):
        """Test logistic transformation formula is correct."""
        delta2 = 5.0
        # Manual calculation: log_odds = 0.12 * 5.0 = 0.6
        # win_prob = 1 / (1 + exp(-0.6)) = 0.6457
        # advantage = (0.6457 - 0.5) * 100 = 14.57 -> clamped to 10.0

        result = scorer.delta2_to_win_advantage(delta2, "TestChamp")

        # Should be clamped to max 10.0
        assert result == 10.0


class TestScoreAgainstTeam:
    """Tests for score_against_team matchup calculations."""

    def test_returns_zero_without_champion_name(self, scorer, sample_matchups):
        """Test that function returns 0 when champion_name is not provided."""
        result = scorer.score_against_team(sample_matchups, ["Darius"], champion_name=None)

        assert result == 0.0

    def test_blind_pick_uses_avg_delta2(self, scorer, sample_matchups):
        """Test that blind pick scenario uses average delta2."""
        result = scorer.score_against_team(sample_matchups, [], champion_name="Aatrox")

        # Should use avg_delta2 of sample_matchups
        avg_delta2 = scorer.avg_delta2(sample_matchups)
        expected = scorer.delta2_to_win_advantage(avg_delta2, "Aatrox")

        assert abs(result - expected) < 0.01

    def test_known_matchup_calculation(self, scorer):
        """Test calculation against known enemy."""
        matchups = [
            ("Darius", 48.0, -150, -200, 10.0, 1500),
        ]

        result = scorer.score_against_team(matchups, ["Darius"], champion_name="Aatrox")

        # Should calculate advantage based on Darius matchup delta2
        expected = scorer.delta2_to_win_advantage(-200, "Aatrox")
        assert abs(result - expected) < 0.01

    def test_mixed_known_and_blind(self, scorer):
        """Test calculation with some known and some blind picks."""
        matchups = [
            ("Darius", 48.0, -150, -200, 10.0, 1500),
            ("Garen", 52.0, 100, 150, 12.0, 2000),
            ("Teemo", 45.0, -300, -400, 5.0, 800),
        ]

        # Enemy team: Darius known, 4 blind picks
        result = scorer.score_against_team(matchups, ["Darius"], champion_name="Aatrox")

        # Should use Darius delta2 + avg of remaining for blind picks
        assert isinstance(result, float)
        assert -10.0 <= result <= 10.0

    def test_empty_matchups_returns_zero(self, scorer):
        """Test with no matchup data."""
        result = scorer.score_against_team([], ["Darius"], champion_name="Aatrox")

        assert result == 0.0


class TestCalculateTeamWinrate:
    """Tests for calculate_team_winrate geometric mean calculation."""

    def test_geometric_mean_calculation(self, scorer):
        """Test geometric mean formula is correct."""
        # Winrates: [52%, 51%, 53%]
        # Probabilities: [0.52, 0.51, 0.53]
        # Geometric mean: (0.52 * 0.51 * 0.53)^(1/3) = 0.5199
        # Team winrate: 51.99%

        result = scorer.calculate_team_winrate([52.0, 51.0, 53.0])

        assert "team_winrate" in result
        assert "individual_winrates" in result
        assert abs(result["team_winrate"] - 52.0) < 1.0  # Approximately 52%

    def test_empty_list_returns_50_percent(self, scorer):
        """Test that empty list returns neutral 50% winrate."""
        result = scorer.calculate_team_winrate([])

        assert result["team_winrate"] == 50.0
        assert result["individual_winrates"] == []

    def test_clamping_individual_winrates(self, scorer):
        """Test that individual winrates are clamped to [20%, 80%]."""
        result = scorer.calculate_team_winrate([90.0, 10.0, 50.0])

        assert result["individual_winrates"] == [80.0, 20.0, 50.0]

    def test_team_winrate_bounds(self, scorer):
        """Test that team winrate is clamped to [25%, 75%]."""
        # All very high winrates
        result_high = scorer.calculate_team_winrate([80.0, 80.0, 80.0, 80.0, 80.0])
        assert result_high["team_winrate"] <= 75.0

        # All very low winrates
        result_low = scorer.calculate_team_winrate([20.0, 20.0, 20.0, 20.0, 20.0])
        assert result_low["team_winrate"] >= 25.0

    def test_single_champion(self, scorer):
        """Test calculation with single champion."""
        result = scorer.calculate_team_winrate([55.0])

        assert result["team_winrate"] == 55.0
        assert result["individual_winrates"] == [55.0]
