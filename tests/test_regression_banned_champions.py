"""
Regression test for banned champions bug in Live Coach.

Bug description:
    The Live Coach was recommending champions that were already banned.
    This happened because remaining_matchups included matchups against
    banned champions when calculating avg_delta2 for blind picks.

Fixed in: PR #XX commit XXXXXXX

Test approach:
    Verify that banned champions are excluded from remaining matchup pool
    when calculating scores for unknown enemy picks (blind picks).
"""

import pytest
from src.models import Matchup


def test_banned_champions_excluded_from_blind_pick_calculation(scorer):
    """
    Regression test: Banned champions should be excluded from avg_delta2 calculation.

    Scenario:
        - Champion A has matchups against enemies B, C, D, E, F
        - Enemy team reveals: B (only 1 enemy known, 4 blind picks remaining)
        - Champions C and D are BANNED
        - Expected: avg_delta2 for blind picks should only include E and F (not C or D)
    """
    # Create matchups for ChampionA vs 5 enemies
    # Format: Matchup(enemy_name, winrate, delta1, delta2, pickrate, games)
    matchups = [
        Matchup("EnemyB", 52.0, 100.0, 100.0, 10.0, 1000),  # Known enemy (revealed)
        Matchup("EnemyC", 45.0, -200.0, -200.0, 15.0, 1000),  # BANNED - should be excluded
        Matchup("EnemyD", 48.0, -100.0, -100.0, 12.0, 1000),  # BANNED - should be excluded
        Matchup("EnemyE", 51.0, 50.0, 50.0, 11.0, 1000),  # Available for blind pick
        Matchup("EnemyF", 53.0, 150.0, 150.0, 13.0, 1000),  # Available for blind pick
    ]

    # Test WITHOUT banned champions (baseline)
    team_without_bans = ["EnemyB"]  # 1 known enemy, 4 blind picks
    score_without_bans = scorer.score_against_team(
        matchups, team_without_bans, "ChampionA", banned_champions=None
    )

    # Test WITH banned champions
    banned = ["EnemyC", "EnemyD"]  # Ban the two worst matchups
    score_with_bans = scorer.score_against_team(
        matchups, team_without_bans, "ChampionA", banned_champions=banned
    )

    # Assert: Score should IMPROVE when bad matchups are banned
    # Because avg_delta2 for blind picks excludes EnemyC (-200) and EnemyD (-100)
    # and only includes EnemyE (+50) and EnemyF (+150)
    assert score_with_bans > score_without_bans, (
        f"Score should improve when bad matchups are banned. "
        f"Without bans: {score_without_bans:.2f}, With bans: {score_with_bans:.2f}"
    )

    # Assert: The improvement should be significant (at least 0.5%)
    improvement = score_with_bans - score_without_bans
    assert improvement >= 0.5, (
        f"Improvement should be at least 0.5% when two bad matchups are banned. "
        f"Got: {improvement:.2f}%"
    )


def test_banned_champions_pure_blind_pick(scorer):
    """
    Regression test: Banned champions excluded from pure blind pick (no enemies revealed).

    Scenario:
        - Champion A has matchups against enemies B, C, D, E, F
        - No enemy team revealed yet (pure blind pick)
        - Champions C and D are BANNED
        - Expected: avg_delta2 should only include B, E, F (not C or D)
    """
    # Create matchups with clear delta2 values
    matchups = [
        Matchup("EnemyB", 51.0, 50.0, 50.0, 10.0, 1000),  # Available
        Matchup("EnemyC", 45.0, -200.0, -200.0, 15.0, 1000),  # BANNED - worst matchup
        Matchup("EnemyD", 48.0, -100.0, -100.0, 12.0, 1000),  # BANNED - bad matchup
        Matchup("EnemyE", 51.0, 50.0, 50.0, 11.0, 1000),  # Available
        Matchup("EnemyF", 53.0, 150.0, 150.0, 13.0, 1000),  # Available - best matchup
    ]

    # Pure blind pick (no enemies revealed)
    empty_team = []

    # Test WITHOUT bans
    score_without_bans = scorer.score_against_team(
        matchups, empty_team, "ChampionA", banned_champions=None
    )

    # Test WITH bans
    banned = ["EnemyC", "EnemyD"]
    score_with_bans = scorer.score_against_team(
        matchups, empty_team, "ChampionA", banned_champions=banned
    )

    # Assert: Score should improve significantly when worst matchups are banned
    assert score_with_bans > score_without_bans, (
        f"Pure blind pick score should improve when bad matchups are banned. "
        f"Without bans: {score_without_bans:.2f}, With bans: {score_with_bans:.2f}"
    )

    improvement = score_with_bans - score_without_bans
    assert improvement >= 1.0, (
        f"Improvement should be at least 1.0% in pure blind pick when two worst matchups banned. "
        f"Got: {improvement:.2f}%"
    )


def test_banned_champions_case_insensitive(scorer):
    """
    Regression test: Banned champion filtering should be case-insensitive.

    Scenario:
        - Matchup data uses "EnemyC" (capitalized)
        - Banned list uses "enemyc" (lowercase)
        - Expected: EnemyC should still be filtered out
    """
    matchups = [
        Matchup("EnemyB", 51.0, 50.0, 50.0, 10.0, 1000),
        Matchup("EnemyC", 45.0, -200.0, -200.0, 15.0, 1000),  # Should be filtered
    ]

    # Test with case mismatch
    banned_lowercase = ["enemyc"]  # lowercase
    score = scorer.score_against_team(matchups, [], "ChampionA", banned_champions=banned_lowercase)

    # Calculate expected score (should only include EnemyB)
    # Since EnemyC is banned, avg_delta2 should only use EnemyB's delta2 (50.0)
    expected_advantage = scorer.delta2_to_win_advantage(50.0, "ChampionA")

    # Assert: Score should match expected (case-insensitive filtering worked)
    assert abs(score - expected_advantage) < 0.1, (
        f"Case-insensitive filtering failed. "
        f"Expected: {expected_advantage:.2f}, Got: {score:.2f}"
    )


def test_no_banned_champions_backward_compatibility(scorer):
    """
    Regression test: Passing None or empty list for banned_champions should work.

    Scenario:
        - Ensure backward compatibility when banned_champions is not provided
        - Should behave exactly like the old code (no filtering)
    """
    matchups = [
        Matchup("EnemyB", 52.0, 100.0, 100.0, 10.0, 1000),
        Matchup("EnemyC", 45.0, -200.0, -200.0, 15.0, 1000),
    ]

    team = ["EnemyB"]

    # Test with None (default)
    score_none = scorer.score_against_team(matchups, team, "ChampionA", banned_champions=None)

    # Test with empty list
    score_empty = scorer.score_against_team(matchups, team, "ChampionA", banned_champions=[])

    # Test without parameter (relies on default)
    score_default = scorer.score_against_team(matchups, team, "ChampionA")

    # Assert: All three should give identical results
    assert abs(score_none - score_empty) < 0.01, "None and empty list should give same result"
    assert abs(score_none - score_default) < 0.01, "None and default should give same result"
