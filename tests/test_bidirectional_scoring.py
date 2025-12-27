"""Tests for bidirectional advantage calculation in scoring.py."""

import pytest
from src.analysis.scoring import ChampionScorer


class TestBidirectionalAdvantage:
    """Tests for bidirectional advantage calculation in score_against_team."""

    def test_symmetric_matchup_reduces_advantage(self, db, scorer, insert_matchup):
        """
        Test symmetric matchup where both sides have similar advantages.

        Scenario: Aatrox vs Darius
        - Aatrox perspective: +200 delta2 (Aatrox favored)
        - Darius perspective: +150 delta2 (Darius also favored - asymmetric data)

        Bidirectional should show smaller net advantage than unidirectional.
        """
        # Insert Aatrox matchup vs Darius (Aatrox perspective)
        insert_matchup("Aatrox", "Darius", 53.0, 100, 200, 10.0, 2000)

        # Insert Darius matchup vs Aatrox (Darius perspective - also favored!)
        insert_matchup("Darius", "Aatrox", 52.0, 80, 150, 10.0, 2000)

        # Get Aatrox matchups
        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        # Calculate bidirectional advantage for Aatrox vs Darius
        result = scorer.score_against_team(
            aatrox_matchups,
            ["Darius"],
            champion_name="Aatrox"
        )

        # Our advantage from delta2=200
        our_adv = scorer.delta2_to_win_advantage(200, "Aatrox")

        # Opponent advantage from delta2=150
        opp_adv = scorer.delta2_to_win_advantage(150, "Darius")

        # Net should be our_adv - opp_adv
        expected_net = our_adv - opp_adv

        assert abs(result - expected_net) < 0.01
        # Result should be less than pure our_adv (bidirectional reduces it)
        assert result < our_adv

    def test_asymmetric_matchup_amplifies_advantage(self, db, scorer, insert_matchup):
        """
        Test asymmetric matchup where we dominate and they struggle.

        Scenario: Aatrox vs Teemo
        - Aatrox perspective: +300 delta2 (strongly favored)
        - Teemo perspective: -250 delta2 (Teemo struggling vs Aatrox)

        Bidirectional should amplify advantage (both perspectives agree).
        Note: Result is capped at +10% due to conservative bounds.
        """
        # Aatrox dominates Teemo
        insert_matchup("Aatrox", "Teemo", 58.0, 200, 300, 8.0, 1500)

        # Teemo struggles vs Aatrox (negative delta2)
        insert_matchup("Teemo", "Aatrox", 42.0, -180, -250, 8.0, 1500)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["Teemo"],
            champion_name="Aatrox"
        )

        # Our advantage (bounded at +10%)
        our_adv = scorer.delta2_to_win_advantage(300, "Aatrox")
        assert our_adv == 10.0

        # Opponent advantage (bounded at -10%)
        opp_adv = scorer.delta2_to_win_advantage(-250, "Teemo")
        assert opp_adv == -10.0

        # Net would be +20% but capped at +10%
        # Since both perspectives agree we dominate, result should be max positive
        assert result == 10.0

    def test_multiple_enemies_average_calculation(self, db, scorer, insert_matchup):
        """
        Test bidirectional calculation with multiple enemies.

        Calculates average opponent advantage across all enemies.
        """
        # Aatrox vs 3 enemies
        insert_matchup("Aatrox", "Darius", 52.0, 50, 100, 10.0, 2000)
        insert_matchup("Aatrox", "Garen", 54.0, 100, 200, 12.0, 2500)
        insert_matchup("Aatrox", "Sett", 48.0, -80, -150, 8.0, 1800)

        # Reverse matchups
        insert_matchup("Darius", "Aatrox", 51.0, 30, 80, 10.0, 2000)
        insert_matchup("Garen", "Aatrox", 49.0, -50, -100, 12.0, 2500)
        insert_matchup("Sett", "Aatrox", 53.0, 120, 180, 8.0, 1800)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["Darius", "Garen", "Sett"],
            champion_name="Aatrox"
        )

        # Our average delta2: (100 + 200 - 150) / 3 = 50
        our_avg_delta2 = (100 + 200 - 150) / 3
        our_adv = scorer.delta2_to_win_advantage(our_avg_delta2, "Aatrox")

        # Opponent average delta2: (80 - 100 + 180) / 3 = 53.33
        opp_avg_delta2 = (80 - 100 + 180) / 3
        opp_adv = scorer.delta2_to_win_advantage(opp_avg_delta2, "Aatrox")

        expected_net = our_adv - opp_adv

        assert abs(result - expected_net) < 0.01

    def test_missing_opponent_data_graceful_degradation(self, db, scorer, insert_matchup):
        """
        Test graceful handling when opponent has no matchup data.

        Should treat missing opponent advantage as 0 (neutral).
        """
        # Only Aatrox has matchup data
        insert_matchup("Aatrox", "NewChampion", 52.0, 80, 150, 7.0, 1200)

        # NewChampion has NO reverse matchup data (not in database)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["NewChampion"],
            champion_name="Aatrox"
        )

        # Should be: our_advantage - 0 (no opponent data)
        our_adv = scorer.delta2_to_win_advantage(150, "Aatrox")

        assert abs(result - our_adv) < 0.01

    def test_partial_opponent_data(self, db, scorer, insert_matchup):
        """
        Test when only some enemies have reverse matchup data.

        Should average only available opponent advantages and not crash.
        """
        # Aatrox vs 3 enemies
        insert_matchup("Aatrox", "Darius", 52.0, 10, 20, 10.0, 2000)
        insert_matchup("Aatrox", "Garen", 54.0, 20, 30, 12.0, 2500)
        insert_matchup("Aatrox", "Yasuo", 48.0, -10, -15, 9.0, 1900)

        # Only 2 reverse matchups (Yasuo missing)
        insert_matchup("Darius", "Aatrox", 51.0, 5, 10, 10.0, 2000)
        insert_matchup("Garen", "Aatrox", 49.0, -10, -20, 12.0, 2500)
        # Yasuo has no reverse data - should be handled gracefully

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        # Should not crash with partial opponent data
        result = scorer.score_against_team(
            aatrox_matchups,
            ["Darius", "Garen", "Yasuo"],
            champion_name="Aatrox"
        )

        # Result should be valid (within bounds)
        assert -10.0 <= result <= 10.0

        # With partial favorable matchups, should be positive
        assert result > 0

    def test_blind_pick_unchanged(self, db, scorer, insert_matchup):
        """
        Test blind pick scenario (empty enemy team).

        Should use avg_delta2 without bidirectional calculation.
        """
        insert_matchup("Aatrox", "Darius", 52.0, 50, 100, 10.0, 2000)
        insert_matchup("Aatrox", "Garen", 54.0, 100, 200, 15.0, 2500)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        # Empty team = blind pick
        result = scorer.score_against_team(
            aatrox_matchups,
            [],
            champion_name="Aatrox"
        )

        # Should use weighted average (by pickrate)
        # Weighted avg = (100*10 + 200*15) / (10+15) = 160
        weighted_avg = (100 * 10 + 200 * 15) / (10 + 15)
        expected = scorer.delta2_to_win_advantage(weighted_avg, "Aatrox")

        assert abs(result - expected) < 0.01

    def test_bounds_still_applied(self, db, scorer, insert_matchup):
        """
        Test that conservative bounds (-10%, +10%) are still applied to net advantage.
        """
        # Extreme matchup with very high delta2 values
        insert_matchup("Aatrox", "Teemo", 70.0, 800, 1000, 5.0, 1000)
        insert_matchup("Teemo", "Aatrox", 30.0, -800, -1000, 5.0, 1000)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["Teemo"],
            champion_name="Aatrox"
        )

        # Even with extreme values, result should be bounded
        assert result >= -10.0
        assert result <= 10.0

    def test_no_champion_name_returns_zero(self, db, scorer, sample_matchups):
        """Test that missing champion_name returns 0 (existing behavior)."""
        result = scorer.score_against_team(
            sample_matchups,
            ["Darius"],
            champion_name=None
        )

        assert result == 0.0
