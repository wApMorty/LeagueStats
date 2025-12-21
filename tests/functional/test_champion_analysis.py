"""
Functional tests for Champion Analysis features.

Tests menu option 4 (Analysis & Tournament) functionalities.
"""


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


class TestChampionAnalysisNonRegression:
    """Non-regression tests for champion analysis features."""

    def test_tierlist_delta2_method_exists(self, assistant):
        """Regression test: tierlist_delta2 method exists."""
        assert hasattr(assistant, 'tierlist_delta2'), \
            "Assistant must have tierlist_delta2 method"
        assert callable(assistant.tierlist_delta2), \
            "tierlist_delta2 must be callable"

    def test_methods_return_expected_types(self, assistant):
        """Regression test: Methods return expected types."""
        # tierlist_delta2 should return list
        result1 = assistant.tierlist_delta2(['Aatrox'])
        assert isinstance(result1, list), "tierlist_delta2 should return list"
