"""Tests for src/analysis/lane_restante.py (SPEC-11 étage a).

blind_pick_contribution() is exercised via a real ChampionScorer (avg_delta2
and filter_valid_matchups touch no DB, so Mock() is safe there) rather than
a stub, so the "other slots" math stays the real production formula and
this file only pins the NEW behavior, not a reimplementation of the old one.

is_enabled() is a one-line wrapper over Database.count_labelled_predictions()
-- tested against the real `db` fixture in test_scoring_lane_restante.py
alongside the full score_against_team() gate, not duplicated here.
"""

from unittest.mock import Mock

import pytest

from src.analysis.lane_restante import blind_pick_contribution
from src.analysis.scoring import ChampionScorer
from src.config_constants import role_inference_config
from src.models import Matchup

# Zed mostly middle, Yasuo mostly top; equal pickrate/games so the flat
# (unconditioned) average cancels out to exactly 0.0, isolating whatever the
# lane-conditioned math contributes.
MATCHUPS = [
    Matchup(enemy_name="Zed", winrate=50.0, delta1=0.0, delta2=10.0, pickrate=10.0, games=1000),
    Matchup(enemy_name="Yasuo", winrate=50.0, delta1=0.0, delta2=-10.0, pickrate=10.0, games=1000),
]
LANE_DISTRIBUTIONS = {
    "zed": {"top": 5.0, "middle": 80.0},
    "yasuo": {"top": 70.0, "middle": 20.0},
}


@pytest.fixture
def scorer():
    return ChampionScorer(Mock(), verbose=False)


class TestFallsBackToFlatAverageWhenNothingToDistinguish:
    """Same output as the pre-SPEC-11 formula in every case where there is
    no specific "our lane" slot to isolate -- never a silent guess."""

    def test_no_player_lane_is_a_no_op(self, scorer):
        contribution, weight = blind_pick_contribution(
            scorer,
            MATCHUPS,
            blind_picks=2,
            player_lane=None,
            enemy_lanes_filled=set(),
            lane_distributions_by_name=LANE_DISTRIBUTIONS,
        )
        assert (contribution, weight) == (2 * scorer.avg_delta2(MATCHUPS), 2.0)

    def test_player_lane_already_filled_by_a_known_enemy_is_a_no_op(self, scorer):
        """The known-enemy loop in score_against_team already applied
        SAME_LANE_WEIGHT to that pick -- isolating another blind slot for
        "our lane" too would double-count it."""
        contribution, weight = blind_pick_contribution(
            scorer,
            MATCHUPS,
            blind_picks=2,
            player_lane="top",
            enemy_lanes_filled={"top"},
            lane_distributions_by_name=LANE_DISTRIBUTIONS,
        )
        assert (contribution, weight) == (2 * scorer.avg_delta2(MATCHUPS), 2.0)

    def test_zero_blind_picks_is_a_no_op(self, scorer):
        contribution, weight = blind_pick_contribution(
            scorer,
            MATCHUPS,
            blind_picks=0,
            player_lane="top",
            enemy_lanes_filled=set(),
            lane_distributions_by_name=LANE_DISTRIBUTIONS,
        )
        assert (contribution, weight) == (0.0, 0.0)


class TestIsolatesTheSameLaneSlot:
    def test_one_slot_weighted_and_averaged_by_lane_plausibility(self, scorer):
        # Hand-computed: confidence(1000) is identical for both rows, so it
        # cancels in the ratio. weight(Zed) = 10*conf*5.0, weight(Yasuo) =
        # 10*conf*70.0 -> lane-conditioned avg = (10*5 - 10*70) / (5+70)
        # = -650/75 = -8.6667. The flat (unconditioned) average is exactly
        # 0.0 (equal pickrate/games, opposite deltas).
        expected_same_lane_avg = -650.0 / 75.0
        other_blind = 1  # blind_picks(2) - 1
        expected_contribution = (
            role_inference_config.SAME_LANE_WEIGHT * expected_same_lane_avg
            + other_blind * role_inference_config.OTHER_LANE_WEIGHT * 0.0
        )
        expected_weight = role_inference_config.SAME_LANE_WEIGHT + other_blind

        contribution, weight = blind_pick_contribution(
            scorer,
            MATCHUPS,
            blind_picks=2,
            player_lane="top",
            enemy_lanes_filled=set(),
            lane_distributions_by_name=LANE_DISTRIBUTIONS,
        )

        assert contribution == pytest.approx(expected_contribution)
        assert weight == pytest.approx(expected_weight)

    def test_last_blind_slot_is_pure_lane_conditioned_no_other_dilution(self, scorer):
        """blind_picks=1: the single remaining slot IS the same-lane one --
        no "other" slots left to blend with the flat average."""
        expected_same_lane_avg = -650.0 / 75.0

        contribution, weight = blind_pick_contribution(
            scorer,
            MATCHUPS,
            blind_picks=1,
            player_lane="top",
            enemy_lanes_filled=set(),
            lane_distributions_by_name=LANE_DISTRIBUTIONS,
        )

        assert contribution == pytest.approx(
            role_inference_config.SAME_LANE_WEIGHT * expected_same_lane_avg
        )
        assert weight == pytest.approx(role_inference_config.SAME_LANE_WEIGHT)

    def test_missing_lane_data_floors_to_epsilon_never_zero(self, scorer):
        """A candidate absent from champion_lanes must not collapse to zero
        weight (role_inference.py's own EPSILON convention) -- it should
        still contribute, just as an implausible-but-not-impossible pick."""
        contribution, _weight = blind_pick_contribution(
            scorer,
            MATCHUPS,
            blind_picks=1,
            player_lane="top",
            enemy_lanes_filled=set(),
            lane_distributions_by_name={},  # no data at all
        )
        # Both candidates floored to EPSILON -> equal weight -> the average
        # collapses back to the flat mean over the two deltas (0.0).
        assert contribution == pytest.approx(0.0)
