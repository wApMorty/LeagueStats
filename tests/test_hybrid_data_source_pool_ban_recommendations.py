"""
Regression tests for HybridDataSource.save_pool_ban_recommendations method.

Bug History:
-----------
**Original Bug**: AttributeError: 'HybridDataSource' object has no attribute 'save_pool_ban_recommendations'

**Root Cause**: During Sprint 2 refactoring to DataSource architecture, the save_pool_ban_recommendations
method was not migrated from Database class to the DataSource interface. This caused
Assistant.precalculate_pool_bans() to fail when calling self.db.save_pool_ban_recommendations().

**Fix Applied**:
- Added abstract save_pool_ban_recommendations method to DataSource interface (src/data_source.py:329-341)
- Implemented save_pool_ban_recommendations in SQLiteDataSource (delegating to Database)
- Implemented save_pool_ban_recommendations in HybridDataSource (writes to SQLite only)
- Implemented save_pool_ban_recommendations in APIDataSource (raises NotImplementedError)

**Test Objectives**:
This test suite ensures the bug cannot regress by verifying:
1. save_pool_ban_recommendations method exists in all DataSource implementations
2. Write operations go to SQLite only (never to API)
3. Assistant.precalculate_pool_bans() can call the method end-to-end
4. Explicit error when SQLite source unavailable
5. API source correctly raises NotImplementedError (read-only)

Author: @pj35
Created: 2026-02-10
Sprint: 2 - API Integration (DataSource Architecture Regression Tests)
Reference: Similar to test_hybrid_data_source_champion_scores.py
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import logging

from src.data_source import DataSource
from src.hybrid_data_source import HybridDataSource
from src.sqlite_data_source import SQLiteDataSource
from src.api_data_source import APIDataSource
from src.assistant import Assistant


class TestDataSourceInterfaceDefinition:
    """Regression test: Verify save_pool_ban_recommendations exists in DataSource interface."""

    def test_method_exists_in_data_source_interface(self):
        """
        Regression test: DataSource interface must define save_pool_ban_recommendations.

        Bug: Missing abstract method in DataSource interface
        Fix: Added @abstractmethod save_pool_ban_recommendations to DataSource
        """
        # Verify method exists in DataSource
        assert hasattr(
            DataSource, "save_pool_ban_recommendations"
        ), "save_pool_ban_recommendations method missing from DataSource interface"

        # Verify method is callable
        assert callable(
            getattr(DataSource, "save_pool_ban_recommendations")
        ), "save_pool_ban_recommendations is not callable"

    def test_method_is_abstract(self):
        """
        Regression test: save_pool_ban_recommendations must be abstract method.

        This ensures all DataSource implementations must implement this method.
        """
        import inspect

        # Get method from DataSource
        method = getattr(DataSource, "save_pool_ban_recommendations")

        # Check if method has __isabstractmethod__ attribute set to True
        assert getattr(
            method, "__isabstractmethod__", False
        ), "save_pool_ban_recommendations should be marked as @abstractmethod"


class TestSQLiteDataSourceImplementation:
    """Regression test: Verify SQLiteDataSource implements save_pool_ban_recommendations."""

    def test_method_exists_in_sqlite_data_source(self):
        """
        Regression test: SQLiteDataSource must implement save_pool_ban_recommendations.

        Bug: Method missing from SQLiteDataSource adapter
        Fix: Implemented method delegating to self.db.save_pool_ban_recommendations()
        """
        with patch("src.sqlite_data_source.Database"):
            sqlite_ds = SQLiteDataSource(database_path="test.db")

            # Verify method exists
            assert hasattr(
                sqlite_ds, "save_pool_ban_recommendations"
            ), "save_pool_ban_recommendations method missing from SQLiteDataSource"

            # Verify method is callable
            assert callable(
                getattr(sqlite_ds, "save_pool_ban_recommendations")
            ), "save_pool_ban_recommendations is not callable"

    def test_sqlite_delegates_to_database(self):
        """
        Regression test: SQLiteDataSource should delegate to Database.save_pool_ban_recommendations().

        This ensures the SQLiteDataSource adapter correctly wraps the Database layer.
        """
        with patch("src.sqlite_data_source.Database") as mock_db_class:
            mock_db = MagicMock()
            mock_db.save_pool_ban_recommendations.return_value = 3
            mock_db_class.return_value = mock_db

            sqlite_ds = SQLiteDataSource(database_path="test.db")

            # Sample ban data
            ban_data = [
                ("Darius", 15.5, -2.5, "Aatrox", 3),
                ("Garen", 12.0, -1.5, "Camille", 4),
                ("Malphite", 10.5, -1.0, "Fiora", 2),
            ]

            # Call save_pool_ban_recommendations
            result = sqlite_ds.save_pool_ban_recommendations("TestPool", ban_data)

            # Verify delegation to Database
            mock_db.save_pool_ban_recommendations.assert_called_once_with("TestPool", ban_data)

            # Verify return value
            assert result == 3


class TestHybridDataSourceImplementation:
    """Regression test: Verify HybridDataSource implements save_pool_ban_recommendations."""

    def test_method_exists_in_hybrid_data_source(self):
        """
        Regression test: HybridDataSource must have save_pool_ban_recommendations method.

        Bug: AttributeError: 'HybridDataSource' object has no attribute 'save_pool_ban_recommendations'
        Fix: Added method to HybridDataSource that delegates to sqlite_source
        """
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "hybrid"
            mock_config.ENABLED = True

            with patch("src.hybrid_data_source.APIDataSource"):
                with patch("src.hybrid_data_source.SQLiteDataSource"):
                    hybrid_ds = HybridDataSource()

                    # Verify method exists
                    assert hasattr(
                        hybrid_ds, "save_pool_ban_recommendations"
                    ), "save_pool_ban_recommendations method missing from HybridDataSource"

                    # Verify method is callable
                    assert callable(
                        getattr(hybrid_ds, "save_pool_ban_recommendations")
                    ), "save_pool_ban_recommendations is not callable"

    def test_method_signature_matches_data_source_interface(self):
        """
        Regression test: Verify method signature matches DataSource interface.

        The method signature must match the abstract definition in DataSource
        to ensure compatibility across all data sources.
        """
        import inspect

        # Get abstract method signature
        abstract_sig = inspect.signature(DataSource.save_pool_ban_recommendations)

        # Get HybridDataSource implementation signature
        hybrid_sig = inspect.signature(HybridDataSource.save_pool_ban_recommendations)

        # Verify signatures match (excluding 'self')
        abstract_params = list(abstract_sig.parameters.keys())[1:]  # Skip 'self'
        hybrid_params = list(hybrid_sig.parameters.keys())[1:]  # Skip 'self'

        assert (
            abstract_params == hybrid_params
        ), f"Method signature mismatch: expected {abstract_params}, got {hybrid_params}"


class TestAPIDataSourceImplementation:
    """Regression test: Verify APIDataSource correctly rejects write operations."""

    def test_method_exists_in_api_data_source(self):
        """
        Regression test: APIDataSource must implement save_pool_ban_recommendations.

        Even though API is read-only, it must implement the interface method
        to raise NotImplementedError with a clear message.
        """
        api_ds = APIDataSource()

        # Verify method exists
        assert hasattr(
            api_ds, "save_pool_ban_recommendations"
        ), "save_pool_ban_recommendations method missing from APIDataSource"

        # Verify method is callable
        assert callable(
            getattr(api_ds, "save_pool_ban_recommendations")
        ), "save_pool_ban_recommendations is not callable"

    def test_api_raises_not_implemented_error(self):
        """
        Regression test: APIDataSource should raise NotImplementedError for writes.

        API is read-only, so write operations must fail with clear error message.
        """
        api_ds = APIDataSource()

        ban_data = [
            ("Darius", 15.5, -2.5, "Aatrox", 3),
            ("Garen", 12.0, -1.5, "Camille", 4),
        ]

        with pytest.raises(NotImplementedError, match="APIDataSource is read-only"):
            api_ds.save_pool_ban_recommendations("TestPool", ban_data)


class TestHybridDataSourceWritesToSQLiteOnly:
    """Regression test: Verify write operations go to SQLite only, never API."""

    @pytest.fixture
    def mock_sqlite_source(self):
        """Mock SQLite data source."""
        return MagicMock(spec=SQLiteDataSource)

    @pytest.fixture
    def hybrid_source_with_mocked_sqlite(self, mock_sqlite_source):
        """Create HybridDataSource with mocked SQLite source."""
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "hybrid"
            mock_config.ENABLED = True

            with patch("src.hybrid_data_source.APIDataSource"):
                with patch("src.hybrid_data_source.SQLiteDataSource") as mock_sqlite_class:
                    mock_sqlite_class.return_value = mock_sqlite_source
                    hybrid_ds = HybridDataSource()
                    hybrid_ds.connect()
                    return hybrid_ds

    def test_save_pool_ban_recommendations_writes_to_sqlite_only(
        self, hybrid_source_with_mocked_sqlite, mock_sqlite_source
    ):
        """
        Regression test: Write operations must go to SQLite, never to API.

        Verify that HybridDataSource.save_pool_ban_recommendations() delegates to
        sqlite_source.save_pool_ban_recommendations(), not to api_source.

        This is critical because:
        - API is read-only (no write endpoint exists)
        - All writes must persist to local SQLite database
        - Hybrid mode should never attempt to write to API
        """
        ban_data = [
            ("Darius", 15.5, -2.5, "Aatrox", 3),
            ("Garen", 12.0, -1.5, "Camille", 4),
            ("Malphite", 10.5, -1.0, "Fiora", 2),
        ]

        # Call save_pool_ban_recommendations
        hybrid_source_with_mocked_sqlite.save_pool_ban_recommendations("TopLane", ban_data)

        # Verify SQLite source was called with exact parameters
        mock_sqlite_source.save_pool_ban_recommendations.assert_called_once_with(
            "TopLane", ban_data
        )

    def test_save_pool_ban_recommendations_never_calls_api_source(
        self, hybrid_source_with_mocked_sqlite
    ):
        """
        Regression test: Verify API source is NEVER called for write operations.

        This test ensures that even if api_source exists, it is never used for writes.
        """
        # Mock api_source to verify it's never called
        hybrid_source_with_mocked_sqlite.api_source = MagicMock()

        ban_data = [
            ("Zed", 20.0, -3.0, "Lissandra", 5),
        ]

        # Call save_pool_ban_recommendations
        hybrid_source_with_mocked_sqlite.save_pool_ban_recommendations("MidLane", ban_data)

        # Verify API source was NEVER called
        assert (
            not hybrid_source_with_mocked_sqlite.api_source.save_pool_ban_recommendations.called
        ), "save_pool_ban_recommendations should NEVER call API source (writes are SQLite-only)"

    def test_save_pool_ban_recommendations_logs_write_operation(
        self, hybrid_source_with_mocked_sqlite, caplog
    ):
        """
        Regression test: Verify write operations are logged for diagnostics.

        Logs help diagnose issues and confirm where data is being written.
        """
        ban_data = [
            ("Darius", 15.5, -2.5, "Aatrox", 3),
        ]

        with caplog.at_level(logging.INFO):
            hybrid_source_with_mocked_sqlite.save_pool_ban_recommendations("TopLane", ban_data)

        # Verify logging occurred
        assert any(
            "Saving ban recommendations" in record.message and "TopLane" in record.message
            for record in caplog.records
        ), "Expected log message for write operation not found"


class TestHybridDataSourceErrorHandling:
    """Regression test: Verify error handling when SQLite unavailable."""

    def test_save_pool_ban_recommendations_raises_error_when_sqlite_unavailable(self):
        """
        Regression test: Raise explicit error when SQLite source unavailable.

        HybridDataSource should raise RuntimeError with clear message
        if sqlite_source is None (e.g., in api_only mode).

        This prevents silent failures and provides clear diagnostics.
        """
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "api_only"
            mock_config.ENABLED = True

            with patch("src.hybrid_data_source.APIDataSource"):
                hybrid_ds = HybridDataSource()

                # Verify sqlite_source is None in api_only mode
                assert hybrid_ds.sqlite_source is None

                ban_data = [
                    ("Darius", 15.5, -2.5, "Aatrox", 3),
                ]

                # Attempt to save should raise RuntimeError
                with pytest.raises(RuntimeError, match="SQLite source not available"):
                    hybrid_ds.save_pool_ban_recommendations("TopLane", ban_data)

    def test_save_pool_ban_recommendations_error_is_logged(self, caplog):
        """
        Regression test: Verify errors are logged when SQLite unavailable.

        Logging ensures errors are visible in production diagnostics.
        """
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "api_only"
            mock_config.ENABLED = True

            with patch("src.hybrid_data_source.APIDataSource"):
                hybrid_ds = HybridDataSource()

                ban_data = [
                    ("Darius", 15.5, -2.5, "Aatrox", 3),
                ]

                with caplog.at_level(logging.ERROR):
                    with pytest.raises(RuntimeError):
                        hybrid_ds.save_pool_ban_recommendations("TopLane", ban_data)

                # Verify error was logged
                assert any(
                    "Cannot save ban recommendations" in record.message for record in caplog.records
                ), "Expected error log message not found"


class TestAssistantPrecalculatePoolBansIntegration:
    """
    Regression test: Verify Assistant.precalculate_pool_bans() works end-to-end.

    This is the actual code path that was failing:
    src/assistant.py:1298 calls self.db.save_pool_ban_recommendations()
    """

    @pytest.fixture
    def mock_data_source(self):
        """Mock DataSource for testing Assistant integration."""
        from src.models import Matchup

        mock_ds = MagicMock()

        # Mock champion names
        mock_ds.get_all_champion_names.return_value = {
            1: "Aatrox",
            2: "Darius",
            3: "Garen",
            4: "Camille",
        }

        # Mock get_champion_id
        mock_ds.get_champion_id.side_effect = lambda name: {
            "Aatrox": 1,
            "Darius": 2,
            "Garen": 3,
            "Camille": 4,
        }.get(name)

        # Mock get_champion_matchups_by_name
        # Need pickrate >= 1.0 and games >= 30 to pass MIN_PICKRATE and MIN_MATCHUP_GAMES
        def mock_matchups(champion_name):
            if champion_name == "Aatrox":
                return [
                    Matchup("Darius", 48.5, -150, -200, 8.5, 1500),  # High pickrate
                    Matchup("Garen", 52.0, 100, 150, 12.3, 2000),  # High pickrate
                ]
            elif champion_name == "Camille":
                return [
                    Matchup("Darius", 51.0, 50, 80, 10.0, 1800),  # High pickrate
                    Matchup("Garen", 49.0, -80, -120, 11.0, 1900),  # High pickrate
                ]
            return []

        mock_ds.get_champion_matchups_by_name.side_effect = mock_matchups

        # Mock get_matchup_delta2 - critical for precalculate_pool_bans
        def mock_delta2(our_champion, enemy_champion):
            # Aatrox vs enemies
            if our_champion == "Aatrox" and enemy_champion == "Darius":
                return -150.0
            elif our_champion == "Aatrox" and enemy_champion == "Garen":
                return 100.0
            # Camille vs enemies
            elif our_champion == "Camille" and enemy_champion == "Darius":
                return 50.0
            elif our_champion == "Camille" and enemy_champion == "Garen":
                return -80.0
            return None

        mock_ds.get_matchup_delta2.side_effect = mock_delta2

        # Mock save_pool_ban_recommendations to track calls
        mock_ds.save_pool_ban_recommendations = MagicMock(return_value=2)

        return mock_ds

    def test_assistant_precalculate_pool_bans_can_save_recommendations(self, mock_data_source):
        """
        Regression test: Assistant.precalculate_pool_bans() must work end-to-end.

        This test reproduces the exact failing code path:
        1. Assistant initializes with HybridDataSource
        2. precalculate_pool_bans() is called
        3. self.db.save_pool_ban_recommendations() is invoked

        Before fix: AttributeError: 'HybridDataSource' object has no attribute 'save_pool_ban_recommendations'
        After fix: Method exists and is callable
        """
        # Create Assistant with mocked data source
        assistant = Assistant(data_source=mock_data_source, verbose=False)

        champion_pool = ["Aatrox", "Camille"]

        # Call precalculate_pool_bans - should NOT raise AttributeError
        try:
            result = assistant.precalculate_pool_bans("TopLane", champion_pool)
            success = True
            error_message = None
        except AttributeError as e:
            success = False
            error_message = str(e)
            result = False

        # Verify no AttributeError occurred
        assert success, f"precalculate_pool_bans() raised AttributeError: {error_message}"

        # Verify save_pool_ban_recommendations was called
        assert (
            mock_data_source.save_pool_ban_recommendations.call_count == 1
        ), "save_pool_ban_recommendations() should be called once"

        # Verify return value indicates success
        assert result is True, "precalculate_pool_bans() should return True on success"

    def test_assistant_precalculate_pool_bans_calls_save_with_correct_params(
        self, mock_data_source
    ):
        """
        Regression test: Verify save_pool_ban_recommendations is called with correct parameters.

        This ensures the method is not just present, but actually invoked correctly
        by Assistant.precalculate_pool_bans().
        """
        assistant = Assistant(data_source=mock_data_source, verbose=False)

        champion_pool = ["Aatrox", "Camille"]

        # Call precalculate_pool_bans
        assistant.precalculate_pool_bans("TopLane", champion_pool)

        # Verify save_pool_ban_recommendations was called
        calls = mock_data_source.save_pool_ban_recommendations.call_args_list
        assert len(calls) == 1, "save_pool_ban_recommendations should be called once"

        # Verify call structure
        call_args, call_kwargs = calls[0]

        # Method can be called with positional or keyword args
        if call_args:
            # Positional args: (pool_name, ban_data)
            assert len(call_args) == 2, "Expected 2 positional arguments"
            pool_name, ban_data = call_args
        else:
            # Keyword args
            pool_name = call_kwargs.get("pool_name")
            ban_data = call_kwargs.get("ban_data")

        # Verify pool_name
        assert pool_name == "TopLane", f"Expected pool_name='TopLane', got '{pool_name}'"

        # Verify ban_data structure (list of tuples)
        assert isinstance(ban_data, list), "ban_data should be a list"
        assert len(ban_data) > 0, "ban_data should not be empty"

        # Verify first tuple structure: (enemy_champion, threat_score, best_response_delta2, best_response_champion, matchups_count)
        first_ban = ban_data[0]
        assert isinstance(first_ban, tuple), "Each ban should be a tuple"
        assert len(first_ban) == 5, "Each ban tuple should have 5 elements"

        (
            enemy_champion,
            threat_score,
            best_response_delta2,
            best_response_champion,
            matchups_count,
        ) = first_ban
        assert isinstance(enemy_champion, str), "enemy_champion should be string"
        assert isinstance(threat_score, (int, float)), "threat_score should be numeric"
        assert isinstance(
            best_response_delta2, (int, float)
        ), "best_response_delta2 should be numeric"
        assert isinstance(best_response_champion, str), "best_response_champion should be string"
        assert isinstance(matchups_count, int), "matchups_count should be integer"

    def test_assistant_with_hybrid_data_source_can_save_recommendations(self):
        """
        Regression test: Verify Assistant works with real HybridDataSource instance.

        This test uses the actual HybridDataSource class (with mocked backends)
        to ensure compatibility, not just a generic Mock.
        """
        from src.models import Matchup

        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "sqlite_only"
            mock_config.ENABLED = True

            with patch("src.hybrid_data_source.SQLiteDataSource") as mock_sqlite_class:
                mock_sqlite = MagicMock()

                # Mock required methods
                mock_sqlite.get_all_champion_names.return_value = {
                    1: "Aatrox",
                    2: "Camille",
                }
                mock_sqlite.get_champion_id.side_effect = lambda name: {
                    "Aatrox": 1,
                    "Camille": 2,
                }.get(name)

                # Mock matchups
                def mock_matchups(champion_name):
                    if champion_name == "Aatrox":
                        return [
                            Matchup("Darius", 48.5, -150, -200, 8.5, 1500),
                            Matchup("Garen", 52.0, 100, 150, 12.3, 2000),
                        ]
                    elif champion_name == "Camille":
                        return [
                            Matchup("Darius", 51.0, 50, 80, 10.0, 1800),
                        ]
                    return []

                mock_sqlite.get_champion_matchups_by_name.side_effect = mock_matchups

                # Mock save method
                mock_sqlite.save_pool_ban_recommendations = MagicMock(return_value=5)

                mock_sqlite_class.return_value = mock_sqlite

                # Create real HybridDataSource
                hybrid_ds = HybridDataSource()
                hybrid_ds.connect()

                # Create Assistant with HybridDataSource
                assistant = Assistant(data_source=hybrid_ds, verbose=False)

                champion_pool = ["Aatrox", "Camille"]

                # Call precalculate_pool_bans - should work without AttributeError
                try:
                    result = assistant.precalculate_pool_bans("TopLane", champion_pool)
                    success = True
                    error_message = None
                except AttributeError as e:
                    success = False
                    error_message = str(e)
                    result = False

                assert success, f"Assistant with HybridDataSource failed: {error_message}"

                # Verify save was called on SQLite backend
                assert mock_sqlite.save_pool_ban_recommendations.call_count == 1

                # Verify result
                assert result is True


class TestSQLiteDataSourceIntegration:
    """Integration tests: Verify SQLiteDataSource can save and retrieve ban recommendations."""

    @pytest.fixture
    def sqlite_source_with_real_database(self, tmp_path):
        """Create SQLiteDataSource with real (temporary) database."""
        from src.db import Database

        # Create temporary database
        db_path = tmp_path / "test_bans.db"

        # Initialize database directly with path
        db = Database(str(db_path))
        db.connect()  # Critical: connect before using
        db.init_pool_ban_recommendations_table()

        # Create SQLiteDataSource with the same path
        sqlite_ds = SQLiteDataSource(database_path=str(db_path))
        sqlite_ds.connect()  # Connect SQLiteDataSource too
        return sqlite_ds

    def test_sqlite_data_source_delegates_to_database(self, sqlite_source_with_real_database):
        """
        Integration test: SQLiteDataSource should successfully save ban recommendations.

        This test verifies the entire chain:
        SQLiteDataSource -> Database -> SQLite file
        """
        ban_data = [
            ("Darius", 15.5, -2.5, "Aatrox", 3),
            ("Garen", 12.0, -1.5, "Camille", 4),
            ("Malphite", 10.5, -1.0, "Fiora", 2),
        ]

        # Save ban recommendations
        result = sqlite_source_with_real_database.save_pool_ban_recommendations("TopLane", ban_data)

        # Verify return value (number of records saved)
        assert result == 3

        # Verify data is actually in the database
        cursor = sqlite_source_with_real_database._db.connection.cursor()
        cursor.execute(
            "SELECT enemy_champion, threat_score FROM pool_ban_recommendations WHERE pool_name = ? ORDER BY threat_score DESC",
            ("TopLane",),
        )
        saved_bans = cursor.fetchall()

        assert len(saved_bans) == 3
        assert saved_bans[0][0] == "Darius"  # Highest threat score first
        assert saved_bans[0][1] == 15.5
