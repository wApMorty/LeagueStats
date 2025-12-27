"""Tests for bidirectional advantage calculation in scoring.py."""

import pytest
from src.analysis.scoring import ChampionScorer


class TestBidirectionalAdvantage:
    """Tests for bidirectional advantage calculation in score_against_team."""

    def test_symmetric_matchup_reduces_advantage(self, db, scorer, insert_matchup):
        """
        Test symmetric matchup where both sides have similar advantages.

        Scenario: Aatrox vs Darius
        - Aatrox perspective: +100 delta2 (Aatrox strongly favored)
        - Darius perspective: +10 delta2 (Darius slightly favored - asymmetric data)

        Bidirectional should show reduced advantage due to opponent's perspective.
        With 1 known enemy + 4 blind picks, our delta2 is diluted: (100+0*4)/5 = 20
        """
        # Insert Aatrox matchup vs Darius (Aatrox perspective - strong advantage)
        insert_matchup("Aatrox", "Darius", 58.0, 50, 100, 10.0, 2000)

        # Insert Darius matchup vs Aatrox (Darius perspective - weak advantage)
        insert_matchup("Darius", "Aatrox", 51.0, 5, 10, 10.0, 2000)

        # Get Aatrox matchups
        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        # Calculate bidirectional advantage for Aatrox vs Darius
        result = scorer.score_against_team(
            aatrox_matchups,
            ["Darius"],
            champion_name="Aatrox"
        )

        # With blind pick dilution: our_avg_delta2 = 100/5 = 20
        our_diluted_adv = scorer.delta2_to_win_advantage(20, "Aatrox")

        # Opponent advantage from delta2=10 (no dilution)
        opp_adv = scorer.delta2_to_win_advantage(10, "Darius")

        # Net should be positive but reduced by opponent advantage
        assert result > 0
        assert result < our_diluted_adv  # Reduced by opponent's advantage

    def test_asymmetric_matchup_amplifies_advantage(self, db, scorer, insert_matchup):
        """
        Test asymmetric matchup where we dominate and they struggle.

        Scenario: Aatrox vs Teemo
        - Aatrox perspective: +300 delta2 (strongly favored)
        - Teemo perspective: -250 delta2 (Teemo struggling vs Aatrox)

        Bidirectional should amplify advantage (both perspectives agree).
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

        # Our advantage (no bounds)
        our_adv = scorer.delta2_to_win_advantage(300, "Aatrox")

        # Since both perspectives agree we dominate, result should be very high
        assert result > our_adv  # Amplified by opponent's negative advantage
        assert result > 15.0  # Should be significantly positive

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

        # With mixed matchups (some favorable, some not), result should be moderate
        assert isinstance(result, float)
        # Net effect of bidirectional should reduce our advantage slightly
        assert result < 10.0  # Not too extreme

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
        # Result should be positive (we have favorable matchup)
        assert result > 0
        # With delta2=150, should be a strong advantage
        assert result > 20.0

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

        # Result should be a valid float
        assert isinstance(result, float)

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

    def test_extreme_delta2_values(self, db, scorer, insert_matchup):
        """
        Test handling of extreme delta2 values with bidirectional calculation.
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

        # With extreme values and no bounds, result should be very high
        assert isinstance(result, float)
        assert result > 20.0  # Should be significantly positive with such extreme values

    def test_no_champion_name_returns_zero(self, db, scorer, sample_matchups):
        """Test that missing champion_name returns 0 (existing behavior)."""
        result = scorer.score_against_team(
            sample_matchups,
            ["Darius"],
            champion_name=None
        )

        assert result == 0.0

    def test_opponent_data_respects_pickrate_filter(self, db, scorer, insert_matchup):
        """Test that opponent data below pickrate threshold is ignored."""
        # Aatrox has valid matchup
        insert_matchup("Aatrox", "Darius", 52.0, 100, 150, 5.0, 2000)

        # Darius has low pickrate matchup (below 0.5% threshold)
        insert_matchup("Darius", "Aatrox", 51.0, 50, 80, 0.4, 2000)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["Darius"],
            champion_name="Aatrox"
        )

        # Should use only our advantage (opponent data filtered out due to low pickrate)
        # With 1 known + 4 blind: (150+0*4)/5 = 30
        our_diluted_advantage = scorer.delta2_to_win_advantage(30, "Aatrox")
        # Opponent advantage should be 0 (filtered out)
        assert abs(result - our_diluted_advantage) < 0.5

    def test_opponent_data_respects_games_filter(self, db, scorer, insert_matchup):
        """Test that opponent data below games threshold is ignored."""
        # Aatrox has valid matchup
        insert_matchup("Aatrox", "Garen", 54.0, 120, 180, 8.0, 2500)

        # Garen has insufficient games (below 200 threshold)
        insert_matchup("Garen", "Aatrox", 52.0, 60, 100, 5.0, 150)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["Garen"],
            champion_name="Aatrox"
        )

        # Should use only our advantage (opponent data filtered out due to insufficient games)
        # With 1 known + 4 blind: (180+0*4)/5 = 36
        our_diluted_advantage = scorer.delta2_to_win_advantage(36, "Aatrox")
        # Opponent advantage should be 0 (filtered out)
        assert abs(result - our_diluted_advantage) < 0.5

    def test_bidirectional_uses_subtraction_not_addition(self, db, scorer, insert_matchup):
        """
        CRITICAL: Verify opponent advantage is SUBTRACTED, not added.

        This negative test ensures the formula is implemented correctly.
        """
        # Aatrox heavily favored (high positive delta2)
        insert_matchup("Aatrox", "Teemo", 60.0, 400, 500, 10.0, 2000)

        # Teemo also thinks they're favored (asymmetric data - both can't be right!)
        insert_matchup("Teemo", "Aatrox", 55.0, 200, 250, 10.0, 2000)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["Teemo"],
            champion_name="Aatrox"
        )

        # Calculate expected values
        # Our advantage: (500+0*4)/5 = 100
        our_adv = scorer.delta2_to_win_advantage(100, "Aatrox")
        # Opponent advantage: 250 (no dilution)
        opp_adv = scorer.delta2_to_win_advantage(250, "Teemo")

        # CRITICAL: Must be subtraction (our - opp), NOT addition
        expected_net = our_adv - opp_adv
        assert abs(result - expected_net) < 0.5

        # Verify it's NOT addition (would be very high and positive)
        wrong_addition = our_adv + opp_adv
        assert abs(result - wrong_addition) > 10.0  # Should NOT be addition

    def test_blind_pick_dilution_reduces_advantage(self, db, scorer, insert_matchup):
        """
        Negative test: Verify blind pick dilution actually reduces our advantage.

        Ensures formula doesn't accidentally amplify instead of dilute.
        """
        # Strong matchup vs known enemy
        insert_matchup("Aatrox", "Darius", 60.0, 400, 500, 10.0, 2000)

        # No reverse matchup (unidirectional scenario)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["Darius"],  # 1 known + 4 blind
            champion_name="Aatrox"
        )

        # Diluted advantage: (500+0*4)/5 = 100
        diluted_adv = scorer.delta2_to_win_advantage(100, "Aatrox")

        # Undiluted (raw) advantage: 500
        raw_adv = scorer.delta2_to_win_advantage(500, "Aatrox")

        # Verify dilution reduces advantage
        assert result < raw_adv
        assert abs(result - diluted_adv) < 0.5  # Should match diluted calculation

    def test_blind_pick_dilution_formula_explicit(self, db, scorer, insert_matchup):
        """
        Explicitly test blind pick dilution formula with known + blind matchups.

        Verifies the exact calculation: (known_delta2 + blind_picks * avg_delta2) / 5
        """
        # Known enemy: delta2=200
        insert_matchup("Aatrox", "Darius", 55.0, 150, 200, 10.0, 2000)

        # Other matchups for blind pick average (will be used for 4 blind picks)
        insert_matchup("Aatrox", "Garen", 52.0, 50, 100, 10.0, 2000)
        insert_matchup("Aatrox", "Sett", 48.0, -50, -100, 10.0, 2000)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            ["Darius"],  # 1 known + 4 blind
            champion_name="Aatrox"
        )

        # Manually calculate expected result
        # After removing Darius from remaining matchups:
        # Blind pick average = (100*10 + (-100)*10) / (10+10) = 0
        # Diluted delta2 = (200 + 0*4) / 5 = 40
        expected_avg_delta2 = (200 + 0 * 4) / 5  # Should equal 40
        expected_advantage = scorer.delta2_to_win_advantage(expected_avg_delta2, "Aatrox")

        # No opponent perspective in this test (unidirectional)
        assert abs(result - expected_advantage) < 0.5

    def test_weighted_vs_simple_average(self, db, scorer, insert_matchup):
        """
        Test that OUR advantage uses weighted average while ENEMY advantage uses simple mean.

        Documents and verifies this asymmetric design choice.
        Uses full 5v5 team to avoid blind pick dilution complexity.
        """
        # Setup 5 enemies for full team (no blind pick dilution)
        enemies = ["Enemy1", "Enemy2", "Enemy3", "Enemy4", "Enemy5"]

        # Our champion matchups with very different pickrates
        insert_matchup("Aatrox", "Enemy1", 52.0, 10, 20, 30.0, 4000)    # Very high pickrate, low delta2
        insert_matchup("Aatrox", "Enemy2", 65.0, 200, 250, 2.0, 800)    # Very low pickrate, high delta2
        insert_matchup("Aatrox", "Enemy3", 54.0, 50, 80, 15.0, 2500)
        insert_matchup("Aatrox", "Enemy4", 48.0, -20, -30, 12.0, 2000)
        insert_matchup("Aatrox", "Enemy5", 51.0, 30, 50, 10.0, 1800)

        # Enemy matchups - simple avg will differ from weighted avg
        insert_matchup("Enemy1", "Aatrox", 51.0, 5, 10, 40.0, 5000)     # Low delta2, high pickrate
        insert_matchup("Enemy2", "Aatrox", 70.0, 280, 320, 1.0, 500)    # High delta2, low pickrate
        insert_matchup("Enemy3", "Aatrox", 52.0, 40, 60, 10.0, 1500)
        insert_matchup("Enemy4", "Aatrox", 46.0, -25, -40, 8.0, 1200)
        insert_matchup("Enemy5", "Aatrox", 50.0, 20, 30, 12.0, 2000)

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result = scorer.score_against_team(
            aatrox_matchups,
            enemies,
            champion_name="Aatrox"
        )

        # Our advantage: weighted by pickrate
        # (20*30 + 250*2 + 80*15 + (-30)*12 + 50*10) / (30+2+15+12+10) = 2500/69 = 36.23
        our_weighted_avg = (20*30 + 250*2 + 80*15 + (-30)*12 + 50*10) / (30+2+15+12+10)
        our_adv = scorer.delta2_to_win_advantage(our_weighted_avg, "Aatrox")

        # Enemy advantage: SIMPLE average (not weighted)
        # (10 + 320 + 60 + (-40) + 30) / 5 = 380/5 = 76
        enemy_simple_avg = (10 + 320 + 60 + (-40) + 30) / 5
        enemy_adv = scorer.delta2_to_win_advantage(enemy_simple_avg, "Aatrox")

        expected = our_adv - enemy_adv

        # This test verifies the design choice is implemented
        # Exact values are complex due to filtering, so we verify behavior exists
        assert isinstance(result, float)

        # Verify that enemy advantage uses simple mean by testing with extreme pickrate differences
        # If enemy used weighted average, the high pickrate (40%) for low delta2 (10)
        # would dominate the calculation, giving much lower enemy advantage
        # With simple average, the high delta2 (320) gets equal weight

        # The simple average (76) is much higher than what weighted would be (~15)
        # This means enemy_adv_simple > enemy_adv_weighted
        # Therefore: our_adv - enemy_adv_simple < our_adv - enemy_adv_weighted
        # i.e., result < wrong_result_if_symmetric

        # Calculate what result would be if enemy used weighted (wrong implementation)
        enemy_weighted_avg = (10*40 + 320*1 + 60*10 + (-40)*8 + 30*12) / (40+1+10+8+12)
        enemy_adv_if_weighted = scorer.delta2_to_win_advantage(enemy_weighted_avg, "Aatrox")
        wrong_result_if_symmetric = our_adv - enemy_adv_if_weighted

        # With simple mean giving higher enemy advantage, our net should be lower
        assert result < wrong_result_if_symmetric
