"""Regression test for ban recommendations format bug.

Bug: Ban recommendations displayed non-integer champion counts (e.g., "Counters 2.45/5")
because get_ban_recommendations() returned best_response_delta2 (float) as the 3rd element
instead of matchups_count (int).

Fixed in: PR #XX (2026-01-14)

This test ensures the format returned by get_ban_recommendations() matches the format
expected by the database and display code.
"""

import pytest
from src.db import Database
from src.assistant import Assistant


@pytest.fixture
def temp_db_with_data(db, insert_matchup):
    """Create a database with test matchup data."""
    # Insert matchups using the insert_matchup helper
    # TestChampion1 has bad matchup vs EnemyChampion1 (countered)
    insert_matchup("TestChampion1", "EnemyChampion1", 45.0, -150.0, -200.0, 10.0, 1000)
    # TestChampion1 has good matchup vs EnemyChampion2
    insert_matchup("TestChampion1", "EnemyChampion2", 52.0, 100.0, 180.0, 8.0, 1000)

    # TestChampion2 has bad matchup vs EnemyChampion1 (countered)
    insert_matchup("TestChampion2", "EnemyChampion1", 46.0, -140.0, -160.0, 10.0, 1000)
    # TestChampion2 has neutral matchup vs EnemyChampion2
    insert_matchup("TestChampion2", "EnemyChampion2", 50.0, 0.0, 0.0, 8.0, 1000)

    return db


def test_ban_recommendations_format_has_five_elements(temp_db_with_data):
    """Test that get_ban_recommendations() returns tuples with exactly 5 elements."""
    assistant = Assistant(temp_db_with_data, verbose=False)
    pool = ["TestChampion1", "TestChampion2"]

    # Get ban recommendations
    ban_recommendations = assistant.get_ban_recommendations(pool, num_bans=2)

    # Verify we got results
    assert len(ban_recommendations) > 0, "Should return at least one ban recommendation"

    # Verify each tuple has exactly 5 elements
    for recommendation in ban_recommendations:
        assert (
            len(recommendation) == 5
        ), f"Ban recommendation tuple should have 5 elements, got {len(recommendation)}: {recommendation}"


def test_ban_recommendations_format_element_types(temp_db_with_data):
    """Test that get_ban_recommendations() returns correct types for each element."""
    assistant = Assistant(temp_db_with_data, verbose=False)
    pool = ["TestChampion1", "TestChampion2"]

    # Get ban recommendations
    ban_recommendations = assistant.get_ban_recommendations(pool, num_bans=2)

    assert len(ban_recommendations) > 0, "Should return at least one ban recommendation"

    for enemy_name, threat_score, best_delta2, best_champion, matchups_count in ban_recommendations:
        # Element 1: enemy_name should be string
        assert isinstance(enemy_name, str), f"enemy_name should be str, got {type(enemy_name)}"

        # Element 2: threat_score should be numeric (int or float)
        assert isinstance(
            threat_score, (int, float)
        ), f"threat_score should be numeric, got {type(threat_score)}"

        # Element 3: best_delta2 should be numeric (int or float)
        assert isinstance(
            best_delta2, (int, float)
        ), f"best_delta2 should be numeric, got {type(best_delta2)}"

        # Element 4: best_champion should be string
        assert isinstance(
            best_champion, str
        ), f"best_champion should be str, got {type(best_champion)}"

        # Element 5: matchups_count should be integer (CRITICAL - this was the bug)
        assert isinstance(
            matchups_count, int
        ), f"matchups_count should be int (not float!), got {type(matchups_count)}: {matchups_count}"


def test_ban_recommendations_matchups_count_is_integer_not_float(temp_db_with_data):
    """Regression test: Verify matchups_count is integer, not float (the bug).

    Before fix: matchups_count was actually best_response_delta2 (float like 2.45)
    After fix: matchups_count is the actual integer count of matchups (like 2)
    """
    assistant = Assistant(temp_db_with_data, verbose=False)
    pool = ["TestChampion1", "TestChampion2"]

    # Get ban recommendations
    ban_recommendations = assistant.get_ban_recommendations(pool, num_bans=2)

    assert len(ban_recommendations) > 0, "Should return at least one ban recommendation"

    for enemy_name, threat_score, best_delta2, best_champion, matchups_count in ban_recommendations:
        # The bug: matchups_count was a float (best_response_delta2)
        # After fix: matchups_count must be an integer
        assert isinstance(matchups_count, int), (
            f"BUG DETECTED: matchups_count for {enemy_name} is {type(matchups_count).__name__} "
            f"({matchups_count}), should be int. This means best_response_delta2 is being "
            f"returned as matchups_count!"
        )

        # Additionally verify it's a reasonable count (0 to pool size)
        assert (
            0 <= matchups_count <= len(pool)
        ), f"matchups_count should be between 0 and {len(pool)}, got {matchups_count}"


def test_ban_recommendations_format_matches_database_format(temp_db_with_data):
    """Test that format matches get_pool_ban_recommendations() from database."""
    assistant = Assistant(temp_db_with_data, verbose=False)
    pool = ["TestChampion1", "TestChampion2"]

    # Pre-calculate bans and store in database
    pool_name = "TestPool"
    success = assistant.precalculate_pool_bans(pool_name, pool)
    assert success, "Failed to pre-calculate bans"

    # Get bans from database
    db_bans = temp_db_with_data.get_pool_ban_recommendations(pool_name, limit=5)

    # Get bans from real-time calculation
    realtime_bans = assistant.get_ban_recommendations(pool, num_bans=5)

    # Both should have same structure (5 elements per tuple)
    if db_bans:
        assert all(
            len(ban) == 5 for ban in db_bans
        ), "Database bans should have 5 elements per tuple"

    if realtime_bans:
        assert all(
            len(ban) == 5 for ban in realtime_bans
        ), "Real-time bans should have 5 elements per tuple"

    # Element types should match
    for db_ban, rt_ban in zip(db_bans, realtime_bans):
        assert type(db_ban[0]) == type(rt_ban[0]), "Element 1 (enemy_name) type mismatch"
        assert type(db_ban[1]) == type(rt_ban[1]), "Element 2 (threat_score) type mismatch"
        assert type(db_ban[2]) == type(rt_ban[2]), "Element 3 (best_delta2) type mismatch"
        assert type(db_ban[3]) == type(rt_ban[3]), "Element 4 (best_champion) type mismatch"
        assert type(db_ban[4]) == type(rt_ban[4]), "Element 5 (matchups_count) type mismatch"
