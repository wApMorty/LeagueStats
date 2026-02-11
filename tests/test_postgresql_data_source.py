"""Unit tests for src/postgresql_data_source.py with Database class mocking.

Tests delegation to server.src.db.Database and READ-ONLY enforcement.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

from src.postgresql_data_source import PostgreSQLDataSource


@pytest.fixture
def mock_database():
    """Mock Database class for testing delegation."""
    with patch("src.postgresql_data_source.Database") as MockDatabase:
        mock_db_instance = Mock()
        MockDatabase.return_value = mock_db_instance
        yield mock_db_instance


@pytest.fixture
def mock_deobfuscate():
    """Mock credentials.deobfuscate to avoid real connection string."""
    with patch("src.postgresql_data_source.deobfuscate") as mock_deobfuscate:
        mock_deobfuscate.return_value = "postgresql://test:test@localhost:5432/test"
        yield mock_deobfuscate


def test_init_deobfuscates_connection_string(mock_database, mock_deobfuscate):
    """Test that __init__ deobfuscates connection string."""
    ds = PostgreSQLDataSource()

    # Verify deobfuscate was called
    mock_deobfuscate.assert_called_once()

    # Verify Database was instantiated with deobfuscated string
    assert ds._db is not None


def test_get_champion_id_delegates_to_database(mock_database, mock_deobfuscate):
    """Test get_champion_id delegates to Database."""
    mock_database.get_champion_id.return_value = 1

    ds = PostgreSQLDataSource()
    result = ds.get_champion_id("Aatrox")

    mock_database.get_champion_id.assert_called_once_with("Aatrox")
    assert result == 1


def test_get_all_matchups_bulk_delegates(mock_database, mock_deobfuscate):
    """Test get_all_matchups_bulk delegates to Database."""
    mock_data = [("Aatrox", "Ahri", 52.5, 100, 1.2, 3.5)]
    mock_database.get_all_matchups_bulk.return_value = mock_data

    ds = PostgreSQLDataSource()
    result = ds.get_all_matchups_bulk()

    mock_database.get_all_matchups_bulk.assert_called_once()
    assert result == mock_data


def test_get_champion_matchups_by_name_delegates(mock_database, mock_deobfuscate):
    """Test get_champion_matchups_by_name delegates to Database."""
    mock_matchups = [("Ahri", 52.5, 100, 1.2, 3.5)]
    mock_database.get_champion_matchups_by_name.return_value = mock_matchups

    ds = PostgreSQLDataSource()
    result = ds.get_champion_matchups_by_name("Aatrox")

    # PostgreSQLDataSource calls with as_dataclass=True by default
    mock_database.get_champion_matchups_by_name.assert_called_once_with("Aatrox", True)
    assert result == mock_matchups


def test_save_champion_scores_raises_not_implemented(mock_database, mock_deobfuscate):
    """Test save_champion_scores raises NotImplementedError (READ-ONLY)."""
    ds = PostgreSQLDataSource()

    with pytest.raises(NotImplementedError, match="READ-ONLY"):
        ds.save_champion_scores(1, 50.0, 2.5, 100, 8.0, 1.2, 0.5)


def test_save_pool_ban_recommendations_raises_not_implemented(mock_database, mock_deobfuscate):
    """Test save_pool_ban_recommendations raises NotImplementedError (READ-ONLY)."""
    ds = PostgreSQLDataSource()

    with pytest.raises(NotImplementedError, match="READ-ONLY"):
        ds.save_pool_ban_recommendations("my_pool", [])


def test_connect_is_noop(mock_database, mock_deobfuscate):
    """Test connect() is a no-op (Database handles connection pooling)."""
    ds = PostgreSQLDataSource()
    ds.connect()  # Should not raise, should do nothing


def test_close_is_noop(mock_database, mock_deobfuscate):
    """Test close() is a no-op (Database handles connection pooling)."""
    ds = PostgreSQLDataSource()
    ds.close()  # Should not raise, should do nothing


def test_build_champion_cache_converts_list_to_dict(mock_database, mock_deobfuscate):
    """Test build_champion_cache converts Database output to expected format."""
    # Database.get_all_champions() returns List[(id, name)]
    mock_database.get_all_champions.return_value = [
        (1, "Aatrox"),
        (2, "Ahri"),
        (3, "Akali"),
    ]

    ds = PostgreSQLDataSource()
    result = ds.build_champion_cache()

    # Expected format: {name: id, lowercase_name: id}
    assert "Aatrox" in result
    assert "aatrox" in result
    assert result["Aatrox"] == 1
    assert result["aatrox"] == 1


def test_get_champion_base_winrate_returns_50_fallback(mock_database, mock_deobfuscate):
    """Test get_champion_base_winrate returns 50.0 fallback (Database lacks this method)."""
    ds = PostgreSQLDataSource()
    result = ds.get_champion_base_winrate("Aatrox")

    # Should return 50.0 fallback (Database doesn't have this method)
    assert result == 50.0


def test_pool_has_ban_recommendations_returns_false(mock_database, mock_deobfuscate):
    """Test pool_has_ban_recommendations returns False (Database lacks ban table)."""
    ds = PostgreSQLDataSource()
    result = ds.pool_has_ban_recommendations("my_pool")

    # Should return False (Database doesn't have ban_recommendations table)
    assert result is False


def test_get_all_champion_names_converts_to_dict(mock_database, mock_deobfuscate):
    """Test get_all_champion_names converts Database output to {id: name} dict."""
    mock_database.get_all_champions.return_value = [
        (1, "Aatrox"),
        (2, "Ahri"),
    ]

    ds = PostgreSQLDataSource()
    result = ds.get_all_champion_names()

    # Expected format: {id: name}
    assert result == {1: "Aatrox", 2: "Ahri"}
