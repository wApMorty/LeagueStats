"""Tests for src/role_inference.py (SPEC-04 B4 — team role inference).

Distributions are fixed in the test file, never read from the real
database: the meta changes, these tests must not (SPEC-04 §6).
"""

import math

import pytest

from src.role_inference import RoleAssignment, infer_team_roles

# A "classic" team: one champion overwhelmingly favoring each lane.
ORNN, SEJUANI, AHRI, JINX, THRESH = 1, 2, 3, 4, 5

CLASSIC_DISTRIBUTIONS = {
    ORNN: {"top": 90.0, "jungle": 5.0, "middle": 2.0, "bottom": 1.0, "support": 2.0},
    SEJUANI: {"top": 5.0, "jungle": 85.0, "middle": 2.0, "bottom": 2.0, "support": 6.0},
    AHRI: {"top": 2.0, "jungle": 3.0, "middle": 88.0, "bottom": 5.0, "support": 2.0},
    JINX: {"top": 1.0, "jungle": 1.0, "middle": 3.0, "bottom": 90.0, "support": 5.0},
    THRESH: {"top": 2.0, "jungle": 3.0, "middle": 2.0, "bottom": 8.0, "support": 85.0},
}


class TestClassicTeam:
    def test_resolves_exactly(self):
        result = infer_team_roles([ORNN, SEJUANI, AHRI, JINX, THRESH], CLASSIC_DISTRIBUTIONS)
        assert result.roles == {
            ORNN: "top",
            SEJUANI: "jungle",
            AHRI: "middle",
            JINX: "bottom",
            THRESH: "support",
        }

    def test_all_sources_inferred(self):
        result = infer_team_roles([ORNN, SEJUANI, AHRI, JINX, THRESH], CLASSIC_DISTRIBUTIONS)
        assert all(source == "inferred" for source in result.source.values())

    def test_high_confidence_when_unambiguous(self):
        result = infer_team_roles([ORNN, SEJUANI, AHRI, JINX, THRESH], CLASSIC_DISTRIBUTIONS)
        assert all(c > 0.9 for c in result.confidence.values())


class TestRoleUniqueness:
    def test_never_duplicates_a_role(self):
        result = infer_team_roles([ORNN, SEJUANI, AHRI, JINX, THRESH], CLASSIC_DISTRIBUTIONS)
        assert len(set(result.roles.values())) == 5

    def test_two_junglers_forced_apart(self):
        """Two champions who both mostly play jungle still get distinct roles."""
        distributions = {
            100: {"top": 5.0, "jungle": 80.0, "middle": 5.0, "bottom": 5.0, "support": 5.0},
            101: {"top": 5.0, "jungle": 70.0, "middle": 5.0, "bottom": 5.0, "support": 15.0},
        }
        result = infer_team_roles([100, 101], distributions)
        assert result.roles[100] != result.roles[101]
        # The stronger jungler keeps the lane, the other is pushed elsewhere.
        assert result.roles[100] == "jungle"


class TestKnownPositions:
    def test_lcu_role_is_fixed(self):
        # Ornn's own distribution favors top, but the LCU says he's on jungle.
        result = infer_team_roles(
            [ORNN, SEJUANI, AHRI, JINX, THRESH],
            CLASSIC_DISTRIBUTIONS,
            known_positions={ORNN: "jungle"},
        )
        assert result.roles[ORNN] == "jungle"
        assert result.confidence[ORNN] == 1.0
        assert result.source[ORNN] == "lcu"

    def test_remaining_champions_avoid_the_fixed_lane(self):
        result = infer_team_roles(
            [ORNN, SEJUANI, AHRI, JINX, THRESH],
            CLASSIC_DISTRIBUTIONS,
            known_positions={ORNN: "jungle"},
        )
        assert result.roles[SEJUANI] != "jungle"
        assert len(set(result.roles.values())) == 5

    def test_fully_known_team_has_nothing_to_infer(self):
        known = {ORNN: "top", SEJUANI: "jungle", AHRI: "middle", JINX: "bottom", THRESH: "support"}
        result = infer_team_roles([ORNN, SEJUANI, AHRI, JINX, THRESH], {}, known_positions=known)
        assert result.roles == known
        assert all(source == "lcu" for source in result.source.values())
        assert all(c == 1.0 for c in result.confidence.values())


class TestPartialTeams:
    @pytest.mark.parametrize("size", [1, 2, 3, 4, 5])
    def test_no_exception_and_distinct_roles(self, size):
        champion_ids = [ORNN, SEJUANI, AHRI, JINX, THRESH][:size]
        result = infer_team_roles(champion_ids, CLASSIC_DISTRIBUTIONS)
        assert len(result.roles) == size
        assert len(set(result.roles.values())) == size

    def test_single_champion_gets_most_probable_lane(self):
        result = infer_team_roles([THRESH], CLASSIC_DISTRIBUTIONS)
        assert result.roles[THRESH] == "support"


class TestMissingDistribution:
    def test_champion_without_data_does_not_crash(self):
        result = infer_team_roles([999], {})
        assert 999 in result.roles

    def test_missing_champion_among_known_ones_gets_a_role(self):
        result = infer_team_roles([ORNN, 999], CLASSIC_DISTRIBUTIONS)
        assert len(set(result.roles.values())) == 2
        assert result.roles[ORNN] == "top"


class TestEpsilonPreventsLogZero:
    def test_explicit_zero_share_does_not_raise(self):
        distributions = {
            42: {"top": 90.0, "jungle": 0.0, "middle": 0.0, "bottom": 0.0, "support": 0.0}
        }
        result = infer_team_roles([42], distributions)
        assert result.roles[42] == "top"

    def test_forced_into_a_zero_share_lane_stays_finite(self):
        """The only valid assignment sometimes requires an unplayed lane —
        it must be improbable, not impossible (no -inf / exception)."""
        distributions = {
            1: {"top": 90.0, "jungle": 0.0},
            2: {"top": 85.0, "jungle": 0.0},
        }
        result = infer_team_roles([1, 2], distributions, known_positions={1: "top"})
        assert result.roles[2] == "jungle"
        assert math.isfinite(result.confidence[2])


class TestAmbiguousCase:
    def test_low_confidence_when_two_lanes_are_near_tied(self):
        # Both champions are ~equally at home on top or support (Pantheon-like).
        distributions = {
            10: {"top": 50.0, "support": 48.0, "jungle": 1.0, "middle": 0.5, "bottom": 0.5},
            11: {"top": 48.0, "support": 50.0, "jungle": 1.0, "middle": 0.5, "bottom": 0.5},
        }
        result = infer_team_roles([10, 11], distributions)
        assert len(set(result.roles.values())) == 2
        assert result.confidence[10] < 0.2
        assert result.confidence[11] < 0.2

    def test_high_confidence_when_one_lane_dominates(self):
        # Yuumi-like: overwhelmingly one role.
        distributions = {
            20: {"top": 1.0, "jungle": 1.0, "middle": 1.0, "bottom": 2.0, "support": 95.0}
        }
        result = infer_team_roles([20], distributions)
        assert result.roles[20] == "support"
        assert result.confidence[20] > 0.9


class TestFullTie:
    def test_zero_confidence_when_every_champion_is_a_blank_slate(self):
        result = infer_team_roles([1, 2, 3], {})
        assert len(set(result.roles.values())) == 3
        assert all(c == pytest.approx(0.0, abs=1e-9) for c in result.confidence.values())
