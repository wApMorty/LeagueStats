"""Console display of the current draft state.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 7) : déplacement
verbatim, aucun changement de comportement.
"""

from typing import Callable

from ..config_constants import role_inference_config
from .state import DraftState


def format_role_tag(champion_id: int, state: DraftState) -> str:
    """Role annotation for one champion in the draft display (SPEC-04 B5).

    "(lane·LCU)" for a role certain from the queue, "(lane·forced)" for a
    manual correction, "(lane·NN%)" for an inferred one — with a trailing
    "?" below ROLE_CONFIDENCE_WARN to flag it for a `r <champion> <lane>`
    check. Empty string when no lane is known yet (e.g. before B4's
    distributions load, or a champion missing from the lane_distributions
    likelihood matrix).
    """
    lane = state.inferred_roles.get(champion_id)
    if lane is None:
        return ""

    source = state.role_source.get(champion_id, "inferred")
    if source == "lcu":
        label = "LCU"
    elif source == "user":
        label = "forcé"
    else:
        confidence = state.role_confidence.get(champion_id, 0.0)
        label = f"{confidence * 100:.0f}%"
        if confidence < role_inference_config.ROLE_CONFIDENCE_WARN:
            label += "?"

    return f" ({lane}·{label})"


def display_draft_state(
    state: DraftState,
    display_name: Callable[[int], str],
    should_show_bans: Callable[[DraftState], bool],
) -> None:
    """Display current draft state in terminal."""
    print(f"\n[ALLY] ÉQUIPE ALLIÉE :")
    if state.ally_picks:
        for i, champ_id in enumerate(state.ally_picks, 1):
            name = display_name(champ_id)
            print(f"  {i}. {name}{format_role_tag(champ_id, state)}")
    else:
        print("  (Aucun pick pour l'instant)")

    # Only show bans during ban phases or when bans are relevant
    if state.ally_bans and should_show_bans(state):
        display_bans = [display_name(champ_id) for champ_id in state.ally_bans]
        print(f"  Bans : {', '.join(display_bans)}")

    print(f"\n[ENEMY] ÉQUIPE ENNEMIE :")
    if state.enemy_picks:
        for i, champ_id in enumerate(state.enemy_picks, 1):
            name = display_name(champ_id)
            print(f"  {i}. {name}{format_role_tag(champ_id, state)}")
    else:
        print("  (Aucun pick pour l'instant)")

    # Only show bans during ban phases or when bans are relevant
    if state.enemy_bans and should_show_bans(state):
        display_bans = [display_name(champ_id) for champ_id in state.enemy_bans]
        print(f"  Bans : {', '.join(display_bans)}")
