"""
Regression test for bug: TypeError in _calculate_and_display_recommendations.

Bug description:
    TypeError: Assistant._calculate_and_display_recommendations() takes from 4 to 5
    positional arguments but 6 were given.

    Root cause: The method was defined twice in assistant.py. A legacy version without
    the `banned_champions` parameter appeared after the correct version and overwrote it
    at class definition time, effectively hiding the correct 5-argument signature (+ self).

    The legacy definition accepted only:
        (self, enemy_team, ally_team, nb_results, champion_pool=None)  -> 5 args max

    The correct definition accepts:
        (self, enemy_team, ally_team, nb_results, champion_pool=None, banned_champions=None)
                                                                       -> 6 args max

    The caller in src/ui/lol_coach_legacy.py:1565 always passed all 6 arguments:
        assistant._calculate_and_display_recommendations(
            enemy_team, ally_team, nb_results, champion_pool, banned_champions
        )
    This raised TypeError because the surviving (legacy) method only accepted 5.

Fixed in: T1 (2026-02-22)
    - Duplicate legacy method definition removed from assistant.py
    - Correct method with banned_champions parameter is now the only definition

Test approach:
    Verify that calling _calculate_and_display_recommendations() with all 5 positional
    arguments (excluding self) does NOT raise TypeError, and that the call is properly
    delegated to the underlying RecommendationEngine.
"""

import pytest
from unittest.mock import Mock
from src.assistant import Assistant


@pytest.fixture
def mock_data_source():
    """Mock DataSource with all methods required by Assistant.__init__."""
    mock_db = Mock()
    mock_db.connect.return_value = None
    mock_db.close.return_value = None
    mock_db.get_champion_matchups_for_draft.return_value = []
    mock_db.get_reverse_matchups_for_draft.return_value = []
    mock_db.get_matchup_delta2.return_value = None
    return mock_db


@pytest.fixture
def assistant_instance(mock_data_source):
    """Create an Assistant with mocked data source via dependency injection."""
    return Assistant(data_source=mock_data_source, verbose=False)


class TestCalculateAndDisplayRecommendationsRegression:
    """
    Regression tests for the duplicated-method TypeError bug in Assistant.

    Bug: _calculate_and_display_recommendations() raised TypeError when called with
    the banned_champions argument because a legacy definition without that parameter
    silently overwrote the correct one in the class body.
    """

    def test_regression_accepts_banned_champions_argument(self, assistant_instance):
        """
        Regression test: _calculate_and_display_recommendations() must accept
        banned_champions as a 5th positional argument (6th including self).

        Before fix: TypeError: takes from 4 to 5 positional arguments but 6 were given
        After fix:  Call succeeds; delegate to recommender without raising TypeError.

        Caller context (src/ui/lol_coach_legacy.py:1565):
            assistant._calculate_and_display_recommendations(
                enemy_team, ally_team, nb_results, champion_pool, banned_champions
            )
        """
        # Mock the underlying recommender so no real DB access is needed
        mock_recommender = Mock()
        mock_recommender.calculate_and_display_recommendations.return_value = []
        assistant_instance.recommender = mock_recommender

        # WHEN: called with all 5 positional arguments (the exact call that triggered the bug)
        # This must NOT raise TypeError
        result = assistant_instance._calculate_and_display_recommendations(
            ["Zeri"],  # enemy_team
            ["Varus"],  # ally_team
            3,  # nb_results
            ["Ashe"],  # champion_pool
            ["Darius"],  # banned_champions  <- this argument caused TypeError before fix
        )

        # THEN: Returns the value from the recommender (no exception raised)
        assert result == []

    def test_regression_delegates_banned_champions_to_recommender(self, assistant_instance):
        """
        Regression test: banned_champions must be forwarded to the recommender.

        Verify that _calculate_and_display_recommendations() passes banned_champions
        through to recommender.calculate_and_display_recommendations().
        """
        mock_recommender = Mock()
        mock_recommender.calculate_and_display_recommendations.return_value = [("Ashe", 72.5)]
        assistant_instance.recommender = mock_recommender

        enemy_team = ["Zeri", "Thresh"]
        ally_team = ["Jinx"]
        nb_results = 5
        champion_pool = ["Ashe", "Caitlyn"]
        banned_champions = ["Darius", "Garen"]

        assistant_instance._calculate_and_display_recommendations(
            enemy_team, ally_team, nb_results, champion_pool, banned_champions
        )

        # THEN: recommender received all arguments including banned_champions
        mock_recommender.calculate_and_display_recommendations.assert_called_once_with(
            enemy_team, ally_team, nb_results, champion_pool, banned_champions
        )

    def test_regression_backward_compat_without_banned_champions(self, assistant_instance):
        """
        Regression test: Omitting banned_champions must still work (backward compatibility).

        Calls with 3 or 4 positional arguments (original API) must not break.
        """
        mock_recommender = Mock()
        mock_recommender.calculate_and_display_recommendations.return_value = []
        assistant_instance.recommender = mock_recommender

        # 3 positional args (the minimum valid call)
        assistant_instance._calculate_and_display_recommendations(["Jhin"], ["Ashe"], 3)

        # 4 positional args (with champion_pool, no banned_champions)
        assistant_instance._calculate_and_display_recommendations(
            ["Jhin"], ["Ashe"], 3, ["Caitlyn"]
        )

        # THEN: Two calls made, no TypeError raised
        assert mock_recommender.calculate_and_display_recommendations.call_count == 2

    def test_regression_method_signature_has_banned_champions_parameter(self):
        """
        Regression test: Verify the method signature at import time includes banned_champions.

        Inspects the actual method signature to confirm the correct definition
        (not the legacy one) is active on the class.
        """
        import inspect

        method = getattr(Assistant, "_calculate_and_display_recommendations")
        sig = inspect.signature(method)
        params = list(sig.parameters.keys())

        # Expected parameters: self, enemy_team, ally_team, nb_results,
        #                      champion_pool, banned_champions
        assert "banned_champions" in params, (
            "banned_champions parameter missing from method signature - "
            "legacy method definition may have overwritten the correct one again"
        )
        assert "champion_pool" in params
        assert "enemy_team" in params
        assert "ally_team" in params
        assert "nb_results" in params

        # Both optional parameters should have default value None
        assert sig.parameters["champion_pool"].default is None
        assert sig.parameters["banned_champions"].default is None

    def test_regression_returns_recommender_result(self, assistant_instance):
        """
        Regression test: Return value from recommender is passed back to caller.

        Ensures the wrapper does not swallow the return value.
        """
        expected_result = [("Ashe", 80.0), ("Caitlyn", 75.5), ("Jhin", 70.1)]
        mock_recommender = Mock()
        mock_recommender.calculate_and_display_recommendations.return_value = expected_result
        assistant_instance.recommender = mock_recommender

        result = assistant_instance._calculate_and_display_recommendations(
            ["Zeri"], ["Varus"], 3, ["Ashe", "Caitlyn", "Jhin"], ["Darius"]
        )

        assert result == expected_result
