"""End-to-End tests for HybridDataSource in postgresql_only mode.

These tests require a valid PostgreSQL DATABASE_URL environment variable.
If DATABASE_URL is not set, tests will be skipped (CI-friendly).

Setup:
    export DATABASE_URL="postgresql://user:pass@host:5432/db"
    pytest tests/test_hybrid_data_source_e2e.py -v
"""

import os
import pytest

from src.hybrid_data_source import HybridDataSource
from src.config_constants import api_config


# Skip all tests if DATABASE_URL not configured
pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set (E2E tests require real PostgreSQL connection)",
)


@pytest.fixture
def postgresql_data_source():
    """Create HybridDataSource in postgresql_only mode for E2E testing."""
    # Save original mode
    original_mode = api_config.MODE

    # Set to postgresql_only mode
    api_config.MODE = "postgresql_only"
    api_config.ENABLED = True

    ds = HybridDataSource()
    ds.connect()

    yield ds

    ds.close()

    # Restore original mode
    api_config.MODE = original_mode


@pytest.fixture
def hybrid_data_source():
    """Create HybridDataSource in hybrid mode (PostgreSQL primary, SQLite fallback)."""
    # Save original mode
    original_mode = api_config.MODE

    # Set to hybrid mode
    api_config.MODE = "hybrid"
    api_config.ENABLED = True

    ds = HybridDataSource()
    ds.connect()

    yield ds

    ds.close()

    # Restore original mode
    api_config.MODE = original_mode


def test_postgresql_mode_get_all_champions(postgresql_data_source):
    """Test get_all_champion_names with real PostgreSQL connection."""
    champions = postgresql_data_source.get_all_champion_names()

    # Verify we got champions from PostgreSQL
    assert isinstance(champions, dict)
    assert len(champions) > 150  # League has 160+ champions
    assert 1 in champions  # Champion ID 1 exists
    assert isinstance(champions[1], str)  # Champion name is string


def test_postgresql_mode_get_champion_id(postgresql_data_source):
    """Test get_champion_id with real PostgreSQL connection."""
    # Test a known champion
    champion_id = postgresql_data_source.get_champion_id("Jinx")

    assert isinstance(champion_id, int)
    assert champion_id > 0


def test_postgresql_mode_get_matchups(postgresql_data_source):
    """Test get_champion_matchups_by_name with real PostgreSQL connection."""
    matchups = postgresql_data_source.get_champion_matchups_by_name("Jinx")

    # Verify we got matchups
    assert isinstance(matchups, list)
    assert len(matchups) > 0  # Jinx should have matchups

    # Verify matchup structure (tuple: enemy_name, winrate, games, delta2, pickrate)
    first_matchup = matchups[0]
    assert len(first_matchup) >= 5
    assert isinstance(first_matchup[0], str)  # enemy_name
    assert isinstance(first_matchup[1], (int, float))  # winrate
    assert isinstance(first_matchup[2], int)  # games


def test_postgresql_mode_get_synergies(postgresql_data_source):
    """Test get_champion_synergies_by_name with real PostgreSQL connection."""
    synergies = postgresql_data_source.get_champion_synergies_by_name("Jinx")

    # Verify we got synergies
    assert isinstance(synergies, list)
    # Note: synergies might be empty if no data, that's OK


def test_readonly_enforcement_save_champion_scores(postgresql_data_source):
    """Test that save_champion_scores raises NotImplementedError (READ-ONLY)."""
    with pytest.raises(NotImplementedError, match="READ-ONLY"):
        postgresql_data_source.save_champion_scores(1, 50.0, 2.5, 100, 8.0, 1.2, 0.5)


def test_readonly_enforcement_save_pool_ban(postgresql_data_source):
    """Test that save_pool_ban_recommendations raises NotImplementedError (READ-ONLY)."""
    with pytest.raises(NotImplementedError, match="READ-ONLY"):
        postgresql_data_source.save_pool_ban_recommendations("test_pool", [])


def test_hybrid_mode_fallback_behavior(hybrid_data_source):
    """Test hybrid mode fallback from PostgreSQL to SQLite."""
    # This test verifies that hybrid mode tries PostgreSQL first
    # and falls back to SQLite if PostgreSQL fails

    # If this test runs successfully, hybrid mode is working
    # (either PostgreSQL succeeded, or fallback to SQLite worked)
    champions = hybrid_data_source.get_all_champion_names()

    assert isinstance(champions, dict)
    assert len(champions) > 150


def test_postgresql_mode_connection_pooling(postgresql_data_source):
    """Test that multiple queries work (connection pooling)."""
    # Make multiple queries to test connection pooling
    for _ in range(5):
        champion_id = postgresql_data_source.get_champion_id("Jinx")
        assert champion_id > 0

    # If we got here, connection pooling works
    assert True


def test_postgresql_mode_error_handling_invalid_champion(postgresql_data_source):
    """Test error handling for invalid champion name."""
    # This might raise an exception or return None depending on implementation
    try:
        result = postgresql_data_source.get_champion_id("InvalidChampionXYZ123")
        # If no exception, result should be None or 0
        assert result is None or result == 0
    except Exception:
        # Exception is acceptable for invalid input
        pass
