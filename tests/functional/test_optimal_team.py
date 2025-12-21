"""
Functional tests for Optimal Team Builder.

Tests menu option 5 functionalities (simplified version).
"""

import pytest


class TestBanRecommendations:
    """Test ban recommendation functionality."""

    def test_ban_recommendations_returns_list(self, assistant):
        """Test that get_ban_recommendations returns a list."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']

        # Act
        result = assistant.get_ban_recommendations(champion_pool, num_bans=3)

        # Assert
        assert isinstance(result, list), "Should return a list"


class TestOptimalTeamNonRegression:
    """Non-regression tests for optimal team builder."""

    def test_get_ban_recommendations_method_exists(self, assistant):
        """Regression test: get_ban_recommendations exists."""
        assert hasattr(assistant, 'get_ban_recommendations'), \
            "Assistant must have get_ban_recommendations method"
        assert callable(assistant.get_ban_recommendations), \
            "get_ban_recommendations must be callable"

    def test_set_scoring_profile_method_exists(self, assistant):
        """Regression test: set_scoring_profile exists."""
        assert hasattr(assistant, 'set_scoring_profile'), \
            "Assistant must have set_scoring_profile method"
        assert callable(assistant.set_scoring_profile), \
            "set_scoring_profile must be callable"

    def test_find_optimal_trios_method_exists(self, assistant):
        """Regression test: find_optimal_trios_holistic exists."""
        assert hasattr(assistant, 'find_optimal_trios_holistic'), \
            "Assistant must have find_optimal_trios_holistic method"
        assert callable(assistant.find_optimal_trios_holistic), \
            "find_optimal_trios_holistic must be callable"
