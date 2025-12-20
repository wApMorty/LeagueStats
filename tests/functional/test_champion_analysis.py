"""
Functional tests for Champion Analysis features.

Tests menu option 4 (Analysis & Tournament) functionalities:
- Blind pick analysis
- Score against enemy team
- Optimal duo finding
"""

import pytest


class TestBlindPickAnalysis:
    """Test blind pick analysis functionality."""

    def test_blind_pick_returns_sorted_list(self, assistant):
        """Test blind_pick returns champions sorted by score."""
        # Arrange
        champion_list = ['Aatrox', 'Ahri', 'Jinx']

        # Act
        result = assistant.blind_pick(champion_list)

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

    def test_blind_pick_sorted_descending(self, assistant):
        """Test that blind pick results are sorted by score (descending)."""
        # Arrange
        champion_list = ['Aatrox', 'Ahri', 'Jinx', 'Lee Sin']

        # Act
        result = assistant.blind_pick(champion_list)

        # Assert
        if len(result) > 1:
            scores = [score for _, score in result]
            assert scores == sorted(scores, reverse=True), \
                "Results should be sorted descending by score"

    def test_blind_pick_empty_list(self, assistant):
        """Test blind pick with empty champion list."""
        # Act
        result = assistant.blind_pick([])

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


class TestOptimalDuoFinding:
    """Test optimal duo finding functionality."""

    def test_optimal_duo_for_champion(self, assistant):
        """Test finding optimal duo for a given champion."""
        # Arrange
        champion = 'Aatrox'
        champion_pool = ['Ahri', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius', 'Zed']

        # Act
        result = assistant.optimal_duo_for_champion(
            champion=champion,
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=3
        )

        # Assert
        assert isinstance(result, list), "Should return a list"
        assert len(result) <= 3, "Should return at most nb_results entries"

        # Validate structure
        for entry in result:
            assert 'duo_partner' in entry, "Entry should have duo_partner"
            assert 'combined_score' in entry, "Entry should have combined_score"
            assert entry['duo_partner'] in champion_pool, \
                f"Duo partner {entry['duo_partner']} should be from pool"

    def test_optimal_duo_sorted_by_score(self, assistant):
        """Test that optimal duo results are sorted by combined score."""
        # Arrange
        champion = 'Ahri'
        champion_pool = ['Aatrox', 'Jinx', 'Lee Sin', 'Thresh']
        enemy_team = ['Darius', 'Zed', 'Vayne']

        # Act
        result = assistant.optimal_duo_for_champion(
            champion=champion,
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=4
        )

        # Assert
        if len(result) > 1:
            scores = [entry['combined_score'] for entry in result]
            assert scores == sorted(scores, reverse=True), \
                "Results should be sorted descending by combined_score"

    def test_optimal_duo_empty_pool(self, assistant):
        """Test optimal duo with empty champion pool."""
        # Arrange
        champion = 'Aatrox'
        champion_pool = []
        enemy_team = ['Darius']

        # Act
        result = assistant.optimal_duo_for_champion(
            champion=champion,
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=3
        )

        # Assert
        assert result == [], "Empty pool should return empty result"

    def test_optimal_duo_excludes_main_champion(self, assistant):
        """Test that optimal duo doesn't include the main champion."""
        # Arrange
        champion = 'Aatrox'
        champion_pool = ['Aatrox', 'Ahri', 'Jinx']  # Pool includes main champion
        enemy_team = ['Darius']

        # Act
        result = assistant.optimal_duo_for_champion(
            champion=champion,
            champion_pool=champion_pool,
            enemy_team=enemy_team,
            nb_results=3
        )

        # Assert
        for entry in result:
            assert entry['duo_partner'] != champion, \
                "Duo partner should not be the main champion"


class TestChampionAnalysisNonRegression:
    """Non-regression tests for champion analysis features."""

    def test_blind_pick_method_exists(self, assistant):
        """Regression test: blind_pick method exists."""
        assert hasattr(assistant, 'blind_pick'), \
            "Assistant must have blind_pick method"
        assert callable(assistant.blind_pick), \
            "blind_pick must be callable"

    def test_score_against_team_method_exists(self, assistant):
        """Regression test: score_against_team method exists."""
        assert hasattr(assistant, 'score_against_team'), \
            "Assistant must have score_against_team method"
        assert callable(assistant.score_against_team), \
            "score_against_team must be callable"

    def test_optimal_duo_method_exists(self, assistant):
        """Regression test: optimal_duo_for_champion method exists."""
        assert hasattr(assistant, 'optimal_duo_for_champion'), \
            "Assistant must have optimal_duo_for_champion method"
        assert callable(assistant.optimal_duo_for_champion), \
            "optimal_duo_for_champion must be callable"

    def test_methods_return_expected_types(self, assistant):
        """Regression test: Methods return expected types."""
        # blind_pick should return list
        result1 = assistant.blind_pick(['Aatrox'])
        assert isinstance(result1, list), "blind_pick should return list"

        # score_against_team should return float/int
        result2 = assistant.score_against_team('Aatrox', ['Darius'])
        assert isinstance(result2, (int, float)), \
            "score_against_team should return numeric"

        # optimal_duo_for_champion should return list
        result3 = assistant.optimal_duo_for_champion(
            'Aatrox', ['Ahri'], ['Darius'], nb_results=1
        )
        assert isinstance(result3, list), \
            "optimal_duo_for_champion should return list"
