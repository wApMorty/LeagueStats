"""
Functional tests for Champion Analysis features.

Tests menu option 4 (Analysis & Tournament) functionalities.
"""

import pytest


class TestTierListAnalysis:
    """Test tier list analysis functionality via tierlist_delta2."""

    def test_tierlist_delta2_returns_sorted_list(self, assistant):
        """Test tierlist_delta2 returns champions sorted by score."""
        # Arrange
        champion_list = ['Aatrox', 'Ahri', 'Jinx']

        # Act
        result = assistant.tierlist_delta2(champion_list)

        # Assert
        assert isinstance(result, list), "Should return a list"
        assert len(result) > 0, "Should have at least one result"

        # Verify structure: list of (champion, score) tuples
        for entry in result:
            assert isinstance(entry, tuple), "Each entry should be a tuple"
            assert len(entry) == 2, "Each tuple should have 2 elements (champion, score)"
            champion, score = entry
            assert isinstance(champion, str), "Champion should be a string"
            assert isinstance(score, (int, float)), "Score should be numeric"

    def test_tierlist_delta2_sorted_descending(self, assistant):
        """Test that tierlist results are sorted by score (descending)."""
        # Arrange
        champion_list = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin']

        # Act
        result = assistant.tierlist_delta2(champion_list)

        # Assert
        if len(result) > 1:
            scores = [score for _, score in result]
            assert scores == sorted(scores, reverse=True), \
                "Results should be sorted descending by score"

    def test_tierlist_delta2_empty_list(self, assistant):
        """Test tierlist with empty champion list."""
        # Act
        result = assistant.tierlist_delta2([])

        # Assert
        assert result == [], "Empty list should return empty result"


class TestScoreAgainstTeam:
    """Test score_against_team functionality."""

    def test_score_against_single_enemy(self, assistant):
        """Test scoring a champion against a single enemy."""
        # Arrange
        champion = 'Aatrox'
        enemy_team = ['Darius']

        # Act
        score = assistant.score_against_team(champion, enemy_team)

        # Assert
        assert isinstance(score, (int, float)), "Score should be numeric"

    def test_score_against_multiple_enemies(self, assistant):
        """Test scoring against full enemy team."""
        # Arrange
        champion = 'Ahri'
        enemy_team = ['Zed', 'Aatrox', 'Lee Sin']

        # Act
        score = assistant.score_against_team(champion, enemy_team)

        # Assert
        assert isinstance(score, (int, float)), "Score should be numeric"

    def test_score_against_empty_team_returns_zero(self, assistant):
        """Test that scoring against empty team returns 0."""
        # Arrange
        champion = 'Aatrox'
        enemy_team = []

        # Act
        score = assistant.score_against_team(champion, enemy_team)

        # Assert
        assert score == 0.0, "Empty enemy team should return 0 score"

    def test_score_consistency(self, assistant):
        """Test that same inputs produce same outputs."""
        # Arrange
        champion = 'Aatrox'
        enemy_team = ['Darius', 'Ahri']

        # Act
        score1 = assistant.score_against_team(champion, enemy_team)
        score2 = assistant.score_against_team(champion, enemy_team)

        # Assert
        assert score1 == score2, "Same inputs should produce same score"


class TestChampionAnalysisNonRegression:
    """Non-regression tests for champion analysis features."""

    def test_tierlist_delta2_method_exists(self, assistant):
        """Regression test: tierlist_delta2 method exists."""
        assert hasattr(assistant, 'tierlist_delta2'), \
            "Assistant must have tierlist_delta2 method"
        assert callable(assistant.tierlist_delta2), \
            "tierlist_delta2 must be callable"

    def test_score_against_team_method_exists(self, assistant):
        """Regression test: score_against_team method exists."""
        assert hasattr(assistant, 'score_against_team'), \
            "Assistant must have score_against_team method"
        assert callable(assistant.score_against_team), \
            "score_against_team must be callable"

    def test_methods_return_expected_types(self, assistant):
        """Regression test: Methods return expected types."""
        # tierlist_delta2 should return list
        result1 = assistant.tierlist_delta2(['Aatrox'])
        assert isinstance(result1, list), "tierlist_delta2 should return list"

        # score_against_team should return float/int
        result2 = assistant.score_against_team('Aatrox', ['Darius'])
        assert isinstance(result2, (int, float)), \
            "score_against_team should return numeric"
