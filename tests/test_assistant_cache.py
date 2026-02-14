"""Regression tests for bidirectional cache system in Assistant class.

Feature: Bidirectional Cache System (Task #16 - Sprint 2)
--------------------------------------------------------
The Assistant class implements a bidirectional cache for matchup lookups:
1. Direct cache: champion (as picker) -> [(enemy, delta2, ...)]
2. Reverse cache: champion (as enemy) -> [(picker, delta2, ...)]

This enables 99% faster lookups for ban recommendations (reverse queries).

Key Methods Tested:
- warm_cache(): Loads both direct and reverse caches from database
- get_cached_matchup_delta2(): Bidirectional lookup (direct -> reverse -> SQL)
- clear_cache(): Clears both caches and resets statistics
- print_cache_stats(): Displays bidirectional cache statistics

Author: QA Expert (Claude Sonnet 4.5)
Created: 2026-02-14
Sprint: 2 - Tâche #16 (Support des Synergies)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from src.assistant import Assistant
from src.models import MatchupDraft


class TestAssistantCacheBidirectional:
    """Test suite for bidirectional cache implementation in Assistant."""

    @pytest.fixture
    def mock_db(self):
        """Mock database with get_champion_matchups_for_draft and get_reverse_matchups_for_draft."""
        db = Mock()

        # Mock methods that warm_cache() will call
        db.get_champion_matchups_for_draft = Mock(return_value=[])
        db.get_reverse_matchups_for_draft = Mock(return_value=[])
        db.get_matchup_delta2 = Mock(return_value=None)

        # Mock close method
        db.close = Mock()

        return db

    @pytest.fixture
    def assistant(self, mock_db):
        """Create Assistant instance with mocked database via dependency injection."""
        # Use dependency injection to provide mock database
        asst = Assistant(data_source=mock_db, verbose=False)
        return asst

    # ==================== Initialization Tests ====================

    def test_cache_initialization(self, assistant):
        """Test that both caches are initialized empty on startup.

        Expected state after Assistant creation:
        - _matchups_cache: empty dict {}
        - _reverse_cache: empty dict {}
        - _cache_enabled: False
        - _cache_hits: 0
        - _cache_misses: 0
        """
        assert assistant._matchups_cache == {}
        assert assistant._reverse_cache == {}
        assert assistant._cache_enabled is False
        assert assistant._cache_hits == 0
        assert assistant._cache_misses == 0

    # ==================== Direct Cache Tests ====================

    def test_warm_cache_direct(self, assistant, mock_db):
        """Test direct cache loading (champion as picker -> enemies).

        Scenario: warm_cache(["Darius"]) should call:
        1. db.get_champion_matchups_for_draft("Darius")
        2. db.get_reverse_matchups_for_draft("Darius")

        Result: Direct cache contains Darius with 2 matchups
        """
        # Setup: Mock direct matchups (Darius picks against Jax and Fiora)
        mock_db.get_champion_matchups_for_draft.return_value = [
            MatchupDraft(enemy_name="Jax", delta2=2.5, pickrate=5.0, games=500),
            MatchupDraft(enemy_name="Fiora", delta2=-1.2, pickrate=3.0, games=300),
        ]

        # Setup: Mock reverse matchups (empty for this test)
        mock_db.get_reverse_matchups_for_draft.return_value = []

        # Execute: Warm cache for Darius
        assistant.warm_cache(["Darius"])

        # Verify: Direct cache loaded
        assert "Darius" in assistant._matchups_cache
        assert len(assistant._matchups_cache["Darius"]) == 2

        # Verify: Cache enabled
        assert assistant._cache_enabled is True

        # Verify: DB methods called once each
        mock_db.get_champion_matchups_for_draft.assert_called_once_with("Darius")
        mock_db.get_reverse_matchups_for_draft.assert_called_once_with("Darius")

    # ==================== Reverse Cache Tests ====================

    def test_warm_cache_reverse(self, assistant, mock_db):
        """Test reverse cache loading (champion as enemy -> pickers).

        Scenario: warm_cache(["Darius"]) should also load reverse matchups.
        Reverse matchups = Champions that PICK AGAINST Darius.

        Result: Reverse cache contains Darius with 2 champions that counter him
        """
        # Setup: Mock direct matchups (empty for this test)
        mock_db.get_champion_matchups_for_draft.return_value = []

        # Setup: Mock reverse matchups (Jax and Camille pick against Darius)
        mock_db.get_reverse_matchups_for_draft.return_value = [
            MatchupDraft(enemy_name="Jax", delta2=3.0, pickrate=6.0, games=600),
            MatchupDraft(enemy_name="Camille", delta2=2.0, pickrate=4.0, games=400),
        ]

        # Execute: Warm cache for Darius
        assistant.warm_cache(["Darius"])

        # Verify: Reverse cache loaded
        assert "Darius" in assistant._reverse_cache
        assert len(assistant._reverse_cache["Darius"]) == 2

        # Verify: Cache enabled
        assert assistant._cache_enabled is True

    def test_warm_cache_both_caches(self, assistant, mock_db):
        """Test that warm_cache() loads BOTH direct and reverse caches.

        Scenario: Champion pool has 2 champions (Darius, Garen)
        Each champion has both direct and reverse matchups.

        Result: Both caches contain both champions
        """
        # Setup: Mock direct matchups
        mock_db.get_champion_matchups_for_draft.side_effect = [
            # Darius direct matchups
            [MatchupDraft(enemy_name="Jax", delta2=2.5, pickrate=5.0, games=500)],
            # Garen direct matchups
            [MatchupDraft(enemy_name="Teemo", delta2=-3.0, pickrate=4.0, games=400)],
        ]

        # Setup: Mock reverse matchups
        mock_db.get_reverse_matchups_for_draft.side_effect = [
            # Darius reverse matchups (who picks against Darius)
            [MatchupDraft(enemy_name="Fiora", delta2=2.0, pickrate=3.0, games=300)],
            # Garen reverse matchups (who picks against Garen)
            [MatchupDraft(enemy_name="Quinn", delta2=1.5, pickrate=2.5, games=250)],
        ]

        # Execute: Warm cache for both champions
        assistant.warm_cache(["Darius", "Garen"])

        # Verify: Direct cache has both champions
        assert "Darius" in assistant._matchups_cache
        assert "Garen" in assistant._matchups_cache

        # Verify: Reverse cache has both champions
        assert "Darius" in assistant._reverse_cache
        assert "Garen" in assistant._reverse_cache

        # Verify: Cache enabled
        assert assistant._cache_enabled is True

    # ==================== Bidirectional Lookup Tests ====================

    def test_get_cached_matchup_delta2_direct_hit(self, assistant):
        """Test bidirectional lookup with direct cache hit.

        Scenario: Direct cache contains Darius -> Jax with delta2=2.5
        Query: get_cached_matchup_delta2("Darius", "Jax")

        Expected: Returns 2.5 from direct cache (no SQL)
        """
        # Setup: Fill direct cache manually with TUPLES (enemy_name, delta2, pickrate, games)
        assistant._matchups_cache["Darius"] = [
            ("Jax", 2.5, 5.0, 500),
            ("Fiora", -1.2, 3.0, 300),
        ]
        assistant._cache_enabled = True

        # Execute: Get delta2 (should hit direct cache)
        delta2 = assistant.get_cached_matchup_delta2("Darius", "Jax")

        # Verify: Returns correct delta2
        assert delta2 == 2.5

        # Verify: Cache hit recorded
        assert assistant._cache_hits == 1
        assert assistant._cache_misses == 0

    def test_get_cached_matchup_delta2_reverse_hit(self, assistant):
        """Test bidirectional lookup with reverse cache hit (inverted delta2).

        Scenario: Reverse cache contains Jax -> Darius with delta2=3.0
        This means: When Jax picks against Darius, Jax has +3.0 delta2

        Query: get_cached_matchup_delta2("Darius", "Jax")
        Expected: Returns -3.0 (INVERTED from reverse cache perspective)

        Why inversion?
        - Reverse cache stores: "Jax picks against Darius" = +3.0 (from Jax's view)
        - We query: "Darius vs Jax" = -3.0 (from Darius's view, opposite sign)
        """
        # Setup: Fill reverse cache with TUPLES (enemy_name, delta2, pickrate, games)
        assistant._reverse_cache["Jax"] = [
            ("Darius", 3.0, 6.0, 600),
            ("Garen", 2.0, 4.0, 400),
        ]
        assistant._cache_enabled = True

        # Execute: Get delta2 (should hit reverse cache and invert)
        delta2 = assistant.get_cached_matchup_delta2("Darius", "Jax")

        # Verify: Returns INVERTED delta2
        assert delta2 == -3.0

        # Verify: Cache hit recorded
        assert assistant._cache_hits == 1
        assert assistant._cache_misses == 0

    def test_get_cached_matchup_delta2_miss_fallback_sql(self, assistant, mock_db):
        """Test bidirectional lookup with cache miss (SQL fallback).

        Scenario: Cache is enabled but matchup not in either cache
        Query: get_cached_matchup_delta2("Darius", "Unknown")

        Expected: Falls back to db.get_matchup_delta2() and records cache miss
        """
        # Setup: Cache enabled but champion not in cache
        assistant._cache_enabled = True
        assistant._matchups_cache = {"Garen": []}  # Different champion
        assistant._reverse_cache = {}

        # Setup: Mock SQL fallback
        mock_db.get_matchup_delta2.return_value = 1.5

        # Execute: Get delta2 (should miss cache and fallback to SQL)
        delta2 = assistant.get_cached_matchup_delta2("Darius", "Unknown")

        # Verify: Returns value from SQL
        assert delta2 == 1.5

        # Verify: Cache miss recorded
        assert assistant._cache_hits == 0
        assert assistant._cache_misses == 1

        # Verify: SQL method called
        mock_db.get_matchup_delta2.assert_called_once_with("Darius", "Unknown")

    def test_get_cached_matchup_delta2_cache_disabled(self, assistant, mock_db):
        """Test that lookups fallback to SQL when cache is disabled.

        Scenario: Cache is not enabled (cold start)
        Query: get_cached_matchup_delta2("Darius", "Jax")

        Expected: Directly calls SQL (no cache check)
        """
        # Setup: Cache disabled (default state)
        assert assistant._cache_enabled is False

        # Setup: Mock SQL fallback
        mock_db.get_matchup_delta2.return_value = 2.5

        # Execute: Get delta2 (should skip cache and use SQL)
        delta2 = assistant.get_cached_matchup_delta2("Darius", "Jax")

        # Verify: Returns value from SQL
        assert delta2 == 2.5

        # Verify: Cache miss recorded (because cache disabled = miss)
        assert assistant._cache_misses == 1

        # Verify: SQL method called
        mock_db.get_matchup_delta2.assert_called_once_with("Darius", "Jax")

    # ==================== Cache Statistics Tests ====================

    def test_cache_stats_multiple_hits_and_misses(self, assistant, mock_db):
        """Test cache statistics tracking with multiple hits and misses.

        Scenario:
        - 3 direct hits
        - 2 reverse hits
        - 1 cache miss

        Expected:
        - Total queries: 6
        - Cache hits: 5 (83.3%)
        - Cache misses: 1 (16.7%)
        """
        # Setup: Fill caches with TUPLES
        assistant._matchups_cache["Darius"] = [
            ("Jax", 2.5, 5.0, 500),
        ]
        assistant._reverse_cache["Fiora"] = [
            ("Darius", 3.0, 6.0, 600),
        ]
        assistant._cache_enabled = True
        mock_db.get_matchup_delta2.return_value = 0.0

        # Execute: 3 direct hits
        assistant.get_cached_matchup_delta2("Darius", "Jax")
        assistant.get_cached_matchup_delta2("Darius", "Jax")
        assistant.get_cached_matchup_delta2("Darius", "Jax")

        # Execute: 2 reverse hits
        assistant.get_cached_matchup_delta2("Darius", "Fiora")
        assistant.get_cached_matchup_delta2("Darius", "Fiora")

        # Execute: 1 cache miss
        assistant.get_cached_matchup_delta2("Darius", "Unknown")

        # Verify: Statistics correct
        assert assistant._cache_hits == 5
        assert assistant._cache_misses == 1

        # Verify: Total queries
        total = assistant._cache_hits + assistant._cache_misses
        assert total == 6

        # Verify: Hit rate
        hit_rate = (assistant._cache_hits / total) * 100
        assert hit_rate == pytest.approx(83.33, abs=0.01)

    # ==================== Clear Cache Tests ====================

    def test_clear_cache(self, assistant, capsys):
        """Test that both caches are cleared and statistics reset.

        Scenario: Caches are filled with data and have statistics
        Action: clear_cache()

        Expected:
        - Both caches cleared (empty dicts)
        - Cache disabled
        - Statistics reset to 0
        - Output message printed
        """
        # Setup: Fill caches with TUPLES
        assistant._matchups_cache = {
            "Darius": [("Jax", 2.5, 5.0, 500)],
            "Garen": [("Teemo", -3.0, 4.0, 400)],
        }
        assistant._reverse_cache = {
            "Jax": [("Darius", 3.0, 6.0, 600)],
            "Fiora": [("Garen", 2.0, 4.0, 400)],
        }
        assistant._cache_enabled = True
        assistant._cache_hits = 10
        assistant._cache_misses = 2

        # Execute: Clear cache
        assistant.clear_cache()

        # Verify: Both caches cleared
        assert assistant._matchups_cache == {}
        assert assistant._reverse_cache == {}

        # Verify: Cache disabled
        assert assistant._cache_enabled is False

        # Verify: Statistics reset
        assert assistant._cache_hits == 0
        assert assistant._cache_misses == 0

        # Verify: Output message contains expected text
        captured = capsys.readouterr()
        assert "2 direct + 2 reverse = 4 entries" in captured.out

    # ==================== Print Cache Stats Tests ====================

    def test_print_cache_stats(self, assistant, capsys):
        """Test cache stats output format with bidirectional cache.

        Scenario: Caches have data and statistics
        Action: print_cache_stats()

        Expected output should include:
        - Total queries
        - Cache hits with percentage
        - Cache misses
        - Direct cache entry count
        - Reverse cache entry count
        - Total cached entries
        """
        # Setup: Fill caches with TUPLES
        assistant._matchups_cache = {
            "Darius": [("Jax", 2.5, 5.0, 500)],
            "Garen": [("Teemo", -3.0, 4.0, 400)],
            "Jax": [("Fiora", 1.0, 3.0, 300)],
        }
        assistant._reverse_cache = {
            "Fiora": [("Darius", 3.0, 6.0, 600)],
            "Camille": [("Garen", 2.0, 4.0, 400)],
        }
        assistant._cache_hits = 95
        assistant._cache_misses = 5

        # Execute: Print stats
        assistant.print_cache_stats()

        # Verify: Output contains expected information
        captured = capsys.readouterr()
        output = captured.out

        # Check key metrics in output
        assert "Total queries: 100" in output
        assert "Cache hits: 95 (95.0%)" in output
        assert "Cache misses: 5" in output
        assert "Direct cache entries: 3 champions" in output
        assert "Reverse cache entries: 2 champions" in output
        assert "Total cached: 5 entries" in output

    def test_print_cache_stats_no_queries(self, assistant, capsys):
        """Test that print_cache_stats() outputs nothing when no queries made.

        Scenario: Cache has data but no queries yet
        Action: print_cache_stats()

        Expected: No output (total_queries == 0)
        """
        # Setup: Cache enabled but no queries
        assistant._matchups_cache = {"Darius": []}
        assistant._cache_hits = 0
        assistant._cache_misses = 0

        # Execute: Print stats
        assistant.print_cache_stats()

        # Verify: No output
        captured = capsys.readouterr()
        assert captured.out == ""

    # ==================== Edge Cases ====================

    def test_warm_cache_empty_pool(self, assistant):
        """Test warm_cache with empty pool (edge case).

        Scenario: warm_cache([])

        Expected: Returns immediately, no DB calls, cache stays disabled
        """
        # Execute: Warm cache with empty pool
        assistant.warm_cache([])

        # Verify: Cache stays disabled
        assert assistant._cache_enabled is False

        # Verify: Caches still empty
        assert assistant._matchups_cache == {}
        assert assistant._reverse_cache == {}

    def test_warm_cache_champion_with_no_matchups(self, assistant, mock_db):
        """Test warm_cache when champion has no matchup data.

        Scenario: Champion exists but has no matchups in database

        Expected: DB methods called but caches remain empty for that champion
        """
        # Setup: Mock returns empty lists
        mock_db.get_champion_matchups_for_draft.return_value = []
        mock_db.get_reverse_matchups_for_draft.return_value = []

        # Execute: Warm cache for champion with no data
        assistant.warm_cache(["Darius"])

        # Verify: Cache enabled (even if no data)
        assert assistant._cache_enabled is True

        # Verify: Champion NOT in caches (empty lists not stored)
        assert "Darius" not in assistant._matchups_cache
        assert "Darius" not in assistant._reverse_cache

        # Verify: DB methods called
        mock_db.get_champion_matchups_for_draft.assert_called_once_with("Darius")
        mock_db.get_reverse_matchups_for_draft.assert_called_once_with("Darius")

    def test_get_cached_matchup_delta2_multiple_entries_finds_correct_one(self, assistant):
        """Test that lookup finds correct matchup when cache has multiple entries.

        Scenario: Direct cache has multiple matchups for a champion
        Query: get_cached_matchup_delta2("Darius", "Fiora")

        Expected: Returns correct delta2 for Fiora (not first entry)
        """
        # Setup: Fill direct cache with multiple TUPLES
        assistant._matchups_cache["Darius"] = [
            ("Jax", 2.5, 5.0, 500),
            ("Fiora", -1.2, 3.0, 300),
            ("Camille", 1.0, 4.0, 400),
        ]
        assistant._cache_enabled = True

        # Execute: Get delta2 for second entry (Fiora)
        delta2 = assistant.get_cached_matchup_delta2("Darius", "Fiora")

        # Verify: Returns correct delta2 for Fiora
        assert delta2 == -1.2

        # Verify: Cache hit recorded
        assert assistant._cache_hits == 1

    def test_get_cached_matchup_delta2_not_found_in_cache(self, assistant, mock_db):
        """Test lookup when champion is in cache but enemy is not.

        Scenario: Direct cache has Darius matchups but not vs "Unknown"
        Query: get_cached_matchup_delta2("Darius", "Unknown")

        Expected: Falls back to SQL
        """
        # Setup: Fill direct cache with TUPLE (no "Unknown" enemy)
        assistant._matchups_cache["Darius"] = [
            ("Jax", 2.5, 5.0, 500),
        ]
        assistant._cache_enabled = True

        # Setup: Mock SQL fallback
        mock_db.get_matchup_delta2.return_value = 0.5

        # Execute: Get delta2 for unknown enemy
        delta2 = assistant.get_cached_matchup_delta2("Darius", "Unknown")

        # Verify: Returns value from SQL
        assert delta2 == 0.5

        # Verify: Cache miss recorded
        assert assistant._cache_misses == 1

        # Verify: SQL method called
        mock_db.get_matchup_delta2.assert_called_once_with("Darius", "Unknown")

    def test_reverse_cache_inversion_correctness(self, assistant):
        """Test that reverse cache delta2 inversion is mathematically correct.

        Scenario:
        - Reverse cache: Jax vs Darius = +4.0 (Jax's perspective)
        - Query: Darius vs Jax

        Expected: Returns -4.0 (Darius's perspective, inverted sign)

        Mathematical proof:
        If Jax has +4.0 delta2 against Darius,
        then Darius has -4.0 delta2 against Jax (zero-sum matchup)
        """
        # Setup: Fill reverse cache with TUPLE (Jax picks against Darius with +4.0)
        assistant._reverse_cache["Jax"] = [
            ("Darius", 4.0, 6.0, 600),
        ]
        assistant._cache_enabled = True

        # Execute: Query from Darius's perspective
        delta2 = assistant.get_cached_matchup_delta2("Darius", "Jax")

        # Verify: Delta2 is inverted (negative)
        assert delta2 == -4.0

        # Verify: Cache hit recorded
        assert assistant._cache_hits == 1

        # Mathematical verification
        assert delta2 + 4.0 == 0.0  # Zero-sum property

    def test_cache_priority_direct_before_reverse(self, assistant):
        """Test that direct cache is checked BEFORE reverse cache.

        Scenario: Both caches have data for same matchup
        - Direct: Darius -> Jax = 2.5
        - Reverse: Jax -> Darius = -2.0 (would invert to +2.0)

        Query: get_cached_matchup_delta2("Darius", "Jax")

        Expected: Returns 2.5 from DIRECT cache (higher priority)
        """
        # Setup: Fill BOTH caches with TUPLES (conflicting data)
        assistant._matchups_cache["Darius"] = [
            ("Jax", 2.5, 5.0, 500),
        ]
        assistant._reverse_cache["Jax"] = [
            ("Darius", -2.0, 6.0, 600),
        ]
        assistant._cache_enabled = True

        # Execute: Get delta2
        delta2 = assistant.get_cached_matchup_delta2("Darius", "Jax")

        # Verify: Returns value from DIRECT cache (priority)
        assert delta2 == 2.5

        # Verify: Only one cache hit (stopped at direct cache)
        assert assistant._cache_hits == 1
