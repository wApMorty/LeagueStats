"""
Regression test for bug: API response format parsing (KeyError).

Bug Context:
The FastAPI backend returns wrapped responses with format {"champions": [...], "count": N},
but the client code was trying to access data[0] directly, causing KeyError(0).

Root Cause:
- API returns: {"champions": [{"id": 516, "name": "Malphite"}], "count": 1}
- Client expected: [{"id": 516, "name": "Malphite"}]
- Client code did: data[0]["id"] → KeyError(0) because data is a dict with keys "champions" and "count"

Fix:
Extract the wrapped list/dict from response.json() before processing:
- data = response.json()
- champions = data.get("champions", [])  # Extract wrapped list
- Then process champions list

Related Issue: KeyError(0) in get_champion_id() and other API methods
Created: 2026-02-07
"""

import pytest
from unittest.mock import Mock, patch

from src.api_data_source import APIDataSource


@pytest.fixture
def api_data_source():
    """Create APIDataSource with mocked HTTP client."""
    with patch("src.api_data_source.httpx.Client") as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client

        data_source = APIDataSource(base_url="https://test-api.example.com", timeout=5)
        # Skip cache warmup
        with patch.object(data_source, "_warm_up_caches"):
            data_source.connect()

        yield data_source


class TestBugAPIResponseFormatChampions:
    """Test that champions endpoints parse wrapped responses correctly."""

    def test_get_champion_id_parses_wrapped_response(self, api_data_source):
        """
        Bug: get_champion_id() failed with KeyError(0) on wrapped API response.

        Before fix: data[0]["id"] → KeyError(0)
        After fix: data.get("champions", [])[0]["id"] → Works correctly
        """
        # Mock API response with CORRECT wrapped format
        mock_response = Mock()
        mock_response.json.return_value = {
            "champions": [{"id": 516, "name": "Malphite", "riot_id": "malphite"}],
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        # Should extract champion ID from wrapped response
        champion_id = api_data_source.get_champion_id("Malphite")

        assert champion_id == 516

    def test_get_champion_id_filters_by_name_client_side(self, api_data_source):
        """
        Bug: API doesn't support name query parameter, must filter client-side.

        API returns all champions, client must filter by name (case-insensitive).
        """
        # Mock API response with multiple champions
        mock_response = Mock()
        mock_response.json.return_value = {
            "champions": [
                {"id": 1, "name": "Aatrox", "riot_id": "aatrox"},
                {"id": 516, "name": "Malphite", "riot_id": "malphite"},
                {"id": 777, "name": "Zed", "riot_id": "zed"},
            ],
            "count": 3,
        }
        api_data_source._client.get.return_value = mock_response

        # Should filter by name (case-insensitive)
        champion_id = api_data_source.get_champion_id("malphite")

        assert champion_id == 516

    def test_get_champion_id_returns_none_when_not_found(self, api_data_source):
        """Test get_champion_id() returns None when champion not in wrapped response."""
        # Mock API response with champions that don't match
        mock_response = Mock()
        mock_response.json.return_value = {
            "champions": [{"id": 1, "name": "Aatrox", "riot_id": "aatrox"}],
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        # Should return None when champion not found
        champion_id = api_data_source.get_champion_id("InvalidChampion")

        assert champion_id is None

    def test_get_all_champion_names_parses_wrapped_response(self, api_data_source):
        """
        Bug: get_all_champion_names() failed to extract wrapped champions list.

        Before fix: for champ in data → Iterates over dict keys ("champions", "count")
        After fix: champions = data.get("champions", []) → Iterates over champion objects
        """
        # Mock API response with wrapped format
        mock_response = Mock()
        mock_response.json.return_value = {
            "champions": [
                {"id": 1, "name": "Aatrox", "riot_id": "aatrox"},
                {"id": 516, "name": "Malphite", "riot_id": "malphite"},
            ],
            "count": 2,
        }
        api_data_source._client.get.return_value = mock_response

        # Should extract champions from wrapped response
        names = api_data_source.get_all_champion_names()

        assert names == {1: "Aatrox", 516: "Malphite"}

    def test_build_champion_cache_parses_wrapped_response(self, api_data_source):
        """
        Bug: build_champion_cache() failed to extract wrapped champions list.

        Before fix: for champ in data → KeyError on champ["name"]
        After fix: champions = data.get("champions", []) → Correct iteration
        """
        # Mock API response with wrapped format
        mock_response = Mock()
        mock_response.json.return_value = {
            "champions": [
                {"id": 1, "name": "Aatrox", "riot_id": "aatrox"},
                {"id": 516, "name": "Malphite", "riot_id": "malphite"},
            ],
            "count": 2,
        }
        api_data_source._client.get.return_value = mock_response

        # Should build cache from wrapped response
        cache = api_data_source.build_champion_cache()

        assert "Aatrox" in cache
        assert "aatrox" in cache  # Lowercase variant
        assert cache["Malphite"] == 516
        assert cache["malphite"] == 516


class TestBugAPIResponseFormatMatchups:
    """Test that matchup endpoints parse wrapped responses correctly."""

    def test_get_champion_matchups_by_name_parses_wrapped_response(self, api_data_source):
        """
        Bug: get_champion_matchups_by_name() failed to extract wrapped matchups list.

        API returns: {"champion_id": 1, "champion_name": "Aatrox", "matchups": [...], "count": N}
        Before fix: for m in matchups → Assumed matchups is list
        After fix: matchups = data.get("matchups", []) → Extract from wrapper
        """
        # Pre-populate cache to avoid champion lookup
        api_data_source._champion_cache = {"aatrox": 1, "Aatrox": 1}

        # Mock API response with wrapped format
        mock_response = Mock()
        mock_response.json.return_value = {
            "champion_id": 1,
            "champion_name": "Aatrox",
            "matchups": [
                {
                    "enemy_id": 2,
                    "enemy_name": "Darius",
                    "winrate": 48.5,
                    "games": 1500,
                    "delta2": -200.0,
                    "pickrate": 8.5,
                    "delta1": -150.0,
                }
            ],
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        # Should extract matchups from wrapped response
        matchups = api_data_source.get_champion_matchups_by_name("Aatrox")

        assert len(matchups) == 1
        assert matchups[0].enemy_name == "Darius"

    def test_get_champion_matchups_for_draft_parses_wrapped_response(self, api_data_source):
        """Test get_champion_matchups_for_draft() extracts matchups from wrapped response."""
        api_data_source._champion_cache = {"aatrox": 1, "Aatrox": 1}

        mock_response = Mock()
        mock_response.json.return_value = {
            "champion_id": 1,
            "champion_name": "Aatrox",
            "matchups": [
                {
                    "enemy_id": 2,
                    "enemy_name": "Darius",
                    "winrate": 48.5,
                    "games": 1500,
                    "delta2": -200.0,
                    "pickrate": 8.5,
                    "delta1": -150.0,
                }
            ],
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        # Should extract matchups from wrapped response
        matchups = api_data_source.get_champion_matchups_for_draft("Aatrox")

        assert len(matchups) == 1
        assert matchups[0].delta2 == -200.0

    def test_get_all_matchups_bulk_parses_wrapped_dict(self, api_data_source):
        """
        Bug: get_all_matchups_bulk() failed to extract wrapped matchups dict.

        API returns: {"matchups": {"1": [MatchupResponse, ...], "2": [...]}, "count": N}
        Before fix: Assumed flat list of matchups with champion_name
        After fix: Extract matchups dict and iterate with champion_id keys
        """
        # Pre-populate champion cache for ID->name lookup
        api_data_source._champion_cache = {
            "Aatrox": 1,
            "aatrox": 1,
            "Darius": 2,
            "darius": 2,
        }

        # Mock API response with wrapped dict format
        mock_response = Mock()
        mock_response.json.return_value = {
            "matchups": {
                "1": [  # Aatrox matchups
                    {
                        "enemy_id": 2,
                        "enemy_name": "Darius",
                        "winrate": 48.5,
                        "games": 1500,
                        "delta2": -200.0,
                        "pickrate": 8.5,
                        "delta1": -150.0,
                    }
                ]
            },
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        # Should extract matchups from wrapped dict
        matchups_bulk = api_data_source.get_all_matchups_bulk()

        assert ("aatrox", "darius") in matchups_bulk
        assert matchups_bulk[("aatrox", "darius")] == -200.0


class TestBugAPIResponseFormatSynergies:
    """Test that synergy endpoints parse wrapped responses correctly."""

    def test_get_champion_synergies_by_name_parses_wrapped_response(self, api_data_source):
        """
        Bug: get_champion_synergies_by_name() failed to extract wrapped synergies list.

        API returns: {"champion_id": 42, "champion_name": "Yasuo", "synergies": [...], "count": N}
        Before fix: for s in synergies → Assumed synergies is list
        After fix: synergies = data.get("synergies", []) → Extract from wrapper
        """
        api_data_source._champion_cache = {"yasuo": 42, "Yasuo": 42}

        mock_response = Mock()
        mock_response.json.return_value = {
            "champion_id": 42,
            "champion_name": "Yasuo",
            "synergies": [
                {
                    "ally_id": 516,
                    "ally_name": "Malphite",
                    "winrate": 55.0,
                    "games": 1000,
                    "delta2": 250.0,
                    "pickrate": 8.5,
                }
            ],
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        # Should extract synergies from wrapped response
        synergies = api_data_source.get_champion_synergies_by_name("Yasuo")

        assert len(synergies) == 1
        assert synergies[0].ally_name == "Malphite"

    def test_get_all_synergies_bulk_parses_wrapped_dict(self, api_data_source):
        """
        Bug: get_all_synergies_bulk() failed to extract wrapped synergies dict.

        API returns: {"synergies": {"42": [SynergyResponse, ...], "516": [...]}, "count": N}
        Before fix: Assumed flat list of synergies with champion_name
        After fix: Extract synergies dict and iterate with champion_id keys
        """
        # Pre-populate champion cache
        api_data_source._champion_cache = {
            "Yasuo": 42,
            "yasuo": 42,
            "Malphite": 516,
            "malphite": 516,
        }

        mock_response = Mock()
        mock_response.json.return_value = {
            "synergies": {
                "42": [  # Yasuo synergies
                    {
                        "ally_id": 516,
                        "ally_name": "Malphite",
                        "winrate": 55.0,
                        "games": 1000,
                        "delta2": 250.0,
                        "pickrate": 8.5,
                    }
                ]
            },
            "count": 1,
        }
        api_data_source._client.get.return_value = mock_response

        # Should extract synergies from wrapped dict
        synergies_bulk = api_data_source.get_all_synergies_bulk()

        assert ("yasuo", "malphite") in synergies_bulk
        assert synergies_bulk[("yasuo", "malphite")] == 250.0


class TestBugAPIResponseFormatEmptyDatabase:
    """Test that empty API responses (empty database) are handled gracefully."""

    def test_get_champion_id_handles_empty_database(self, api_data_source):
        """Test get_champion_id() returns None when database is empty."""
        # Mock API response with empty champions list (database empty)
        mock_response = Mock()
        mock_response.json.return_value = {"champions": [], "count": 0}
        api_data_source._client.get.return_value = mock_response

        champion_id = api_data_source.get_champion_id("Malphite")

        assert champion_id is None

    def test_build_champion_cache_handles_empty_database(self, api_data_source):
        """Test build_champion_cache() returns empty dict when database is empty."""
        mock_response = Mock()
        mock_response.json.return_value = {"champions": [], "count": 0}
        api_data_source._client.get.return_value = mock_response

        cache = api_data_source.build_champion_cache()

        assert cache == {}

    def test_get_all_matchups_bulk_handles_empty_database(self, api_data_source):
        """Test get_all_matchups_bulk() returns empty dict when database is empty."""
        mock_response = Mock()
        mock_response.json.return_value = {"matchups": {}, "count": 0}
        api_data_source._client.get.return_value = mock_response

        matchups_bulk = api_data_source.get_all_matchups_bulk()

        assert matchups_bulk == {}
