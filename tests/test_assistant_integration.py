"""
Tests for Assistant database wiring.

This test suite verifies that:
- Assistant accepts a Database via dependency injection
- Assistant defaults to a Database on config.DATABASE_PATH
- The injected database is connected on init and closed by Assistant.close()

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration
Updated: 2026-07-25 (DataSource adapter layer removed - SQLite only)
"""

import pytest
from unittest.mock import Mock, patch

from src.assistant import Assistant
from src.db import Database


class TestAssistantDatabaseInjection:
    """Test database dependency injection."""

    def test_assistant_accepts_database(self, temp_db):
        """Test that Assistant accepts a Database via dependency injection."""
        db = Database(str(temp_db))
        assistant = Assistant(db)

        assert assistant.db is db
        assistant.close()

    def test_assistant_uses_config_path_by_default(self):
        """Test that Assistant builds a Database on config.DATABASE_PATH by default."""
        with patch("src.assistant.Database") as mock_db_class:
            mock_db = Mock()
            mock_db_class.return_value = mock_db

            assistant = Assistant()

            from src.config import config

            mock_db_class.assert_called_once_with(config.DATABASE_PATH)
            assert assistant.db is mock_db
            mock_db.connect.assert_called_once()

    def test_assistant_connects_database_on_init(self, temp_db):
        """Test that Assistant connects the database on initialization."""
        db = Mock(spec=Database)
        Assistant(db)

        db.connect.assert_called_once()

    def test_assistant_close_closes_database(self, temp_db):
        """Test that Assistant.close() closes the database connection."""
        db = Mock(spec=Database)
        assistant = Assistant(db)

        assistant.close()

        db.close.assert_called_once()


class TestAssistantWithMockedDatabase:
    """Test Assistant functionality with a mocked database."""

    @pytest.fixture
    def mock_db(self):
        """Create mock database for testing."""
        mock = Mock()
        mock.get_champion_id.return_value = 42
        mock.get_champion_matchups_for_draft.return_value = []
        mock.get_champion_matchups_by_name.return_value = []
        mock.get_all_matchups_bulk.return_value = {}
        mock.build_champion_cache.return_value = {"Jinx": 42}
        return mock

    def test_assistant_uses_database_for_queries(self, mock_db):
        """Test that Assistant uses the injected database for queries."""
        assistant = Assistant(mock_db)

        # Warm cache should call database methods
        assistant.warm_cache(["Jinx"])

        # Verify database was used
        mock_db.get_champion_matchups_for_draft.assert_called()

    def test_assistant_delegates_to_specialized_modules(self, mock_db):
        """Test that Assistant initializes specialized modules with the database."""
        assistant = Assistant(mock_db)

        assert assistant.scorer is not None
        assert assistant.tier_list_gen is not None
        assert assistant.recommender is not None
        assert assistant.team_analyzer is not None


class TestAssistantWithRealDatabase:
    """Integration tests with a real database (using temp database)."""

    def test_assistant_works_with_real_database(self, temp_db, sample_champions):
        """Test Assistant works with a real Database."""
        db = Database(str(temp_db))
        db.connect()

        # Insert sample champions
        cursor = db.connection.cursor()
        for champ in sample_champions:
            cursor.execute("INSERT OR IGNORE INTO champions (name) VALUES (?)", (champ,))
        db.connection.commit()

        assistant = Assistant(db)

        # Test basic functionality
        champion_id = assistant.db.get_champion_id("Aatrox")
        assert champion_id is not None

        assistant.close()
