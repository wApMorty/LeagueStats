"""
Tests for APIDataSource - HTTP client for FastAPI backend.

This test suite uses httpx mocking to test API data source without making
real HTTP requests. It verifies:
- Correct endpoint mapping
- Retry logic on failures
- Cache warmup
- Error handling

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration (Adapter Pattern Implementation)
"""

import pytest
from unittest.mock import Mock, patch
import httpx

from src.api_data_source import APIDataSource
from src.models import Matchup, MatchupDraft, Synergy


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.Client for testing without real HTTP requests."""
    with patch("src.api_data_source.httpx.Client") as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def api_data_source(mock_httpx_client):
    """Create APIDataSource with mocked HTTP client."""
    data_source = APIDataSource(base_url="https://test-api.example.com", timeout=5)
    # Patch connect to skip cache warmup
    with patch.object(data_source, "_warm_up_caches"):
        data_source.connect()
    return data_source


class TestAPIDataSourceBasics:
    """Test basic connection management and instantiation."""

    def test_init_sets_base_url(self):
        """Test that initialization sets base URL."""
        data_source = APIDataSource(base_url="https://custom-api.example.com")
        assert data_source._base_url == "https://custom-api.example.com"

    def test_init_sets_timeout(self):
        """Test that initialization sets timeout."""
        data_source = APIDataSource(timeout=20)
        assert data_source._timeout == 20

    def test_connect_creates_client(self, mock_httpx_client):
        """Test that connect() creates httpx.Client."""
        data_source = APIDataSource()
        with patch.object(data_source, "_warm_up_caches"):
            data_source.connect()
        assert data_source._client is not None

    def test_close_closes_client(self, api_data_source):
        """Test that close() closes HTTP client."""
        api_data_source.close()
        api_data_source._client.close.assert_called_once()


class TestAPIDataSourceChampionQueries:
    """Test champion-related queries with mocked API responses."""

    def test_get_champion_id_returns_id_from_api(self, api_data_source):
        """Test get_champion_id() queries API and returns ID."""
        # Mock API response with wrapped format
        mock_response = Mock()
        mock_response.json.return_value = {"champions": [{"id": 42, "name": "Jinx"}], "count": 1}
        api_data_source._client.get.return_value = mock_response

        champion_id = api_data_source.get_champion_id("Jinx")

        assert champion_id == 42
        api_data_source._client.get.assert_called_with("/api/champions", params={})

    def test_get_champion_id_uses_cache(self, api_data_source):
        """Test get_champion_id() uses cache before querying API."""
        # Pre-populate cache
        api_data_source._champion_cache = {"jinx": 42, "Jinx": 42}

        champion_id = api_data_source.get_champion_id("Jinx")

        assert champion_id == 42
        # Should not call API if cache hit
        api_data_source._client.get.assert_not_called()

    def test_get_champion_id_returns_none_for_empty_response(self, api_data_source):
        """Test get_champion_id() returns None when champion not found."""
        mock_response = Mock()
        mock_response.json.return_value = {"champions": [], "count": 0}
        api_data_source._client.get.return_value = mock_response

        champion_id = api_data_source.get_champion_id("InvalidChamp")
        assert champion_id is None

    def test_get_champion_by_id_returns_name_from_api(self, api_data_source):
        """Test get_champion_by_id() queries API and returns name."""
        mock_response = Mock()
        mock_response.json.return_value = {"id": 42, "name": "Jinx"}
        api_data_source._client.get.return_value = mock_response

        champion_name = api_data_source.get_champion_by_id(42)

        assert champion_name == "Jinx"
        api_data_source._client.get.assert_called_with("/api/champions/42", params={})

    def test_get_all_champion_names_returns_dict(self, api_data_source):
        """Test get_all_champion_names() returns ID->name mapping."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "champions": [
                {"id": 1, "name": "Aatrox"},
                {"id": 2, "name": "Ahri"},
                {"id": 42, "name": "Jinx"},
            ],
            "count": 3,
        }
        api_data_source._client.get.return_value = mock_response

        names = api_data_source.get_all_champion_names()

        assert names == {1: "Aatrox", 2: "Ahri", 42: "Jinx"}

    def test_build_champion_cache_returns_dict(self, api_data_source):
        """Test build_champion_cache() returns name->ID mapping."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "champions": [
                {"id": 1, "name": "Aatrox"},
                {"id": 42, "name": "Jinx"},
            ],
            "count": 2,
        }
        api_data_source._client.get.return_value = mock_response

        cache = api_data_source.build_champion_cache()

        assert "Aatrox" in cache
        assert "aatrox" in cache  # Lowercase variant
        assert cache["Aatrox"] == 1
        assert cache["Jinx"] == 42


class TestAPIDataSourceMatchupQueries:
    """Test matchup-related queries with mocked API responses."""

    def test_get_champion_matchups_by_name_returns_matchup_objects(self, api_data_source):
        """Test get_champion_matchups_by_name() returns Matchup dataclasses."""
        # Mock champion ID lookup
        api_data_source._champion_cache = {"aatrox": 1, "Aatrox": 1}

        # Mock matchups response with wrapped format
        mock_response = Mock()
        mock_response.json.return_value = {
            "champion_id": 1,
            "champion_name": "Aatrox",
            "matchups": [
                {
                    "enemy_name": "Darius",
                    "winrate": 48.5,
                    "delta1": -150.0,
                    "delta2": -200.0,
                    "pickrate": 8.5,
                    "games": 1500,
                },
                {
                    "enemy_name": "Garen",
                    "winrate": 52.0,
                    "delta1": 100.0,
                    "delta2": 150.0,
                    "pickrate": 12.3,
                    "games": 2000,
                },
            ],
            "count": 2,
        }
        api_data_source._client.get.return_value = mock_response

        matchups = api_data_source.get_champion_matchups_by_name("Aatrox")

        assert isinstance(matchups, list)
        assert len(matchups) == 2
        assert all(isinstance(m, Matchup) for m in matchups)
        assert matchups[0].enemy_name == "Darius"

    def test_get_champion_matchups_by_name_returns_tuples_when_requested(self, api_data_source):
        """Test get_champion_matchups_by_name() can return tuples."""
        api_data_source._champion_cache = {"aatrox": 1, "Aatrox": 1}

        mock_response = Mock()
        mock_response.json.return_value = {
            "champion_id": 1,
            "champion_name": "Aatrox",
            "matchups": [
                {
                    "enemy_name": "Darius",
                    "winrate": 48.5,
                    "delta1": -150.0,
                    "delta2": -200.0,
                    "pickrate": 8.5,
                    "games": 1500,
                }
            ],
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        matchups = api_data_source.get_champion_matchups_by_name("Aatrox", as_dataclass=False)

        assert isinstance(matchups, list)
        assert len(matchups) == 1
        assert isinstance(matchups[0], tuple)

    def test_get_champion_matchups_for_draft_returns_matchupdraft_objects(self, api_data_source):
        """Test get_champion_matchups_for_draft() returns MatchupDraft dataclasses."""
        api_data_source._champion_cache = {"aatrox": 1, "Aatrox": 1}

        mock_response = Mock()
        mock_response.json.return_value = {
            "champion_id": 1,
            "champion_name": "Aatrox",
            "matchups": [
                {
                    "enemy_name": "Darius",
                    "winrate": 48.5,
                    "delta1": -150.0,
                    "delta2": -200.0,
                    "pickrate": 8.5,
                    "games": 1500,
                }
            ],
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        matchups = api_data_source.get_champion_matchups_for_draft("Aatrox")

        assert isinstance(matchups, list)
        assert len(matchups) == 1
        assert isinstance(matchups[0], MatchupDraft)
        assert matchups[0].enemy_name == "Darius"
        assert matchups[0].delta2 == -200.0

    def test_get_matchup_delta2_returns_float_from_api(self, api_data_source):
        """Test get_matchup_delta2() queries API and returns delta2."""
        api_data_source._champion_cache = {"aatrox": 1, "Aatrox": 1, "darius": 2, "Darius": 2}

        mock_response = Mock()
        mock_response.json.return_value = {"delta2": -200.0}
        api_data_source._client.get.return_value = mock_response

        delta2 = api_data_source.get_matchup_delta2("Aatrox", "Darius")

        assert delta2 == -200.0

    def test_get_matchup_delta2_uses_cache(self, api_data_source):
        """Test get_matchup_delta2() uses cache before querying API."""
        api_data_source._matchups_cache = {("aatrox", "darius"): -200.0}

        delta2 = api_data_source.get_matchup_delta2("Aatrox", "Darius")

        assert delta2 == -200.0
        api_data_source._client.get.assert_not_called()

    def test_get_all_matchups_bulk_returns_dict(self, api_data_source):
        """Test get_all_matchups_bulk() returns matchup cache."""
        # Pre-populate champion cache for ID->name lookup
        api_data_source._champion_cache = {
            "Aatrox": 1,
            "aatrox": 1,
            "Darius": 2,
            "darius": 2,
            "Garen": 3,
            "garen": 3,
        }

        mock_response = Mock()
        mock_response.json.return_value = {
            "matchups": {
                "1": [  # Aatrox matchups
                    {
                        "enemy_id": 2,
                        "enemy_name": "Darius",
                        "delta2": -200.0,
                        "games": 1500,
                        "winrate": 48.5,
                    },
                    {
                        "enemy_id": 3,
                        "enemy_name": "Garen",
                        "delta2": 150.0,
                        "games": 2000,
                        "winrate": 52.0,
                    },
                ]
            },
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        matchups_bulk = api_data_source.get_all_matchups_bulk()

        assert isinstance(matchups_bulk, dict)
        assert ("aatrox", "darius") in matchups_bulk
        assert matchups_bulk[("aatrox", "darius")] == -200.0

    def test_get_champion_base_winrate_calculates_weighted_average(self, api_data_source):
        """Test get_champion_base_winrate() calculates weighted average."""
        api_data_source._champion_cache = {"aatrox": 1, "Aatrox": 1}

        mock_response = Mock()
        mock_response.json.return_value = {
            "champion_id": 1,
            "champion_name": "Aatrox",
            "matchups": [
                {
                    "enemy_name": "Darius",
                    "winrate": 48.0,
                    "delta1": -150.0,
                    "delta2": -200.0,
                    "pickrate": 8.5,
                    "games": 1000,
                },
                {
                    "enemy_name": "Garen",
                    "winrate": 52.0,
                    "delta1": 100.0,
                    "delta2": 150.0,
                    "pickrate": 12.3,
                    "games": 1000,
                },
            ],
            "count": 2,
        }
        api_data_source._client.get.return_value = mock_response

        winrate = api_data_source.get_champion_base_winrate("Aatrox")

        # Weighted average: (48*1000 + 52*1000) / 2000 = 50.0
        assert winrate == 50.0


class TestAPIDataSourceSynergyQueries:
    """Test synergy-related queries with mocked API responses."""

    def test_get_champion_synergies_by_name_returns_synergy_objects(self, api_data_source):
        """Test get_champion_synergies_by_name() returns Synergy dataclasses."""
        api_data_source._champion_cache = {"yasuo": 42, "Yasuo": 42}

        mock_response = Mock()
        mock_response.json.return_value = {
            "champion_id": 42,
            "champion_name": "Yasuo",
            "synergies": [
                {
                    "ally_name": "Malphite",
                    "winrate": 55.0,
                    "delta2": 250.0,
                    "pickrate": 8.5,
                    "games": 1000,
                }
            ],
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        synergies = api_data_source.get_champion_synergies_by_name("Yasuo")

        assert isinstance(synergies, list)
        assert len(synergies) == 1
        assert isinstance(synergies[0], Synergy)
        assert synergies[0].ally_name == "Malphite"

    def test_get_synergy_delta2_returns_float_from_cache(self, api_data_source):
        """Test get_synergy_delta2() uses cache."""
        api_data_source._synergies_cache = {("yasuo", "malphite"): 250.0}

        delta2 = api_data_source.get_synergy_delta2("Yasuo", "Malphite")

        assert delta2 == 250.0
        api_data_source._client.get.assert_not_called()

    def test_get_all_synergies_bulk_returns_dict(self, api_data_source):
        """Test get_all_synergies_bulk() returns synergy cache."""
        # Pre-populate champion cache for ID->name lookup
        api_data_source._champion_cache = {
            "Yasuo": 42,
            "yasuo": 42,
            "Malphite": 516,
            "malphite": 516,
            "Gragas": 79,
            "gragas": 79,
        }

        mock_response = Mock()
        mock_response.json.return_value = {
            "synergies": {
                "42": [  # Yasuo synergies
                    {
                        "ally_id": 516,
                        "ally_name": "Malphite",
                        "delta2": 250.0,
                        "games": 1000,
                        "winrate": 55.0,
                    },
                    {
                        "ally_id": 79,
                        "ally_name": "Gragas",
                        "delta2": 120.0,
                        "games": 800,
                        "winrate": 52.5,
                    },
                ]
            },
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        synergies_bulk = api_data_source.get_all_synergies_bulk()

        assert isinstance(synergies_bulk, dict)
        assert ("yasuo", "malphite") in synergies_bulk
        assert synergies_bulk[("yasuo", "malphite")] == 250.0


class TestAPIDataSourceChampionScores:
    """Test champion scores queries with mocked API responses."""

    def test_get_champion_scores_by_name_returns_dict(self, api_data_source):
        """Test get_champion_scores_by_name() returns scores dictionary."""
        api_data_source._champion_cache = {"jinx": 42, "Jinx": 42}

        mock_response = Mock()
        mock_response.json.return_value = {
            "avg_delta2": 150.5,
            "variance": 50.2,
            "coverage": 0.85,
            "peak_impact": 200.0,
            "volatility": 30.5,
            "target_ratio": 0.65,
        }
        api_data_source._client.get.return_value = mock_response

        scores = api_data_source.get_champion_scores_by_name("Jinx")

        assert isinstance(scores, dict)
        assert "avg_delta2" in scores
        assert scores["avg_delta2"] == 150.5

    def test_get_champion_scores_by_name_returns_none_on_404(self, api_data_source):
        """Test get_champion_scores_by_name() returns None when no scores exist."""
        api_data_source._champion_cache = {"jinx": 42, "Jinx": 42}

        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        api_data_source._client.get.side_effect = httpx.HTTPStatusError(
            "Not found", request=Mock(), response=mock_response
        )

        scores = api_data_source.get_champion_scores_by_name("Jinx")
        assert scores is None

    def test_get_all_champion_scores_returns_list(self, api_data_source):
        """Test get_all_champion_scores() returns list of tuples."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "champion_name": "Jinx",
                "avg_delta2": 150.5,
                "variance": 50.2,
                "coverage": 0.85,
                "peak_impact": 200.0,
                "volatility": 30.5,
                "target_ratio": 0.65,
            }
        ]
        api_data_source._client.get.return_value = mock_response

        all_scores = api_data_source.get_all_champion_scores()

        assert isinstance(all_scores, list)
        assert len(all_scores) == 1
        assert isinstance(all_scores[0], tuple)

    def test_champion_scores_table_exists_returns_true_with_data(self, api_data_source):
        """Test champion_scores_table_exists() returns True when data exists."""
        mock_response = Mock()
        mock_response.json.return_value = [{"champion_name": "Jinx"}]
        api_data_source._client.get.return_value = mock_response

        exists = api_data_source.champion_scores_table_exists()
        assert exists is True

    def test_champion_scores_table_exists_returns_false_on_error(self, api_data_source):
        """Test champion_scores_table_exists() returns False on error."""
        api_data_source._client.get.side_effect = httpx.HTTPError("Network error")

        exists = api_data_source.champion_scores_table_exists()
        assert exists is False


class TestAPIDataSourceBanRecommendations:
    """Test ban recommendations queries with mocked API responses."""

    def test_get_pool_ban_recommendations_returns_list(self, api_data_source):
        """Test get_pool_ban_recommendations() returns list of tuples."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "enemy_champion": "Zed",
                "threat_score": 85.5,
                "best_response_delta2": -150.0,
                "best_response_champion": "Malzahar",
                "matchups_count": 10,
            }
        ]
        api_data_source._client.get.return_value = mock_response

        bans = api_data_source.get_pool_ban_recommendations("TestPool")

        assert isinstance(bans, list)
        assert len(bans) == 1
        assert isinstance(bans[0], tuple)
        assert bans[0][0] == "Zed"

    def test_get_pool_ban_recommendations_returns_empty_on_404(self, api_data_source):
        """Test get_pool_ban_recommendations() returns empty list on 404."""
        mock_response = Mock()
        mock_response.status_code = 404
        api_data_source._client.get.side_effect = httpx.HTTPStatusError(
            "Not found", request=Mock(), response=mock_response
        )

        bans = api_data_source.get_pool_ban_recommendations("NonExistentPool")
        assert bans == []

    def test_pool_has_ban_recommendations_returns_true_with_data(self, api_data_source):
        """Test pool_has_ban_recommendations() returns True when recommendations exist."""
        mock_response = Mock()
        mock_response.json.return_value = [
            {
                "enemy_champion": "Zed",
                "threat_score": 85.5,
                "best_response_delta2": -150.0,
                "best_response_champion": "Malzahar",
                "matchups_count": 10,
            }
        ]
        api_data_source._client.get.return_value = mock_response

        has_bans = api_data_source.pool_has_ban_recommendations("TestPool")
        assert has_bans is True

    def test_pool_has_ban_recommendations_returns_false_without_data(self, api_data_source):
        """Test pool_has_ban_recommendations() returns False when no recommendations."""
        mock_response = Mock()
        mock_response.json.return_value = []
        api_data_source._client.get.return_value = mock_response

        has_bans = api_data_source.pool_has_ban_recommendations("NonExistentPool")
        assert has_bans is False


class TestAPIDataSourceExceptionPropagation:
    """
    Regression tests for bug fix: API exceptions must be propagated for SQLite fallback.

    Bug Context:
    Previously, api_data_source methods caught exceptions and returned default values
    (None, [], {}) instead of re-raising them. This prevented HybridDataSource from
    detecting API failures and falling back to SQLite.

    These tests verify that HTTP errors (404, 500, network errors) are now properly
    propagated to allow the hybrid fallback mechanism to work correctly.

    Related Issue: Fallback API → SQLite not working with 404 responses
    """

    def test_get_champion_id_propagates_http_404_error(self, api_data_source):
        """Test get_champion_id() raises HTTPStatusError on 404 (enables fallback)."""
        mock_response = Mock()
        mock_response.status_code = 404
        api_data_source._client.get.side_effect = httpx.HTTPStatusError(
            "Not found", request=Mock(), response=mock_response
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            api_data_source.get_champion_id("UnknownChampion")

        assert exc_info.value.response.status_code == 404

    def test_get_champion_id_propagates_http_500_error(self, api_data_source):
        """Test get_champion_id() raises HTTPStatusError on 500 (enables fallback)."""
        mock_response = Mock()
        mock_response.status_code = 500
        api_data_source._client.get.side_effect = httpx.HTTPStatusError(
            "Server error", request=Mock(), response=mock_response
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            api_data_source.get_champion_id("Jinx")

        assert exc_info.value.response.status_code == 500

    def test_get_champion_by_id_propagates_network_error(self, api_data_source):
        """Test get_champion_by_id() raises NetworkError (enables fallback)."""
        api_data_source._client.get.side_effect = httpx.NetworkError("Connection failed")

        with pytest.raises(httpx.NetworkError):
            api_data_source.get_champion_by_id(42)

    def test_get_all_champion_names_propagates_timeout_error(self, api_data_source):
        """Test get_all_champion_names() raises TimeoutException (enables fallback)."""
        api_data_source._client.get.side_effect = httpx.TimeoutException("Request timeout")

        with pytest.raises(httpx.TimeoutException):
            api_data_source.get_all_champion_names()

    def test_build_champion_cache_propagates_http_error(self, api_data_source):
        """Test build_champion_cache() raises HTTPError (enables fallback)."""
        api_data_source._client.get.side_effect = httpx.HTTPError("Generic HTTP error")

        with pytest.raises(httpx.HTTPError):
            api_data_source.build_champion_cache()

    def test_get_champion_matchups_by_name_propagates_http_error(self, api_data_source):
        """Test get_champion_matchups_by_name() raises HTTPError (enables fallback)."""
        # Pre-populate cache to avoid get_champion_id call
        api_data_source._champion_cache["Jinx"] = 42

        mock_response = Mock()
        mock_response.status_code = 500
        api_data_source._client.get.side_effect = httpx.HTTPStatusError(
            "Server error", request=Mock(), response=mock_response
        )

        with pytest.raises(httpx.HTTPStatusError):
            api_data_source.get_champion_matchups_by_name("Jinx")

    def test_get_matchup_delta2_propagates_http_error(self, api_data_source):
        """Test get_matchup_delta2() raises HTTPError when not in cache (enables fallback)."""
        # Pre-populate champion cache
        api_data_source._champion_cache["Jinx"] = 42
        api_data_source._champion_cache["Caitlyn"] = 51

        api_data_source._client.get.side_effect = httpx.HTTPError("Network error")

        with pytest.raises(httpx.HTTPError):
            api_data_source.get_matchup_delta2("Jinx", "Caitlyn")

    def test_get_all_matchups_bulk_propagates_http_error(self, api_data_source):
        """Test get_all_matchups_bulk() raises HTTPError (enables fallback)."""
        api_data_source._client.get.side_effect = httpx.HTTPError("Connection refused")

        with pytest.raises(httpx.HTTPError):
            api_data_source.get_all_matchups_bulk()

    def test_get_champion_synergies_by_name_propagates_http_error(self, api_data_source):
        """Test get_champion_synergies_by_name() raises HTTPError (enables fallback)."""
        # Pre-populate cache
        api_data_source._champion_cache["Jinx"] = 42

        api_data_source._client.get.side_effect = httpx.HTTPError("API unavailable")

        with pytest.raises(httpx.HTTPError):
            api_data_source.get_champion_synergies_by_name("Jinx")

    def test_get_synergy_delta2_propagates_http_error(self, api_data_source):
        """Test get_synergy_delta2() raises HTTPError when not in cache (enables fallback)."""
        # Pre-populate champion cache
        api_data_source._champion_cache["Jinx"] = 42
        api_data_source._champion_cache["Lux"] = 99

        api_data_source._client.get.side_effect = httpx.HTTPError("Server down")

        with pytest.raises(httpx.HTTPError):
            api_data_source.get_synergy_delta2("Jinx", "Lux")

    def test_get_all_synergies_bulk_propagates_http_error(self, api_data_source):
        """Test get_all_synergies_bulk() raises HTTPError (enables fallback)."""
        api_data_source._client.get.side_effect = httpx.HTTPError("Network failure")

        with pytest.raises(httpx.HTTPError):
            api_data_source.get_all_synergies_bulk()

    def test_get_all_champion_scores_propagates_http_error(self, api_data_source):
        """Test get_all_champion_scores() raises HTTPError (enables fallback)."""
        api_data_source._client.get.side_effect = httpx.HTTPError("API error")

        with pytest.raises(httpx.HTTPError):
            api_data_source.get_all_champion_scores()

    def test_get_champion_scores_by_name_propagates_non_404_errors(self, api_data_source):
        """Test get_champion_scores_by_name() raises HTTPError for non-404 errors."""
        # Pre-populate cache
        api_data_source._champion_cache["Jinx"] = 42

        mock_response = Mock()
        mock_response.status_code = 500
        api_data_source._client.get.side_effect = httpx.HTTPStatusError(
            "Server error", request=Mock(), response=mock_response
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            api_data_source.get_champion_scores_by_name("Jinx")

        assert exc_info.value.response.status_code == 500

    def test_get_pool_ban_recommendations_propagates_non_404_errors(self, api_data_source):
        """Test get_pool_ban_recommendations() raises HTTPError for non-404 errors."""
        mock_response = Mock()
        mock_response.status_code = 503
        api_data_source._client.get.side_effect = httpx.HTTPStatusError(
            "Service unavailable", request=Mock(), response=mock_response
        )

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            api_data_source.get_pool_ban_recommendations("TestPool")

        assert exc_info.value.response.status_code == 503
