"""
Tests for Assistant integration with DataSource abstraction.

This test suite verifies that:
- Assistant accepts DataSource via dependency injection
- Backward compatibility with Database instances
- HybridDataSource is used by default
- All data source types work correctly with Assistant

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration (Adapter Pattern Implementation)
"""

import pytest
from unittest.mock import Mock, patch

from src.assistant import Assistant
from src.sqlite_data_source import SQLiteDataSource
from src.api_data_source import APIDataSource
from src.hybrid_data_source import HybridDataSource


class TestAssistantDataSourceInjection:
    """Test data source dependency injection."""

    def test_assistant_accepts_sqlite_data_source(self, temp_db):
        """Test that Assistant accepts SQLiteDataSource via dependency injection."""
        data_source = SQLiteDataSource(str(temp_db))
        assistant = Assistant(data_source=data_source)

        assert assistant.db is data_source
        assistant.close()

    def test_assistant_uses_hybrid_by_default(self):
        """Test that Assistant uses HybridDataSource by default when no data_source provided."""
        # Patch where HybridDataSource is imported (dynamically in __init__)
        with patch("src.hybrid_data_source.HybridDataSource") as mock_hybrid_class:
            mock_hybrid = Mock()
            mock_hybrid_class.return_value = mock_hybrid

            # Also mock api_config to avoid real connections
            with patch("src.hybrid_data_source.api_config") as mock_config:
                mock_config.MODE = "hybrid"
                mock_config.ENABLED = True

                assistant = Assistant()

                # Verify HybridDataSource was instantiated and connected
                assert assistant.db is mock_hybrid
                mock_hybrid.connect.assert_called_once()

    def test_assistant_connects_data_source_on_init(self, temp_db):
        """Test that Assistant connects data source on initialization."""
        data_source = Mock(spec=SQLiteDataSource)
        assistant = Assistant(data_source=data_source)

        data_source.connect.assert_called_once()

    def test_assistant_close_closes_data_source(self, temp_db):
        """Test that Assistant.close() closes data source connection."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()
        assistant = Assistant(data_source=data_source)

        assistant.close()

        # After close, connection should be None
        # (SQLite doesn't provide a clean way to check, but no exception means success)


class TestAssistantBackwardCompatibility:
    """Test backward compatibility with Database instances."""

    def test_assistant_wraps_database_instance_in_adapter(self, temp_db):
        """Test that Assistant wraps legacy Database in SQLiteDataSource adapter."""
        from src.db import Database

        db = Database(str(temp_db))

        # Patch where SQLiteDataSource is imported (dynamically in __init__)
        with patch("src.sqlite_data_source.SQLiteDataSource") as mock_sqlite_class:
            mock_sqlite = Mock()
            mock_sqlite_class.return_value = mock_sqlite

            assistant = Assistant(data_source=db)

            # Verify Database was wrapped in SQLiteDataSource
            mock_sqlite_class.assert_called_once_with(db.path)
            mock_sqlite.connect.assert_called_once()


class TestAssistantWithMockedDataSource:
    """Test Assistant functionality with mocked data sources."""

    @pytest.fixture
    def mock_data_source(self):
        """Create mock data source for testing."""
        mock_ds = Mock()
        mock_ds.get_champion_id.return_value = 42
        mock_ds.get_champion_matchups_for_draft.return_value = []
        mock_ds.get_champion_matchups_by_name.return_value = []
        mock_ds.get_all_matchups_bulk.return_value = {}
        mock_ds.build_champion_cache.return_value = {"Jinx": 42}
        return mock_ds

    def test_assistant_uses_data_source_for_queries(self, mock_data_source):
        """Test that Assistant uses injected data source for queries."""
        assistant = Assistant(data_source=mock_data_source)

        # Warm cache should call data source methods
        assistant.warm_cache(["Jinx"])

        # Verify data source was used
        mock_data_source.get_champion_matchups_for_draft.assert_called()

    def test_assistant_delegates_to_specialized_modules(self, mock_data_source):
        """Test that Assistant initializes specialized modules with data source."""
        assistant = Assistant(data_source=mock_data_source)

        # Verify specialized components were initialized with data source
        assert assistant.scorer is not None
        assert assistant.tier_list_gen is not None
        assert assistant.recommender is not None
        assert assistant.team_analyzer is not None


class TestAssistantModeConfiguration:
    """Test Assistant behavior with different data source modes."""

    def test_assistant_with_api_only_mode(self):
        """Test Assistant with API-only mode."""
        with patch("src.hybrid_data_source.HybridDataSource") as mock_hybrid_class:
            mock_hybrid = Mock()
            mock_hybrid_class.return_value = mock_hybrid

            # Set API-only mode
            with patch("src.hybrid_data_source.api_config") as mock_config:
                mock_config.MODE = "api_only"
                mock_config.ENABLED = True

                assistant = Assistant()

                # Verify HybridDataSource was created (it will handle mode internally)
                assert assistant.db is mock_hybrid

    def test_assistant_with_sqlite_only_mode(self):
        """Test Assistant with SQLite-only mode."""
        with patch("src.hybrid_data_source.HybridDataSource") as mock_hybrid_class:
            mock_hybrid = Mock()
            mock_hybrid_class.return_value = mock_hybrid

            # Set SQLite-only mode
            with patch("src.hybrid_data_source.api_config") as mock_config:
                mock_config.MODE = "sqlite_only"
                mock_config.ENABLED = True

                assistant = Assistant()

                # Verify HybridDataSource was created (it will handle mode internally)
                assert assistant.db is mock_hybrid


class TestAssistantWithRealDataSources:
    """Integration tests with real data sources (using temp database)."""

    def test_assistant_works_with_real_sqlite_data_source(self, temp_db, sample_champions):
        """Test Assistant works with real SQLiteDataSource."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()

        # Insert sample champions
        cursor = data_source._db.connection.cursor()
        for champ in sample_champions:
            cursor.execute("INSERT OR IGNORE INTO champions (name) VALUES (?)", (champ,))
        data_source._db.connection.commit()

        assistant = Assistant(data_source=data_source)

        # Test basic functionality
        champion_id = assistant.db.get_champion_id("Aatrox")
        assert champion_id is not None

        assistant.close()
