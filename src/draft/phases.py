"""Pure draft-phase predicates.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 6) : déplacement
verbatim, aucun changement de comportement.
"""

from .state import DraftState


def is_draft_complete(state: DraftState) -> bool:
    """Check if the draft is complete (all 10 champions locked)."""
    total_picks = len(state.ally_picks) + len(state.enemy_picks)
    return total_picks >= 10


def has_draft_changed(current_state: DraftState, previous: DraftState) -> bool:
    """Check if draft state has changed significantly."""
    return (
        current_state.ally_picks != previous.ally_picks
        or current_state.enemy_picks != previous.enemy_picks
        or current_state.ally_bans != previous.ally_bans
        or current_state.enemy_bans != previous.enemy_bans
        or current_state.phase != previous.phase
    )


def is_player_turn(state: DraftState) -> bool:
    """Check if it's the local player's turn to pick."""
    if not state.current_actor or not state.local_player_cell_id:
        return False
    return state.current_actor == state.local_player_cell_id


def is_ban_phase(state: DraftState, verbose: bool = False) -> bool:
    """
    Check if we are currently in an active ban phase.

    This method checks multiple conditions:
    1. We have 0 picks (ban phase is before any picks)
    2. We haven't reached the maximum number of bans yet

    Returns:
        True if currently in an active ban phase, False otherwise
    """
    if not state.phase:
        return False

    # Key insight: Ban phase happens BEFORE any picks
    # If there are any picks, we're in pick phase (even if phase name is "BAN_PICK")
    total_picks = len(state.ally_picks) + len(state.enemy_picks)
    if total_picks > 0:
        if verbose:
            print(f"[DEBUG] Not ban phase: {total_picks} picks already made")
        return False

    # Check if we haven't exceeded typical ban limits
    # In most draft modes, each team gets 5 bans (10 total)
    total_bans = len(state.ally_bans) + len(state.enemy_bans)
    if total_bans >= 10:  # Standard draft has 10 bans total
        if verbose:
            print(f"[DEBUG] Ban phase check: Max bans reached ({total_bans}/10)")
        return False

    if verbose:
        print(
            f"[DEBUG] Ban phase detected: Phase='{state.phase}', Picks={total_picks}, Bans={total_bans}/10"
        )

    return True


def is_player_ban_turn(state: DraftState, verbose: bool = False) -> bool:
    """Check if it's the local player's turn to ban."""
    if not is_ban_phase(state, verbose):
        return False
    if not state.current_actor or not state.local_player_cell_id:
        return False
    return state.current_actor == state.local_player_cell_id


def enemy_picks_changed(state: DraftState, previous: DraftState) -> bool:
    """Check if enemy team composition has changed."""
    return state.enemy_picks != previous.enemy_picks


def should_show_bans(state: DraftState) -> bool:
    """
    Determine if bans should be displayed based on the current draft phase.

    Ban phase is considered active until enemy bans are revealed.
    Once enemy bans appear, we know ban phase is complete.

    Returns:
        True if bans should be shown, False otherwise
    """
    if not state.phase:
        return False

    # Show bans during ban phase (until enemy bans are revealed)
    # Once enemy bans appear, ban phase is complete and we hide ban recommendations
    if not state.enemy_bans:
        # No enemy bans yet = still in ban phase
        return True

    # Enemy bans revealed = ban phase complete, hide bans to reduce clutter
    return False
