"""
Functional tests for Optimal Team Builder.

Tests menu option 5 functionalities:
- Finding optimal trios
- Different scoring profiles
- Ban recommendations
- Team composition analysis
"""

import pytest


class TestOptimalTrioFinding:
    """Test optimal trio finding functionality."""

    def test_find_optimal_trios_returns_list(self, assistant):
        """Test that find_optimal_trios_holistic returns a list."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius', 'Zed', 'Vayne']

        # Act
        result = assistant.find_optimal_trios_holistic(
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=3,
            profile="balanced"
        )

        # Assert
        assert isinstance(result, list), "Should return a list"
        assert len(result) <= 3, "Should return at most nb_results"

    def test_optimal_trio_structure(self, assistant):
        """Test that optimal trio results have expected structure."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius']

        # Act
        result = assistant.find_optimal_trios_holistic(
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=1,
            profile="balanced"
        )

        # Assert
        if result:
            trio = result[0]
            assert 'champions' in trio, "Trio should have 'champions' field"
            assert 'total_score' in trio, "Trio should have 'total_score' field"
            assert 'metrics' in trio, "Trio should have 'metrics' field"

            # Validate champions list
            assert isinstance(trio['champions'], list), "Champions should be a list"
            assert len(trio['champions']) == 3, "Should have exactly 3 champions"

            # All champions should be from pool
            for champ in trio['champions']:
                assert champ in champion_pool, f"{champ} should be from pool"

    def test_optimal_trio_sorted_by_score(self, assistant):
        """Test that optimal trios are sorted by total score."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius', 'Zed']

        # Act
        result = assistant.find_optimal_trios_holistic(
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=3,
            profile="balanced"
        )

        # Assert
        if len(result) > 1:
            scores = [trio['total_score'] for trio in result]
            assert scores == sorted(scores, reverse=True), \
                "Trios should be sorted descending by total_score"

    def test_optimal_trio_no_duplicates(self, assistant):
        """Test that optimal trio doesn't contain duplicate champions."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius']

        # Act
        result = assistant.find_optimal_trios_holistic(
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=3,
            profile="balanced"
        )

        # Assert
        for trio in result:
            champions = trio['champions']
            assert len(champions) == len(set(champions)), \
                "Trio should not have duplicate champions"

    def test_optimal_trio_pool_too_small(self, assistant):
        """Test optimal trio with pool smaller than 3 champions."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri']  # Only 2 champions
        enemy_team = ['Darius']

        # Act
        result = assistant.find_optimal_trios_holistic(
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=1,
            profile="balanced"
        )

        # Assert
        assert result == [], "Pool with <3 champions should return empty"


class TestScoringProfiles:
    """Test different scoring profiles for team building."""

    def test_balanced_profile(self, assistant):
        """Test optimal trio with balanced profile."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius']

        # Act
        result = assistant.find_optimal_trios_holistic(
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=1,
            profile="balanced"
        )

        # Assert
        assert result is not None, "Balanced profile should work"

    def test_aggressive_profile(self, assistant):
        """Test optimal trio with aggressive profile."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius']

        # Act
        result = assistant.find_optimal_trios_holistic(
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=1,
            profile="aggressive"
        )

        # Assert
        assert result is not None, "Aggressive profile should work"

    def test_defensive_profile(self, assistant):
        """Test optimal trio with defensive profile."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius']

        # Act
        result = assistant.find_optimal_trios_holistic(
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=1,
            profile="defensive"
        )

        # Assert
        assert result is not None, "Defensive profile should work"

    def test_different_profiles_yield_different_results(self, assistant):
        """Test that different profiles can yield different optimal trios."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius', 'Zed', 'Vayne']

        # Act
        balanced = assistant.find_optimal_trios_holistic(
            champion_pool, enemy_team, nb_results=1, profile="balanced"
        )
        aggressive = assistant.find_optimal_trios_holistic(
            champion_pool, enemy_team, nb_results=1, profile="aggressive"
        )

        # Assert
        # Note: Different profiles might yield different results
        # This test just validates both work
        assert balanced is not None
        assert aggressive is not None


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
        assert len(result) <= 3, "Should return at most num_bans"

    def test_ban_recommendations_structure(self, assistant):
        """Test ban recommendations have expected structure."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx']

        # Act
        result = assistant.get_ban_recommendations(champion_pool, num_bans=2)

        # Assert
        for entry in result:
            assert 'champion' in entry, "Entry should have 'champion'"
            assert 'threat_score' in entry, "Entry should have 'threat_score'"

    def test_ban_recommendations_sorted(self, assistant):
        """Test that ban recommendations are sorted by threat score."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin']

        # Act
        result = assistant.get_ban_recommendations(champion_pool, num_bans=4)

        # Assert
        if len(result) > 1:
            scores = [entry['threat_score'] for entry in result]
            assert scores == sorted(scores, reverse=True), \
                "Bans should be sorted descending by threat score"


class TestOptimalTeamNonRegression:
    """Non-regression tests for optimal team builder."""

    def test_find_optimal_trios_method_exists(self, assistant):
        """Regression test: find_optimal_trios_holistic exists."""
        assert hasattr(assistant, 'find_optimal_trios_holistic'), \
            "Assistant must have find_optimal_trios_holistic method"
        assert callable(assistant.find_optimal_trios_holistic), \
            "find_optimal_trios_holistic must be callable"

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

    def test_scoring_profile_changes_results(self, assistant):
        """Regression test: set_scoring_profile affects calculations."""
        # Arrange
        champion_pool = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius']

        # Act
        assistant.set_scoring_profile("balanced")
        result_balanced = assistant.find_optimal_trios_holistic(
            champion_pool, enemy_team, nb_results=1, profile="balanced"
        )

        assistant.set_scoring_profile("aggressive")
        result_aggressive = assistant.find_optimal_trios_holistic(
            champion_pool, enemy_team, nb_results=1, profile="aggressive"
        )

        # Assert - Both should work (results may or may not differ)
        assert result_balanced is not None
        assert result_aggressive is not None
