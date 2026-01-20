"""API endpoint tests."""

import pytest
from fastapi import status


# ========== Health Check Tests ==========


def test_health_check_returns_200(client):
    """Test health endpoint returns 200 status."""
    response = client.get("/health")
    assert response.status_code == status.HTTP_200_OK


def test_health_check_response_format(client):
    """Test health endpoint returns correct format."""
    response = client.get("/health")
    data = response.json()

    assert "status" in data
    assert "version" in data
    assert "database" in data
    assert "timestamp" in data

    assert data["status"] == "ok"
    assert data["database"] == "connected"


# ========== Champions Endpoints Tests ==========


def test_get_all_champions_returns_200(client):
    """Test GET /api/champions returns 200."""
    response = client.get("/api/champions")
    assert response.status_code == status.HTTP_200_OK


def test_get_all_champions_returns_172_champions(client):
    """Test GET /api/champions returns 172 champions."""
    response = client.get("/api/champions")
    data = response.json()

    assert "champions" in data
    assert "count" in data
    assert data["count"] == 172
    assert len(data["champions"]) == 172


def test_get_all_champions_format(client):
    """Test GET /api/champions returns correct format."""
    response = client.get("/api/champions")
    data = response.json()

    # Check first champion has correct structure
    first_champion = data["champions"][0]
    assert "id" in first_champion
    assert "name" in first_champion
    assert "riot_id" in first_champion

    assert isinstance(first_champion["id"], int)
    assert isinstance(first_champion["name"], str)


def test_get_champion_by_id_exists(client):
    """Test GET /api/champions/{id} for existing champion."""
    # Champion ID 1 should be Annie
    response = client.get("/api/champions/1")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == 1
    assert data["name"] == "Annie"
    assert "riot_id" in data


def test_get_champion_by_id_not_found(client):
    """Test GET /api/champions/{id} returns 404 for non-existent champion."""
    response = client.get("/api/champions/99999")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ========== Matchup Endpoints Tests ==========


def test_get_champion_matchups_returns_200(client):
    """Test GET /api/champions/{id}/matchups returns 200."""
    # Test with Aatrox (id=266)
    response = client.get("/api/champions/266/matchups")
    assert response.status_code == status.HTTP_200_OK


def test_get_champion_matchups_format(client):
    """Test matchups endpoint returns correct format."""
    response = client.get("/api/champions/266/matchups")
    data = response.json()

    assert "champion_id" in data
    assert "champion_name" in data
    assert "matchups" in data
    assert "count" in data

    assert data["champion_id"] == 266
    assert isinstance(data["matchups"], list)
    assert data["count"] > 100  # Should have many matchups

    # Check matchup structure
    if data["matchups"]:
        matchup = data["matchups"][0]
        assert "enemy_id" in matchup
        assert "enemy_name" in matchup
        assert "winrate" in matchup
        assert "games" in matchup
        assert "delta2" in matchup


def test_get_champion_matchups_not_found(client):
    """Test matchups returns 404 for non-existent champion."""
    response = client.get("/api/champions/99999/matchups")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_bulk_matchups_returns_200(client):
    """Test GET /api/matchups/bulk returns 200."""
    response = client.get("/api/matchups/bulk")
    assert response.status_code == status.HTTP_200_OK


def test_get_bulk_matchups_format(client):
    """Test bulk matchups returns dict with 172 keys."""
    response = client.get("/api/matchups/bulk")
    data = response.json()

    assert "matchups" in data
    assert "count" in data
    assert data["count"] == 172
    assert len(data["matchups"]) == 172

    # Check each champion has matchups
    for champion_id, matchups_list in data["matchups"].items():
        assert isinstance(matchups_list, list)
        assert len(matchups_list) > 0


# ========== Synergy Endpoints Tests ==========


def test_get_champion_synergies_returns_200(client):
    """Test GET /api/champions/{id}/synergies returns 200."""
    response = client.get("/api/champions/266/synergies")
    assert response.status_code == status.HTTP_200_OK


def test_get_champion_synergies_format(client):
    """Test synergies endpoint returns correct format."""
    response = client.get("/api/champions/266/synergies")
    data = response.json()

    assert "champion_id" in data
    assert "champion_name" in data
    assert "synergies" in data
    assert "count" in data

    assert data["champion_id"] == 266
    assert isinstance(data["synergies"], list)
    assert data["count"] > 100  # Should have many synergies

    # Check synergy structure
    if data["synergies"]:
        synergy = data["synergies"][0]
        assert "ally_id" in synergy
        assert "ally_name" in synergy
        assert "winrate" in synergy
        assert "games" in synergy
        assert "delta2" in synergy


def test_get_champion_synergies_not_found(client):
    """Test synergies returns 404 for non-existent champion."""
    response = client.get("/api/champions/99999/synergies")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_get_bulk_synergies_returns_200(client):
    """Test GET /api/synergies/bulk returns 200."""
    response = client.get("/api/synergies/bulk")
    assert response.status_code == status.HTTP_200_OK


def test_get_bulk_synergies_format(client):
    """Test bulk synergies returns dict with 172 keys."""
    response = client.get("/api/synergies/bulk")
    data = response.json()

    assert "synergies" in data
    assert "count" in data
    assert data["count"] == 172
    assert len(data["synergies"]) == 172

    # Check each champion has synergies
    for champion_id, synergies_list in data["synergies"].items():
        assert isinstance(synergies_list, list)
        assert len(synergies_list) > 0


# ========== Tier List Endpoint Tests ==========


def test_get_tier_list_returns_200(client):
    """Test GET /api/tier-list with valid params returns 200."""
    response = client.get("/api/tier-list?pool=TOP&type=blind")
    assert response.status_code == status.HTTP_200_OK


def test_get_tier_list_format(client):
    """Test tier list returns correct format."""
    response = client.get("/api/tier-list?pool=TOP&type=blind")
    data = response.json()

    assert "pool" in data
    assert "type" in data
    assert "tier_list" in data
    assert "generated_at" in data

    assert data["pool"] == "TOP"
    assert data["type"] == "blind"
    assert isinstance(data["tier_list"], list)
    assert len(data["tier_list"]) > 0

    # Check tier list entry structure
    entry = data["tier_list"][0]
    assert "id" in entry
    assert "name" in entry
    assert "score" in entry
    assert "tier" in entry
    assert entry["tier"] in ["S", "A", "B", "C"]


def test_get_tier_list_all_pools(client):
    """Test tier list works for all valid pools."""
    pools = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]

    for pool in pools:
        response = client.get(f"/api/tier-list?pool={pool}&type=blind")
        assert response.status_code == status.HTTP_200_OK, f"Failed for pool: {pool}"

        data = response.json()
        assert data["pool"] == pool


def test_get_tier_list_invalid_pool(client):
    """Test tier list returns 400 for invalid pool."""
    response = client.get("/api/tier-list?pool=INVALID&type=blind")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_tier_list_invalid_type(client):
    """Test tier list returns 400 for invalid type."""
    response = client.get("/api/tier-list?pool=TOP&type=invalid")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_get_tier_list_counter_type(client):
    """Test tier list works with counter type."""
    response = client.get("/api/tier-list?pool=TOP&type=counter")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["type"] == "counter"


# ========== Team Analysis Endpoint Tests ==========


def test_analyze_team_returns_200(client):
    """Test POST /api/analyze-team with valid data returns 200."""
    payload = {"champion_ids": [1, 2, 3]}
    response = client.post("/api/analyze-team", json=payload)
    assert response.status_code == status.HTTP_200_OK


def test_analyze_team_format(client):
    """Test team analysis returns correct format."""
    payload = {"champion_ids": [1, 2, 3]}
    response = client.post("/api/analyze-team", json=payload)
    data = response.json()

    assert "champions" in data
    assert "matchup_score" in data
    assert "synergy_score" in data
    assert "holistic_score" in data
    assert "synergy_details" in data
    assert "recommendations" in data

    assert len(data["champions"]) == 3
    assert isinstance(data["matchup_score"], float)
    assert isinstance(data["synergy_score"], float)
    assert isinstance(data["holistic_score"], float)
    assert isinstance(data["synergy_details"], list)
    assert isinstance(data["recommendations"], list)


def test_analyze_team_single_champion(client):
    """Test team analysis with single champion."""
    payload = {"champion_ids": [1]}
    response = client.post("/api/analyze-team", json=payload)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert len(data["champions"]) == 1


def test_analyze_team_five_champions(client):
    """Test team analysis with five champions."""
    payload = {"champion_ids": [1, 2, 3, 4, 5]}
    response = client.post("/api/analyze-team", json=payload)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert len(data["champions"]) == 5


def test_analyze_team_invalid_champion(client):
    """Test team analysis returns 404 for invalid champion ID."""
    payload = {"champion_ids": [99999]}
    response = client.post("/api/analyze-team", json=payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ========== Ban Recommendations Endpoint Tests ==========


def test_ban_recommendations_returns_200(client):
    """Test GET /api/ban-recommendations with valid pool returns 200."""
    response = client.get("/api/ban-recommendations?pool=TOP")
    assert response.status_code == status.HTTP_200_OK


def test_ban_recommendations_format(client):
    """Test ban recommendations returns correct format."""
    response = client.get("/api/ban-recommendations?pool=TOP")
    data = response.json()

    assert "pool" in data
    assert "recommendations" in data
    assert "count" in data

    assert data["pool"] == "TOP"
    assert isinstance(data["recommendations"], list)
    assert len(data["recommendations"]) > 0
    assert data["count"] == len(data["recommendations"])

    # Check recommendation structure
    recommendation = data["recommendations"][0]
    assert "champion_id" in recommendation
    assert "champion_name" in recommendation
    assert "ban_score" in recommendation
    assert "reason" in recommendation


def test_ban_recommendations_all_pools(client):
    """Test ban recommendations works for all valid pools."""
    pools = ["TOP", "JUNGLE", "MID", "ADC", "SUPPORT"]

    for pool in pools:
        response = client.get(f"/api/ban-recommendations?pool={pool}")
        assert response.status_code == status.HTTP_200_OK, f"Failed for pool: {pool}"

        data = response.json()
        assert data["pool"] == pool
        assert len(data["recommendations"]) > 0


def test_ban_recommendations_invalid_pool(client):
    """Test ban recommendations returns 400 for invalid pool."""
    response = client.get("/api/ban-recommendations?pool=INVALID")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
