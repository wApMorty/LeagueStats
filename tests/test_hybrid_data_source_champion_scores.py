"""
Regression tests for HybridDataSource.save_champion_scores method.

Bug History:
-----------
**Original Bug**: AttributeError: 'HybridDataSource' object has no attribute 'save_champion_scores'

**Root Cause**: During Sprint 2 refactoring to DataSource architecture, the save_champion_scores
method was not migrated from Database class to the DataSource interface. This caused
Assistant.calculate_global_scores() to fail when calling self.db.save_champion_scores().

**Fix Applied**:
- Task #2: Added abstract save_champion_scores method to DataSource interface (src/data_source.py:273-295)
- Task #3: Implemented save_champion_scores in SQLiteDataSource (src/sqlite_data_source.py:137-156)
- Task #4: Implemented save_champion_scores in HybridDataSource (src/hybrid_data_source.py:251-278)

**Test Objectives**:
This test suite ensures the bug cannot regress by verifying:
1. save_champion_scores method exists and is callable
2. Write operations go to SQLite only (never to API)
3. Assistant.calculate_global_scores() can call the method end-to-end
4. Explicit error when SQLite source unavailable

Author: @pj35
Created: 2026-02-08
Sprint: 2 - API Integration (DataSource Architecture Regression Tests)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import logging

from src.hybrid_data_source import HybridDataSource
from src.sqlite_data_source import SQLiteDataSource
from src.assistant import Assistant


class TestHybridDataSourceSaveChampionScoresMethodExists:
    """Regression test: Verify save_champion_scores method exists."""

    def test_hybrid_data_source_has_save_champion_scores_method(self):
        """
        Regression test: HybridDataSource must have save_champion_scores method.

        Bug: AttributeError: 'HybridDataSource' object has no attribute 'save_champion_scores'
        Fix: Added method to DataSource interface and implemented in all adapters
        """
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "hybrid"
            mock_config.ENABLED = True

            with patch("src.hybrid_data_source.APIDataSource"):
                with patch("src.hybrid_data_source.SQLiteDataSource"):
                    hybrid_ds = HybridDataSource()

                    # Verify method exists
                    assert hasattr(
                        hybrid_ds, "save_champion_scores"
                    ), "save_champion_scores method missing from HybridDataSource"

                    # Verify method is callable
                    assert callable(
                        getattr(hybrid_ds, "save_champion_scores")
                    ), "save_champion_scores is not callable"

    def test_method_signature_matches_data_source_interface(self):
        """
        Regression test: Verify method signature matches DataSource interface.

        The method signature must match the abstract definition in DataSource
        to ensure compatibility across all data sources.
        """
        from src.data_source import DataSource
        import inspect

        # Get abstract method signature
        abstract_sig = inspect.signature(DataSource.save_champion_scores)

        # Get HybridDataSource implementation signature
        hybrid_sig = inspect.signature(HybridDataSource.save_champion_scores)

        # Verify signatures match (excluding 'self')
        abstract_params = list(abstract_sig.parameters.keys())[1:]  # Skip 'self'
        hybrid_params = list(hybrid_sig.parameters.keys())[1:]  # Skip 'self'

        assert (
            abstract_params == hybrid_params
        ), f"Method signature mismatch: expected {abstract_params}, got {hybrid_params}"


class TestHybridDataSourceSaveChampionScoresWritesToSQLiteOnly:
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

    def test_save_champion_scores_writes_to_sqlite_only(
        self, hybrid_source_with_mocked_sqlite, mock_sqlite_source
    ):
        """
        Regression test: Write operations must go to SQLite, never to API.

        Verify that HybridDataSource.save_champion_scores() delegates to
        sqlite_source.save_champion_scores(), not to api_source.

        This is critical because:
        - API is read-only (no write endpoint exists)
        - All writes must persist to local SQLite database
        - Hybrid mode should never attempt to write to API
        """
        # Call save_champion_scores
        hybrid_source_with_mocked_sqlite.save_champion_scores(
            champion_id=42,
            avg_delta2=150.5,
            variance=50.2,
            coverage=0.85,
            peak_impact=200.0,
            volatility=30.5,
            target_ratio=0.65,
        )

        # Verify SQLite source was called with exact parameters
        mock_sqlite_source.save_champion_scores.assert_called_once_with(
            champion_id=42,
            avg_delta2=150.5,
            variance=50.2,
            coverage=0.85,
            peak_impact=200.0,
            volatility=30.5,
            target_ratio=0.65,
        )

    def test_save_champion_scores_never_calls_api_source(self, hybrid_source_with_mocked_sqlite):
        """
        Regression test: Verify API source is NEVER called for write operations.

        This test ensures that even if api_source exists, it is never used for writes.
        """
        # Mock api_source to verify it's never called
        hybrid_source_with_mocked_sqlite.api_source = MagicMock()

        # Call save_champion_scores
        hybrid_source_with_mocked_sqlite.save_champion_scores(
            champion_id=1,
            avg_delta2=100.0,
            variance=25.0,
            coverage=0.75,
            peak_impact=150.0,
            volatility=20.0,
            target_ratio=0.50,
        )

        # Verify API source was NEVER called
        assert (
            not hybrid_source_with_mocked_sqlite.api_source.save_champion_scores.called
        ), "save_champion_scores should NEVER call API source (writes are SQLite-only)"

    def test_save_champion_scores_logs_write_operation(
        self, hybrid_source_with_mocked_sqlite, caplog
    ):
        """
        Regression test: Verify write operations are logged for diagnostics.

        Logs help diagnose issues and confirm where data is being written.
        """
        with caplog.at_level(logging.INFO):
            hybrid_source_with_mocked_sqlite.save_champion_scores(
                champion_id=42,
                avg_delta2=150.5,
                variance=50.2,
                coverage=0.85,
                peak_impact=200.0,
                volatility=30.5,
                target_ratio=0.65,
            )

        # Verify logging occurred
        assert any(
            "Saving champion scores" in record.message and "champion_id=42" in record.message
            for record in caplog.records
        ), "Expected log message for write operation not found"


class TestHybridDataSourceSaveChampionScoresErrorHandling:
    """Regression test: Verify error handling when SQLite unavailable."""

    def test_save_champion_scores_raises_error_when_sqlite_unavailable(self):
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

                # Attempt to save should raise RuntimeError
                with pytest.raises(RuntimeError, match="SQLite source not available"):
                    hybrid_ds.save_champion_scores(
                        champion_id=42,
                        avg_delta2=150.5,
                        variance=50.2,
                        coverage=0.85,
                        peak_impact=200.0,
                        volatility=30.5,
                        target_ratio=0.65,
                    )

    def test_save_champion_scores_error_is_logged(self, caplog):
        """
        Regression test: Verify errors are logged when SQLite unavailable.

        Logging ensures errors are visible in production diagnostics.
        """
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "api_only"
            mock_config.ENABLED = True

            with patch("src.hybrid_data_source.APIDataSource"):
                hybrid_ds = HybridDataSource()

                with caplog.at_level(logging.ERROR):
                    with pytest.raises(RuntimeError):
                        hybrid_ds.save_champion_scores(
                            champion_id=42,
                            avg_delta2=150.5,
                            variance=50.2,
                            coverage=0.85,
                            peak_impact=200.0,
                            volatility=30.5,
                            target_ratio=0.65,
                        )

                # Verify error was logged
                assert any(
                    "Cannot save champion scores" in record.message for record in caplog.records
                ), "Expected error log message not found"


class TestAssistantCalculateGlobalScoresIntegration:
    """
    Regression test: Verify Assistant.calculate_global_scores() works end-to-end.

    This is the actual code path that was failing:
    src/assistant.py:499 calls self.db.save_champion_scores()
    """

    @pytest.fixture
    def mock_data_source(self):
        """Mock DataSource for testing Assistant integration."""
        from src.models import Matchup

        mock_ds = MagicMock()
        mock_ds.get_all_champion_names.return_value = {
            1: "Aatrox",
            2: "Ahri",
            42: "Jinx",
        }
        # Mock save_champion_scores to track calls
        mock_ds.save_champion_scores = MagicMock()
        # Mock get_champion_id
        mock_ds.get_champion_id.side_effect = lambda name: {
            "Aatrox": 1,
            "Ahri": 2,
            "Jinx": 42,
        }.get(name)

        # Mock get_champion_matchups_by_name to return test matchups
        # Need at least 2 matchups with valid data for calculate_global_scores to work
        def mock_matchups(champion_name):
            if champion_name == "Aatrox":
                return [
                    Matchup("Darius", 48.5, -150, -200, 8.5, 1500),
                    Matchup("Garen", 52.0, 100, 150, 12.3, 2000),
                ]
            return []

        mock_ds.get_champion_matchups_by_name.side_effect = mock_matchups
        return mock_ds

    def test_assistant_calculate_global_scores_can_save_scores(self, mock_data_source):
        """
        Regression test: Assistant.calculate_global_scores() must work end-to-end.

        This test reproduces the exact failing code path:
        1. Assistant initializes with HybridDataSource
        2. calculate_global_scores() is called
        3. self.db.save_champion_scores() is invoked for each champion

        Before fix: AttributeError: 'HybridDataSource' object has no attribute 'save_champion_scores'
        After fix: Method exists and is callable
        """
        # Create Assistant with mocked data source
        assistant = Assistant(data_source=mock_data_source, verbose=False)

        # Call calculate_global_scores - should NOT raise AttributeError
        try:
            result = assistant.calculate_global_scores()
            success = True
            error_message = None
        except AttributeError as e:
            success = False
            error_message = str(e)
            result = None

        # Verify no AttributeError occurred
        assert success, f"calculate_global_scores() raised AttributeError: {error_message}"

        # Verify save_champion_scores was called at least once
        assert (
            mock_data_source.save_champion_scores.call_count > 0
        ), "save_champion_scores() should be called for each champion"

        # Verify return value indicates champions were scored
        assert result >= 0, "calculate_global_scores() should return count of champions scored"

    def test_assistant_calculate_global_scores_calls_save_with_correct_params(
        self, mock_data_source
    ):
        """
        Regression test: Verify save_champion_scores is called with correct parameters.

        This ensures the method is not just present, but actually invoked correctly
        by Assistant.calculate_global_scores().
        """
        assistant = Assistant(data_source=mock_data_source, verbose=False)

        # Call calculate_global_scores
        assistant.calculate_global_scores()

        # Verify save_champion_scores was called with expected parameter names
        # (we don't verify exact values since they're calculated, but we verify structure)
        calls = mock_data_source.save_champion_scores.call_args_list
        assert len(calls) > 0, "save_champion_scores should be called at least once"

        # Verify first call has all required parameters
        first_call_kwargs = calls[0][1] if calls[0][1] else {}
        if not first_call_kwargs:
            # Positional args - verify count matches expected signature
            first_call_args = calls[0][0]
            assert len(first_call_args) == 7, (
                "save_champion_scores should be called with 7 parameters "
                "(champion_id, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)"
            )
        else:
            # Keyword args - verify all required keys present
            required_params = {
                "champion_id",
                "avg_delta2",
                "variance",
                "coverage",
                "peak_impact",
                "volatility",
                "target_ratio",
            }
            assert required_params.issubset(
                set(first_call_kwargs.keys())
            ), f"Missing required parameters: {required_params - set(first_call_kwargs.keys())}"

    def test_assistant_with_hybrid_data_source_can_save_scores(self):
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
                mock_sqlite.get_all_champion_names.return_value = {1: "Aatrox"}
                mock_sqlite.get_champion_id.return_value = 1
                # Need to return matchups for calculate_global_scores to work
                mock_sqlite.get_champion_matchups_by_name.return_value = [
                    Matchup("Darius", 48.5, -150, -200, 8.5, 1500),
                    Matchup("Garen", 52.0, 100, 150, 12.3, 2000),
                ]
                mock_sqlite.save_champion_scores = MagicMock()
                mock_sqlite_class.return_value = mock_sqlite

                # Create real HybridDataSource
                hybrid_ds = HybridDataSource()
                hybrid_ds.connect()

                # Create Assistant with HybridDataSource
                assistant = Assistant(data_source=hybrid_ds, verbose=False)

                # Call calculate_global_scores - should work without AttributeError
                try:
                    assistant.calculate_global_scores()
                    success = True
                    error_message = None
                except AttributeError as e:
                    success = False
                    error_message = str(e)

                assert success, f"Assistant with HybridDataSource failed: {error_message}"

                # Verify save was called on SQLite backend
                assert mock_sqlite.save_champion_scores.call_count > 0
