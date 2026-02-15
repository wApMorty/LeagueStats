"""
Regression test for bug: AttributeError when warm_cache() called with custom pool.

Bug description:
    When DraftMonitor selected a custom pool and called warm_cache(), the Assistant
    attempted to call self.db.get_reverse_matchups_for_draft(champion) which was
    missing from HybridDataSource, causing an AttributeError.

    Error: AttributeError: 'HybridDataSource' object has no attribute 'get_reverse_matchups_for_draft'

Fixed in: TODO #3 (2026-02-15)
    - Added get_reverse_matchups_for_draft() method to HybridDataSource
    - Method delegates to PostgreSQL with SQLite fallback
    - Enables bidirectional cache warmup for pool champions

Test approach:
    Verify that warm_cache() can successfully pre-load matchups for all champions
    in a custom pool without raising AttributeError, and that the reverse matchup
    method is properly called for each champion.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from typing import List

from src.assistant import Assistant
from src.models import MatchupDraft


@pytest.fixture
def mock_hybrid_data_source():
    """Mock HybridDataSource with all required methods for warm_cache()."""
    mock_db = Mock()

    # Mock direct matchups method (champion as picker)
    # MatchupDraft signature: (enemy_name, delta2, pickrate, games)
    mock_db.get_champion_matchups_for_draft.return_value = [
        MatchupDraft("Enemy1", 150.0, 10.0, 1000),
        MatchupDraft("Enemy2", -100.0, 8.0, 800),
    ]

    # Mock reverse matchups method (champion as enemy) - This was missing before fix
    # MatchupDraft signature: (enemy_name, delta2, pickrate, games)
    mock_db.get_reverse_matchups_for_draft.return_value = [
        MatchupDraft("Picker1", 120.0, 9.0, 900),
        MatchupDraft("Picker2", -60.0, 7.0, 700),
    ]

    mock_db.connect.return_value = None
    mock_db.close.return_value = None

    return mock_db


@pytest.fixture
def assistant_with_mock_db(mock_hybrid_data_source):
    """Create Assistant instance with mocked HybridDataSource via dependency injection."""
    # Use dependency injection to provide mock database (no patching needed)
    assistant = Assistant(data_source=mock_hybrid_data_source, verbose=False)
    return assistant


class TestWarmCacheWithCustomPool:
    """Tests for warm_cache() with custom champion pools (regression for bug #9)."""

    def test_warm_cache_with_pool_selection(self, assistant_with_mock_db):
        """
        Regression test: warm_cache() should work with custom pool selection.

        Before fix: AttributeError: 'HybridDataSource' object has no attribute 'get_reverse_matchups_for_draft'
        After fix: warm_cache() successfully pre-loads bidirectional matchups for all pool champions

        Scenario:
            - User selects a custom pool with 3 champions
            - DraftMonitor calls assistant.warm_cache(pool)
            - Assistant should call both:
              * get_champion_matchups_for_draft() for direct matchups
              * get_reverse_matchups_for_draft() for reverse matchups
            - No AttributeError should be raised
        """
        # GIVEN: A custom pool with 3 champions (like pool #9 in real scenario)
        custom_pool = ["Aatrox", "Darius", "Garen"]

        # WHEN: warm_cache() is called with the custom pool
        # This should NOT raise AttributeError
        assistant_with_mock_db.warm_cache(custom_pool)

        # THEN: get_champion_matchups_for_draft() should be called for each champion
        assert assistant_with_mock_db.db.get_champion_matchups_for_draft.call_count == 3

        # THEN: get_reverse_matchups_for_draft() should be called for each champion (CRITICAL FIX)
        assert assistant_with_mock_db.db.get_reverse_matchups_for_draft.call_count == 3

        # THEN: Verify called with correct champion names
        expected_calls_direct = ["Aatrox", "Darius", "Garen"]
        actual_calls_direct = [
            call[0][0]
            for call in assistant_with_mock_db.db.get_champion_matchups_for_draft.call_args_list
        ]
        assert actual_calls_direct == expected_calls_direct

        expected_calls_reverse = ["Aatrox", "Darius", "Garen"]
        actual_calls_reverse = [
            call[0][0]
            for call in assistant_with_mock_db.db.get_reverse_matchups_for_draft.call_args_list
        ]
        assert actual_calls_reverse == expected_calls_reverse

    def test_warm_cache_empty_pool(self, assistant_with_mock_db):
        """
        Regression test: warm_cache() should handle empty pool gracefully.

        Scenario:
            - User provides an empty pool
            - warm_cache() should return immediately without errors
            - No database calls should be made
        """
        # GIVEN: An empty pool
        empty_pool = []

        # WHEN: warm_cache() is called with empty pool
        assistant_with_mock_db.warm_cache(empty_pool)

        # THEN: No database calls should be made (early return)
        assistant_with_mock_db.db.get_champion_matchups_for_draft.assert_not_called()
        assistant_with_mock_db.db.get_reverse_matchups_for_draft.assert_not_called()

    def test_warm_cache_single_champion(self, assistant_with_mock_db):
        """
        Regression test: warm_cache() should work with single-champion pool.

        Scenario:
            - User provides a pool with only 1 champion
            - warm_cache() should successfully cache matchups for that champion
        """
        # GIVEN: A pool with single champion
        single_champion_pool = ["Aatrox"]

        # WHEN: warm_cache() is called
        assistant_with_mock_db.warm_cache(single_champion_pool)

        # THEN: Both methods should be called exactly once
        assert assistant_with_mock_db.db.get_champion_matchups_for_draft.call_count == 1
        assert assistant_with_mock_db.db.get_reverse_matchups_for_draft.call_count == 1

        # THEN: Called with correct champion
        assistant_with_mock_db.db.get_champion_matchups_for_draft.assert_called_with("Aatrox")
        assistant_with_mock_db.db.get_reverse_matchups_for_draft.assert_called_with("Aatrox")

    def test_warm_cache_cache_population(self, assistant_with_mock_db):
        """
        Regression test: Verify that cache is actually populated with matchup data.

        Scenario:
            - After warm_cache() completes, internal cache should contain data
            - Both direct cache and reverse cache should be populated
        """
        # GIVEN: A pool with champions
        pool = ["Aatrox", "Darius"]

        # WHEN: warm_cache() is called
        assistant_with_mock_db.warm_cache(pool)

        # THEN: Internal caches should be populated
        assert "Aatrox" in assistant_with_mock_db._matchups_cache
        assert "Darius" in assistant_with_mock_db._matchups_cache
        assert "Aatrox" in assistant_with_mock_db._reverse_cache
        assert "Darius" in assistant_with_mock_db._reverse_cache

        # THEN: Cache data should be valid (non-empty lists)
        assert len(assistant_with_mock_db._matchups_cache["Aatrox"]) > 0
        assert len(assistant_with_mock_db._reverse_cache["Aatrox"]) > 0


class TestHybridDataSourceReverseMatchupMethod:
    """Tests for HybridDataSource.get_reverse_matchups_for_draft() method existence."""

    def test_hybrid_data_source_has_reverse_matchups_method(self):
        """
        Regression test: Verify HybridDataSource has get_reverse_matchups_for_draft() method.

        Before fix: Method did not exist, causing AttributeError
        After fix: Method exists with correct signature
        """
        # GIVEN: Import HybridDataSource class
        from src.hybrid_data_source import HybridDataSource

        # THEN: Class should have the get_reverse_matchups_for_draft method
        assert hasattr(HybridDataSource, "get_reverse_matchups_for_draft")

        # THEN: Method should be callable
        assert callable(getattr(HybridDataSource, "get_reverse_matchups_for_draft"))

    def test_hybrid_data_source_reverse_matchups_signature(self):
        """
        Regression test: Verify get_reverse_matchups_for_draft() has correct signature.

        Expected signature: get_reverse_matchups_for_draft(champion_name: str, as_dataclass: bool = True)
        """
        # GIVEN: Import HybridDataSource class
        from src.hybrid_data_source import HybridDataSource
        import inspect

        # WHEN: Get method signature
        method = getattr(HybridDataSource, "get_reverse_matchups_for_draft")
        sig = inspect.signature(method)

        # THEN: Should have 3 parameters (self, champion_name, as_dataclass)
        params = list(sig.parameters.keys())
        assert len(params) == 3
        assert params[0] == "self"
        assert params[1] == "champion_name"
        assert params[2] == "as_dataclass"

        # THEN: as_dataclass should have default value True
        as_dataclass_param = sig.parameters["as_dataclass"]
        assert as_dataclass_param.default is True

    def test_hybrid_data_source_reverse_matchups_delegates_to_fallback(self):
        """
        Regression test: Verify get_reverse_matchups_for_draft() uses fallback strategy.

        The method should use _try_postgres_with_fallback() to delegate to PostgreSQL
        with SQLite fallback (hybrid pattern).
        """
        # GIVEN: Mock both PostgreSQL and SQLite sources
        with (
            patch("src.hybrid_data_source.PostgreSQLDataSource") as mock_postgres_class,
            patch("src.hybrid_data_source.SQLiteDataSource") as mock_sqlite_class,
            patch("src.hybrid_data_source.api_config") as mock_config,
        ):

            mock_config.MODE = "hybrid"
            mock_config.ENABLED = True

            # Setup mocks
            mock_postgres = Mock()
            # MatchupDraft signature: (enemy_name, delta2, pickrate, games)
            mock_postgres.get_reverse_matchups_for_draft.return_value = [
                MatchupDraft("Picker1", 120.0, 9.0, 900)
            ]
            mock_postgres_class.return_value = mock_postgres

            mock_sqlite = Mock()
            mock_sqlite_class.return_value = mock_sqlite

            # WHEN: Create HybridDataSource and call get_reverse_matchups_for_draft()
            from src.hybrid_data_source import HybridDataSource

            hybrid_source = HybridDataSource()
            hybrid_source.connect()

            result = hybrid_source.get_reverse_matchups_for_draft("Aatrox")

            # THEN: PostgreSQL method should be called first (hybrid strategy)
            mock_postgres.get_reverse_matchups_for_draft.assert_called_once_with("Aatrox", True)

            # THEN: Result should be returned from PostgreSQL
            assert len(result) == 1
            assert result[0].enemy_name == "Picker1"
