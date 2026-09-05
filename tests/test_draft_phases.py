"""Tests for src/draft/phases.py (SPEC-10 -- couverture du chemin critique).

Pure predicates over DraftState, no external dependency -- decides whether
recommendations/bans should be displayed. Covers every phase/picks/bans
combination that matters for is_ban_phase/should_show_bans, plus the simpler
predicates that were entirely untested.
"""

from src.draft.phases import (
    enemy_picks_changed,
    has_draft_changed,
    is_ban_phase,
    is_draft_complete,
    is_player_ban_turn,
    is_player_turn,
    should_show_bans,
)
from src.draft.state import DraftState


class TestIsDraftComplete:
    def test_incomplete_with_fewer_than_ten_picks(self):
        state = DraftState(ally_picks=["Aatrox"], enemy_picks=["Darius"])
        assert is_draft_complete(state) is False

    def test_complete_with_ten_picks(self):
        state = DraftState(
            ally_picks=["A1", "A2", "A3", "A4", "A5"],
            enemy_picks=["E1", "E2", "E3", "E4", "E5"],
        )
        assert is_draft_complete(state) is True

    def test_empty_state_is_not_complete(self):
        assert is_draft_complete(DraftState()) is False


class TestHasDraftChanged:
    def test_no_change_returns_false(self):
        state = DraftState(ally_picks=["Aatrox"], phase="BAN_PICK")
        previous = DraftState(ally_picks=["Aatrox"], phase="BAN_PICK")
        assert has_draft_changed(state, previous) is False

    def test_pick_change_returns_true(self):
        state = DraftState(ally_picks=["Aatrox"])
        previous = DraftState(ally_picks=[])
        assert has_draft_changed(state, previous) is True

    def test_ban_change_returns_true(self):
        state = DraftState(ally_bans=["Zed"])
        previous = DraftState(ally_bans=[])
        assert has_draft_changed(state, previous) is True

    def test_phase_change_returns_true(self):
        state = DraftState(phase="PICK")
        previous = DraftState(phase="BAN_PICK")
        assert has_draft_changed(state, previous) is True


class TestIsPlayerTurn:
    def test_true_when_actor_matches_local_player(self):
        state = DraftState(current_actor=3, local_player_cell_id=3)
        assert is_player_turn(state) is True

    def test_false_when_actor_differs(self):
        state = DraftState(current_actor=1, local_player_cell_id=3)
        assert is_player_turn(state) is False

    def test_false_when_no_current_actor(self):
        state = DraftState(current_actor=None, local_player_cell_id=3)
        assert is_player_turn(state) is False

    def test_false_when_no_local_player_cell_id(self):
        state = DraftState(current_actor=3, local_player_cell_id=None)
        assert is_player_turn(state) is False


class TestIsBanPhase:
    def test_false_when_no_phase(self):
        state = DraftState(phase="")
        assert is_ban_phase(state) is False

    def test_true_before_any_picks(self):
        state = DraftState(phase="BAN_PICK", ally_bans=["Zed"], enemy_bans=["Yasuo"])
        assert is_ban_phase(state) is True

    def test_false_once_any_pick_exists(self):
        """Ban phase is strictly before the first pick, even if the phase
        name is still 'BAN_PICK' (second ban phase overlaps that name)."""
        state = DraftState(phase="BAN_PICK", ally_picks=["Aatrox"])
        assert is_ban_phase(state) is False

    def test_false_when_ten_bans_already_reached(self):
        state = DraftState(
            phase="BAN_PICK",
            ally_bans=["A1", "A2", "A3", "A4", "A5"],
            enemy_bans=["E1", "E2", "E3", "E4", "E5"],
        )
        assert is_ban_phase(state) is False

    def test_true_with_nine_bans_and_no_picks(self):
        state = DraftState(
            phase="BAN_PICK",
            ally_bans=["A1", "A2", "A3", "A4", "A5"],
            enemy_bans=["E1", "E2", "E3", "E4"],
        )
        assert is_ban_phase(state) is True

    def test_verbose_does_not_raise(self, capsys):
        state = DraftState(phase="BAN_PICK", ally_picks=["Aatrox"])
        assert is_ban_phase(state, verbose=True) is False
        assert "DEBUG" in capsys.readouterr().out


class TestIsPlayerBanTurn:
    def test_false_outside_ban_phase(self):
        state = DraftState(
            phase="PICK", ally_picks=["Aatrox"], current_actor=3, local_player_cell_id=3
        )
        assert is_player_ban_turn(state) is False

    def test_true_when_ban_phase_and_actor_matches(self):
        state = DraftState(phase="BAN_PICK", current_actor=3, local_player_cell_id=3)
        assert is_player_ban_turn(state) is True

    def test_false_when_ban_phase_but_actor_differs(self):
        state = DraftState(phase="BAN_PICK", current_actor=1, local_player_cell_id=3)
        assert is_player_ban_turn(state) is False

    def test_false_when_no_phase(self):
        state = DraftState(phase="", current_actor=3, local_player_cell_id=3)
        assert is_player_ban_turn(state) is False


class TestEnemyPicksChanged:
    def test_true_when_enemy_picks_differ(self):
        state = DraftState(enemy_picks=["Darius"])
        previous = DraftState(enemy_picks=[])
        assert enemy_picks_changed(state, previous) is True

    def test_false_when_identical(self):
        state = DraftState(enemy_picks=["Darius"])
        previous = DraftState(enemy_picks=["Darius"])
        assert enemy_picks_changed(state, previous) is False

    def test_ally_pick_change_does_not_count(self):
        state = DraftState(enemy_picks=[], ally_picks=["Aatrox"])
        previous = DraftState(enemy_picks=[], ally_picks=[])
        assert enemy_picks_changed(state, previous) is False


class TestShouldShowBans:
    def test_false_when_no_phase(self):
        assert should_show_bans(DraftState(phase="")) is False

    def test_true_before_enemy_bans_revealed(self):
        state = DraftState(phase="BAN_PICK", ally_bans=["Zed"], enemy_bans=[])
        assert should_show_bans(state) is True

    def test_false_once_enemy_bans_are_revealed(self):
        state = DraftState(phase="BAN_PICK", enemy_bans=["Yasuo"])
        assert should_show_bans(state) is False

    def test_true_with_no_bans_at_all_yet(self):
        state = DraftState(phase="PLANNING")
        assert should_show_bans(state) is True
