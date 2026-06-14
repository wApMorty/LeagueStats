"""
Regression test for bug: AttributeError when warm_cache() called with custom pool.

Bug description:
    When DraftMonitor selected a custom pool and called warm_cache(), the Assistant
    attempted to call self.db.get_reverse_matchups_for_draft(champion) which was
    missing from the active data source, causing an AttributeError.

    Error: AttributeError: object has no attribute 'get_reverse_matchups_for_draft'

Fixed in: TODO #3 (2026-02-15)
    - Ensured get_reverse_matchups_for_draft() is part of the data source contract
    - Enables bidirectional cache warmup for pool champions

Updated: 2026-06-14 (Horizon 2)
    - Remote PostgreSQL/Neon data layer decommissioned; the regression is now
      asserted against the generic DataSource contract used by Assistant.

Test approach:
    Verify that warm_cache() can successfully pre-load matchups for all champions
    in a custom pool without raising AttributeError, and that the reverse matchup
    method is properly called for each champion.
"""

import pytest
from unittest.mock import Mock

from src.assistant import Assistant
from src.models import MatchupDraft


@pytest.fixture
def mock_data_source():
    """Mock data source with all required methods for warm_cache()."""
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
def assistant_with_mock_db(mock_data_source):
    """Create Assistant instance with mocked data source via dependency injection."""
    # Use dependency injection to provide mock database (no patching needed)
    assistant = Assistant(data_source=mock_data_source, verbose=False)
    return assistant


class TestWarmCacheWithCustomPool:
    """Tests for warm_cache() with custom champion pools (regression for bug #9)."""

    def test_warm_cache_with_pool_selection(self, assistant_with_mock_db):
        """
        Regression test: warm_cache() should work with custom pool selection.

        Before fix: AttributeError: object has no attribute 'get_reverse_matchups_for_draft'
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
