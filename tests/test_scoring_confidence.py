"""Tests for statistical confidence weighting (SPEC-05 B6).

`confidence(games)` composes with `pickrate` (produit, pas remplacement) as
the weight used by avg_delta1/avg_delta2/avg_winrate/calculate_synergy_bonus.
`pickrate` alone still predicts the opponent's pick and must stay active.
"""

import pytest

from src.analysis.scoring import ChampionScorer, confidence
from src.config_constants import analysis_config
from src.models import Matchup, Synergy


class TestConfidenceFunction:
    """Direct tests of confidence(games) = games / (games + CONFIDENCE_K)."""

    def test_confidence_at_200_games(self):
        """200 games (MIN_MATCHUP_GAMES) gives ~0.286 confidence."""
        assert confidence(200) == pytest.approx(0.2857, abs=0.001)

    def test_confidence_at_20000_games(self):
        """20,000 games gives ~0.976 confidence."""
        assert confidence(20000) == pytest.approx(0.9756, abs=0.001)

    def test_confidence_at_k_is_half(self):
        """games == CONFIDENCE_K gives exactly 0.5 (the smoothing pivot)."""
        assert confidence(analysis_config.CONFIDENCE_K) == pytest.approx(0.5)

    def test_confidence_uses_config_constant_not_hardcoded(self):
        """CONFIDENCE_K must be read from config_constants, not hardcoded in
        scoring.py: overriding the config value changes the function output.
        """
        original = analysis_config.CONFIDENCE_K
        try:
            analysis_config.CONFIDENCE_K = 1000
            # At games == CONFIDENCE_K, confidence is always exactly 0.5,
            # regardless of the constant's value -- proves it's read live.
            assert confidence(1000) == pytest.approx(0.5)
            assert confidence(500) != pytest.approx(0.5)
        finally:
            analysis_config.CONFIDENCE_K = original

    def test_confidence_increases_with_games(self):
        """More games -> higher confidence (monotonic)."""
        assert confidence(200) < confidence(2000) < confidence(20000)

    def test_confidence_never_reaches_one(self):
        """Confidence stays strictly below 1 even for very large samples."""
        assert confidence(10_000_000) < 1.0


class TestConfidenceAffectsMatchupWeighting:
    """Same delta2/pickrate, different games -> different contributions."""

    def test_200_games_vs_20000_games_differ(self, scorer):
        """Two matchups with identical delta2 and pickrate but 200 vs 20,000
        games must produce different avg_delta2 contributions once mixed with
        a neutral third matchup, since their weights (pickrate * confidence)
        now differ (ratio ~0.29 vs ~0.98, per SPEC-05 B6 acceptance criteria).
        """
        low_confidence = Matchup("Enemy200", 55.0, 100, 10.0, 5.0, 200)
        high_confidence = Matchup("Enemy20000", 55.0, 100, 10.0, 5.0, 20000)
        neutral = Matchup("Neutral", 50.0, 0, 0.0, 5.0, 20000)

        avg_with_low = scorer.avg_delta2([low_confidence, neutral])
        avg_with_high = scorer.avg_delta2([high_confidence, neutral])

        # Same delta2/pickrate, only `games` differs -> the more confident
        # matchup pulls the average further towards its own delta2 (10.0).
        assert avg_with_high > avg_with_low

    def test_weight_ratio_matches_spec(self):
        """Explicit ratio check from the spec: confidence(200) ~ 0.29, confidence(20000) ~ 0.98."""
        low = confidence(200)
        high = confidence(20000)

        assert low == pytest.approx(0.29, abs=0.01)
        assert high == pytest.approx(0.98, abs=0.01)


class TestPickrateWeightingStillActive:
    """The confidence factor is multiplicative, not a replacement: pickrate
    still drives the weighting when games is held constant."""

    def test_different_pickrate_same_games_differ(self, scorer):
        matchups_low_pickrate = [
            Matchup("EnemyA", 55.0, 0, 100.0, 1.0, 2000),
            Matchup("EnemyB", 50.0, 0, 0.0, 10.0, 2000),
        ]
        matchups_high_pickrate = [
            Matchup("EnemyA", 55.0, 0, 100.0, 10.0, 2000),
            Matchup("EnemyB", 50.0, 0, 0.0, 10.0, 2000),
        ]

        avg_low = scorer.avg_delta2(matchups_low_pickrate)
        avg_high = scorer.avg_delta2(matchups_high_pickrate)

        # Same games for both entries in each list (so confidence is constant
        # within each list) but pickrate of EnemyA changes -> its influence
        # on the weighted average changes too.
        assert avg_high > avg_low


class TestMinMatchupGamesThresholdUnchanged:
    """filter_valid_matchups keeps rejecting anything below MIN_MATCHUP_GAMES;
    confidence() smooths what passes the filter, it does not replace it."""

    def test_below_threshold_still_filtered(self, scorer):
        below_threshold = Matchup(
            "TooFewGames", 50.0, 0, 0.0, 5.0, analysis_config.MIN_MATCHUP_GAMES - 1
        )
        at_threshold = Matchup("AtThreshold", 50.0, 0, 0.0, 5.0, analysis_config.MIN_MATCHUP_GAMES)

        result = scorer.filter_valid_matchups([below_threshold, at_threshold])

        assert below_threshold not in result
        assert at_threshold in result


class TestConfidenceInSynergyBonus:
    """calculate_synergy_bonus's USE_WEIGHTED_AVERAGE branch also applies
    pickrate * confidence(games)."""

    def test_synergy_confidence_changes_bonus(self, db, insert_matchup):
        """Reuse the scorer's DB-backed synergy path via a Mock-free route is
        heavier than needed here; instead exercise the pure weighting formula
        directly on Synergy objects the same way calculate_synergy_bonus does,
        confirming the two allies' contributions differ once games differ.
        """
        from unittest.mock import Mock
        from src.config_constants import synergy_config

        mock_db = Mock()
        mock_db.get_champion_synergies_by_name.return_value = [
            Synergy("AllyLowGames", 55.0, 100.0, 10.0, 5.0, 200),
            Synergy("AllyHighGames", 55.0, 100.0, 10.0, 5.0, 20000),
        ]
        scorer = ChampionScorer(mock_db, verbose=False)

        # Isolate AllyHighGames's contribution by comparing bonus with only
        # that ally against bonus with only AllyLowGames: same delta2/pickrate,
        # so if confidence weren't applied both calls would be identical too
        # (irrelevant here, single ally always returns its own delta2) --
        # instead mix both with a neutral third ally to make the weighting
        # difference observable.
        mock_db.get_champion_synergies_by_name.return_value = [
            Synergy("AllyLowGames", 55.0, 100.0, 10.0, 5.0, 200),
            Synergy("Neutral", 50.0, 0.0, 0.0, 5.0, 20000),
        ]
        bonus_low = scorer.calculate_synergy_bonus("Champ", ["AllyLowGames", "Neutral"])

        mock_db.get_champion_synergies_by_name.return_value = [
            Synergy("AllyHighGames", 55.0, 100.0, 10.0, 5.0, 20000),
            Synergy("Neutral", 50.0, 0.0, 0.0, 5.0, 20000),
        ]
        bonus_high = scorer.calculate_synergy_bonus("Champ", ["AllyHighGames", "Neutral"])

        # AllyHighGames (confidence ~0.98) pulls the bonus closer to 10.0
        # than AllyLowGames (confidence ~0.29) does.
        assert bonus_high > bonus_low

    def test_synergy_pickrate_weighting_still_active(self):
        """Same games for both allies (constant confidence) but different
        pickrate -> different bonus, proving pickrate weighting survives."""
        from unittest.mock import Mock

        mock_db = Mock()
        scorer = ChampionScorer(mock_db, verbose=False)

        mock_db.get_champion_synergies_by_name.return_value = [
            Synergy("AllyA", 55.0, 0.0, 100.0, 1.0, 2000),
            Synergy("AllyB", 50.0, 0.0, 0.0, 10.0, 2000),
        ]
        bonus_low_pickrate = scorer.calculate_synergy_bonus("Champ", ["AllyA", "AllyB"])

        mock_db.get_champion_synergies_by_name.return_value = [
            Synergy("AllyA", 55.0, 0.0, 100.0, 10.0, 2000),
            Synergy("AllyB", 50.0, 0.0, 0.0, 10.0, 2000),
        ]
        bonus_high_pickrate = scorer.calculate_synergy_bonus("Champ", ["AllyA", "AllyB"])

        assert bonus_high_pickrate > bonus_low_pickrate
