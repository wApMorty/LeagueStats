"""Tests for scoring algorithms (src/analysis/scoring.py)."""

import pytest
from src.analysis.probability import sigmoid, winrate_points_to_logit
from src.analysis.scoring import ChampionScorer, estimate_win_probability
from src.config_constants import analysis_config
from src.models import Matchup


class TestFilterValidMatchups:
    """Tests for filter_valid_matchups method."""

    def test_filters_low_pickrate(self, scorer, sample_matchups):
        """Test that matchups with low pickrate are filtered out."""
        # Create matchup with pickrate below threshold
        low_pickrate = Matchup(
            enemy_name="TestChamp",
            winrate=50.0,
            delta1=0,
            delta2=0,
            pickrate=analysis_config.MIN_PICKRATE - 0.1,  # Below threshold
            games=1000,
        )
        matchups = [low_pickrate] + sample_matchups

        result = scorer.filter_valid_matchups(matchups)

        assert low_pickrate not in result
        assert len(result) == len(sample_matchups)

    def test_filters_low_games(self, scorer, sample_matchups):
        """Test that matchups with insufficient games are filtered out."""
        low_games = Matchup(
            enemy_name="TestChamp",
            winrate=50.0,
            delta1=0,
            delta2=0,
            pickrate=10.0,  # Good pickrate
            games=analysis_config.MIN_MATCHUP_GAMES - 1,  # Below threshold
        )
        matchups = [low_games] + sample_matchups

        result = scorer.filter_valid_matchups(matchups)

        assert low_games not in result

    def test_keeps_valid_matchups(self, scorer, sample_matchups):
        """Test that valid matchups are kept."""
        result = scorer.filter_valid_matchups(sample_matchups)

        assert len(result) == len(sample_matchups)

    def test_empty_list(self, scorer):
        """Test filtering empty matchup list."""
        result = scorer.filter_valid_matchups([])

        assert result == []


class TestAvgDelta1:
    """Tests for avg_delta1 weighted average calculation."""

    def test_weighted_average_calculation(self, scorer):
        """Test correct weighted average by pickrate."""
        matchups = [
            Matchup("Champ1", 50.0, 100.0, 0, 10.0, 1000),  # delta1=100, weight=10
            Matchup("Champ2", 50.0, 200.0, 0, 20.0, 1000),  # delta1=200, weight=20
        ]
        # Expected: (100*10 + 200*20) / (10+20) = 5000 / 30 = 166.67

        result = scorer.avg_delta1(matchups)

        assert abs(result - 166.67) < 0.01

    def test_single_matchup(self, scorer):
        """Test average with single matchup."""
        matchups = [Matchup("Champ1", 50.0, 150.0, 0, 10.0, 1000)]

        result = scorer.avg_delta1(matchups)

        assert result == 150.0

    def test_empty_matchups_returns_zero(self, scorer):
        """Test that empty matchup list returns 0."""
        result = scorer.avg_delta1([])

        assert result == 0.0

    def test_zero_total_weight_returns_zero(self, scorer):
        """Test that zero total weight returns 0."""
        # All matchups below pickrate threshold
        matchups = [Matchup("Champ1", 50.0, 100.0, 0, 0.1, 1000)]

        result = scorer.avg_delta1(matchups)

        assert result == 0.0


class TestAvgDelta2:
    """Tests for avg_delta2 weighted average calculation."""

    def test_weighted_average_calculation(self, scorer):
        """Test correct weighted average by pickrate * confidence(games)."""
        matchups = [
            Matchup("Champ1", 50.0, 0, 150.0, 15.0, 1500),  # delta2=150, pickrate=15
            Matchup("Champ2", 50.0, 0, 250.0, 10.0, 1000),  # delta2=250, pickrate=10
        ]
        # recalculé avec confidence(games), cf B6 : le poids est désormais
        # pickrate * confidence(games) et non plus pickrate seul.
        # confidence(1500) = 1500/2000 = 0.75 -> weight1 = 15*0.75 = 11.25
        # confidence(1000) = 1000/1500 = 0.6667 -> weight2 = 10*0.6667 = 6.667
        # (150*11.25 + 250*6.667) / (11.25+6.667) = 187.21

        result = scorer.avg_delta2(matchups)

        assert abs(result - 187.21) < 0.01

    def test_empty_matchups_returns_zero(self, scorer):
        """Test that empty matchup list returns 0."""
        result = scorer.avg_delta2([])

        assert result == 0.0


class TestAvgWinrate:
    """Tests for avg_winrate weighted average calculation."""

    def test_weighted_average_calculation(self, scorer):
        """Test correct weighted average by pickrate * confidence(games)."""
        matchups = [
            Matchup("Champ1", 52.0, 0, 0, 12.0, 1200),  # winrate=52, pickrate=12
            Matchup("Champ2", 48.0, 0, 0, 8.0, 800),  # winrate=48, pickrate=8
        ]
        # recalculé avec confidence(games), cf B6 : le poids est désormais
        # pickrate * confidence(games) et non plus pickrate seul.
        # confidence(1200) = 1200/1700 = 0.7059 -> weight1 = 12*0.7059 = 8.471
        # confidence(800) = 800/1300 = 0.6154 -> weight2 = 8*0.6154 = 4.923
        # (52*8.471 + 48*4.923) / (8.471+4.923) = 50.53

        result = scorer.avg_winrate(matchups)

        assert abs(result - 50.53) < 0.01

    def test_empty_matchups_returns_zero(self, scorer):
        """Test that empty matchup list returns 0."""
        result = scorer.avg_winrate([])

        assert result == 0.0


class TestScoreAgainstTeam:
    """Tests for score_against_team matchup calculations."""

    def test_returns_zero_without_champion_name(self, scorer, sample_matchups):
        """Test that function returns 0 when champion_name is not provided."""
        result = scorer.score_against_team(sample_matchups, ["Darius"], champion_name=None)

        assert result == 0.0

    def test_blind_pick_uses_avg_delta2(self, scorer, sample_matchups):
        """Test that blind pick scenario uses average delta2."""
        result = scorer.score_against_team(sample_matchups, [], champion_name="Aatrox")

        # recalculé : score_against_team sature désormais via sigmoid, cf B7.
        # delta2_to_win_advantage renvoie un log-odds ; on le reconvertit en
        # écart de probabilité saturant avant de comparer, comme le fait
        # score_against_team lui-même.
        avg_delta2 = scorer.avg_delta2(sample_matchups)
        expected_logit = scorer.delta2_to_win_advantage(avg_delta2)
        expected = (sigmoid(expected_logit) - 0.5) * 100.0

        assert abs(result - expected) < 0.01

    def test_known_matchup_calculation(self, scorer):
        """Test calculation against known enemy with bidirectional."""
        matchups = [
            Matchup("Darius", 48.0, -150, -200, 10.0, 1500),
        ]

        result = scorer.score_against_team(matchups, ["Darius"], champion_name="Aatrox")

        # With bidirectional, result may differ from unidirectional if opponent data exists
        # Should be negative (we're at disadvantage with delta2=-200)
        assert result < 0

    def test_mixed_known_and_blind(self, scorer):
        """Test calculation with some known and some blind picks."""
        matchups = [
            Matchup("Darius", 48.0, -150, -200, 10.0, 1500),
            Matchup("Garen", 52.0, 100, 150, 12.0, 2000),
            Matchup("Teemo", 45.0, -300, -400, 5.0, 800),
        ]

        # Enemy team: Darius known, 4 blind picks
        result = scorer.score_against_team(matchups, ["Darius"], champion_name="Aatrox")

        # Should use Darius delta2 + avg of remaining for blind picks
        assert isinstance(result, float)
        # With mixed matchups (negative delta2 vs Darius), should be negative
        assert result < 0

    def test_empty_matchups_returns_zero(self, scorer):
        """Test with no matchup data."""
        result = scorer.score_against_team([], ["Darius"], champion_name="Aatrox")

        assert result == 0.0


class TestScoreAgainstTeamLane:
    """SPEC-03 / B2 : `lane` doit filtrer la requête inverse interne
    (self.db.get_matchup_delta2) et donc changer le résultat, sans qu'aucun
    appelant existant (lane=None) ne soit affecté.
    """

    def test_lane_changes_enemy_perspective_result(self, db, scorer, insert_matchup):
        # Notre perspective : Aatrox vs Darius, non taguée (peu importe pour ce test).
        insert_matchup("Aatrox", "Darius", 58.0, 50, 100, 10.0, 2000)
        # Perspective de l'ennemi, deux lanes aux valeurs opposées.
        insert_matchup("Darius", "Aatrox", 51.0, 5, 10, 10.0, 2000, lane="top")
        insert_matchup("Darius", "Aatrox", 55.0, 20, 40, 10.0, 2000, lane="support")

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")

        result_top = scorer.score_against_team(
            aatrox_matchups, ["Darius"], champion_name="Aatrox", lane="top"
        )
        result_support = scorer.score_against_team(
            aatrox_matchups, ["Darius"], champion_name="Aatrox", lane="support"
        )

        assert result_top != pytest.approx(result_support)
        # recalculé : score_against_team sature désormais via sigmoid, cf B7.
        # our_avg_delta2 = 100/5 = 20 (dilution blind picks), converti en
        # log-odds ; net_advantage = our_logit - enemy_logit, reconverti en
        # écart de probabilité saturant seulement à la toute fin.
        our_logit = winrate_points_to_logit(20.0 * analysis_config.K_MATCHUP)
        top_logit = our_logit - winrate_points_to_logit(10.0 * analysis_config.K_MATCHUP)
        support_logit = our_logit - winrate_points_to_logit(40.0 * analysis_config.K_MATCHUP)
        assert result_top == pytest.approx((sigmoid(top_logit) - 0.5) * 100.0)
        assert result_support == pytest.approx((sigmoid(support_logit) - 0.5) * 100.0)

    def test_lane_none_keeps_full_aggregation_behaviour(self, db, scorer, insert_matchup):
        """lane=None (comportement historique) reste la moyenne pondérée toutes lanes."""
        insert_matchup("Aatrox", "Darius", 58.0, 50, 100, 10.0, 2000)
        insert_matchup("Darius", "Aatrox", 51.0, 5, 10, 10.0, 2000, lane="top")
        insert_matchup("Darius", "Aatrox", 55.0, 20, 40, 10.0, 2000, lane="support")

        aatrox_matchups = db.get_champion_matchups_by_name("Aatrox")
        result_none = scorer.score_against_team(aatrox_matchups, ["Darius"], champion_name="Aatrox")

        weighted_enemy = (10.0 * 2000 + 40.0 * 2000) / 4000  # = 25.0
        # recalculé : score_against_team sature désormais via sigmoid, cf B7.
        our_logit = winrate_points_to_logit(20.0 * analysis_config.K_MATCHUP)
        enemy_logit = winrate_points_to_logit(weighted_enemy * analysis_config.K_MATCHUP)
        assert result_none == pytest.approx((sigmoid(our_logit - enemy_logit) - 0.5) * 100.0)

    def test_lane_with_no_matching_data_degrades_to_unidirectional(
        self, db, scorer, insert_matchup
    ):
        """Une lane sans donnée pour l'ennemi retombe sur le mode unidirectionnel (enemy=0)."""
        insert_matchup("Aatrox", "Darius", 58.0, 50, 100, 10.0, 2000)
        insert_matchup("Darius", "Aatrox", 51.0, 5, 10, 10.0, 2000, lane="top")

        result = scorer.score_against_team(
            db.get_champion_matchups_by_name("Aatrox"),
            ["Darius"],
            champion_name="Aatrox",
            lane="jungle",
        )

        # recalculé : score_against_team sature désormais via sigmoid, cf B7.
        our_logit = winrate_points_to_logit(20.0 * analysis_config.K_MATCHUP)
        assert result == pytest.approx(
            (sigmoid(our_logit) - 0.5) * 100.0
        )  # enemy_logit = 0 (pas de donnée)


class TestCalculateTeamWinrate:
    """Tests for calculate_team_winrate (SPEC-05 B7): thin wrapper around the
    module-level estimate_win_probability now -- no more geometric mean, no
    more [20, 80]/[25, 75] clamps. Behavioral coverage of the log-odds math
    itself (saturation, symmetry, extremes) lives in tests/test_win_probability.py;
    these tests check the wrapper's own contract (dict shape, delegation,
    passthrough of individual_winrates)."""

    def test_returns_expected_dict_shape(self, scorer):
        result = scorer.calculate_team_winrate([52.0, 51.0, 53.0])

        assert "team_winrate" in result
        assert "individual_winrates" in result

    def test_delegates_to_estimate_win_probability(self, scorer):
        """calculate_team_winrate must delegate to the module-level
        estimate_win_probability rather than reimplementing the math."""
        winrates = [52.0, 48.0, 61.0]
        result = scorer.calculate_team_winrate(winrates)

        expected = estimate_win_probability(winrates) * 100.0
        assert result["team_winrate"] == pytest.approx(expected)

    def test_empty_list_returns_50_percent(self, scorer):
        """Test that empty list returns neutral 50% winrate."""
        result = scorer.calculate_team_winrate([])

        assert result["team_winrate"] == 50.0
        assert result["individual_winrates"] == []

    def test_individual_winrates_are_no_longer_clamped(self, scorer):
        """recalculé : SPEC-05 B7 supprime le clamp [20%, 80%] sur les winrates
        individuelles -- il ne servait qu'à masquer les sorties absurdes de la
        moyenne géométrique (SPEC-05 §1.3). Elles sont désormais renvoyées
        telles quelles."""
        result = scorer.calculate_team_winrate([90.0, 10.0, 50.0])

        assert result["individual_winrates"] == [90.0, 10.0, 50.0]

    def test_team_winrate_no_longer_bounded_to_25_75(self, scorer):
        """recalculé : SPEC-05 B7 supprime le clamp [25%, 75%] sur le résultat,
        remplacé par la saturation naturelle du sigmoïde (reste dans ]0, 100[
        sans borne artificielle) -- un draft à 5x80% dépasse désormais 75%,
        et un draft à 5x20% descend désormais sous 25%."""
        result_high = scorer.calculate_team_winrate([80.0, 80.0, 80.0, 80.0, 80.0])
        assert result_high["team_winrate"] > 75.0
        assert result_high["team_winrate"] < 100.0

        result_low = scorer.calculate_team_winrate([20.0, 20.0, 20.0, 20.0, 20.0])
        assert result_low["team_winrate"] < 25.0
        assert result_low["team_winrate"] > 0.0

    def test_single_champion(self, scorer):
        """recalculé : avant B7, un seul champion dans [20, 80] repassait tel
        quel (moyenne géométrique à un seul terme, non clampée). B7 fait
        toujours passer la valeur par logit/sigmoid, donc 55.0 ne redonne
        plus exactement 55.0."""
        result = scorer.calculate_team_winrate([55.0])

        expected = sigmoid(winrate_points_to_logit(55.0 - 50.0)) * 100.0
        assert result["team_winrate"] == pytest.approx(expected)
        assert result["individual_winrates"] == [55.0]


class TestDelta2ToWinAdvantage:
    """Tests for delta2_to_win_advantage (SPEC-05 B7): now returns a raw
    log-odds contribution, not a percentage -- the old `delta2 * 1.0`
    identity displayed directly as a percentage was exactly the defect
    SPEC-05 fixes (see SPEC-05 §1.2). Conversion to a displayable, saturating
    percentage happens one level up, in score_against_team (tested in
    TestScoreAgainstTeam/TestScoreAgainstTeamLane)."""

    def test_positive_delta2_gives_positive_logit(self, scorer):
        result = scorer.delta2_to_win_advantage(2.0)
        assert result > 0

    def test_negative_delta2_gives_negative_logit(self, scorer):
        result = scorer.delta2_to_win_advantage(-2.0)
        assert result < 0

    def test_zero_delta2_gives_zero_logit(self, scorer):
        result = scorer.delta2_to_win_advantage(0.0)
        assert result == pytest.approx(0.0)

    def test_matches_winrate_points_to_logit_formula(self, scorer):
        """delta2_to_win_advantage(delta2) == winrate_points_to_logit(delta2 * K_MATCHUP)."""
        delta2 = 5.0
        result = scorer.delta2_to_win_advantage(delta2)
        expected = winrate_points_to_logit(delta2 * analysis_config.K_MATCHUP)
        assert result == pytest.approx(expected)

    def test_no_longer_the_old_linear_identity(self, scorer):
        """recalculé : avant B7, delta2_to_win_advantage(delta2, name) == delta2
        (identité linéaire *1.0, affichée telle quelle comme un pourcentage --
        le défaut B7a décrit en SPEC-05 §1.2). B7 le remplace par un terme
        log-odds (delta2 * K_MATCHUP * LOGIT_PER_WINRATE_POINT = delta2 * 1.0 * 0.04),
        donc delta2=3.40 ne renvoie plus 3.40 mais 0.136."""
        result = scorer.delta2_to_win_advantage(3.40)

        assert result != pytest.approx(3.40)
        assert result == pytest.approx(
            3.40 * analysis_config.K_MATCHUP * analysis_config.LOGIT_PER_WINRATE_POINT
        )

    def test_extreme_database_values_stay_finite_and_unsaturated_here(self, scorer):
        """Database extremes (SPEC-05 §1.2: delta2 in [-51.43, +31.74]) must
        produce finite log-odds values, still linear at this stage --
        saturation only happens later, at the sigmoid step in
        score_against_team, not inside delta2_to_win_advantage itself."""
        result_positive = scorer.delta2_to_win_advantage(31.74)
        result_negative = scorer.delta2_to_win_advantage(-51.43)

        assert result_positive > 0
        assert result_negative < 0
        assert result_positive == pytest.approx(
            31.74 * analysis_config.K_MATCHUP * analysis_config.LOGIT_PER_WINRATE_POINT
        )
