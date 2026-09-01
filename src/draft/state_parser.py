"""Parse LCU champ-select payloads into a DraftState.

Extracted from src/draft_monitor.py (SPEC-07 E10, lot 8) : déplacement
verbatim, aucun changement de comportement.
"""

from typing import Callable, Dict, Optional, Tuple

from ..role_inference import infer_team_roles
from .state import DraftState


class DraftStateParser:
    """Turn one LCU champ-select snapshot into a ``DraftState``.

    ``forced_roles`` and ``lane_distributions`` are passed to ``parse()`` per
    call rather than captured at construction: both are rebound after the
    monitor is constructed (``_load_lane_distributions``, manual role
    correction commands, and test fixtures reassign them directly), so
    capturing them once would parse against stale data.
    """

    def __init__(self, lcu, display_name: Callable[[int], str], verbose: bool = False) -> None:
        self.lcu = lcu
        self._display_name = display_name
        self.verbose = verbose

    def parse(
        self,
        champ_select_data: Dict,
        forced_roles: Dict[int, str],
        lane_distributions: Dict[int, Dict[str, float]],
    ) -> Tuple[DraftState, Optional[str]]:
        """Parse champion select data into DraftState.

        Returns:
            (state, player_champion) — player_champion is the display name of
            the local player's just-picked champion if one was found in this
            snapshot's actions, else None (the caller must NOT overwrite its
            own tracked player_champion with None in that case — this mirrors
            the pre-extraction behavior where the attribute was only ever
            written, never reset, inside this method).
        """
        state = DraftState()
        player_champion: Optional[str] = None

        # Get basic info
        state.phase = champ_select_data.get("timer", {}).get("phase", "")
        state.local_player_cell_id = champ_select_data.get("localPlayerCellId")

        # Parse team composition
        my_team = champ_select_data.get("myTeam", [])
        their_team = champ_select_data.get("theirTeam", [])

        # SPEC-04 B3: cellId -> lane, for allies whose role is assigned by the queue
        state.ally_positions = self.lcu.get_assigned_positions(champ_select_data)

        # Process ally team
        for player in my_team:
            champ_id = player.get("championId", 0)
            if champ_id > 0:  # 0 means no champion selected
                state.ally_picks.append(champ_id)  # Store Riot ID directly

        # Process enemy team
        for player in their_team:
            champ_id = player.get("championId", 0)
            if champ_id > 0:
                state.enemy_picks.append(champ_id)  # Store Riot ID directly

        # Parse bans - FIXED: Bans are in actions[] with type="ban", not in bans{}
        # The bans{} object is often empty or unreliable in LCU API
        # We must parse completed ban actions from the actions[] array instead
        actions = champ_select_data.get("actions", [])

        for action_set in actions:
            for action in action_set:
                if action.get("type") == "ban" and action.get("completed"):
                    champion_id = action.get("championId", 0)
                    if champion_id > 0:
                        actor_cell_id = action.get("actorCellId")

                        # Determine if this ban is from our team or enemy team
                        # If actorCellId matches any player in myTeam, it's an ally ban
                        is_ally_ban = False
                        for player in my_team:
                            if player.get("cellId") == actor_cell_id:
                                is_ally_ban = True
                                break

                        if is_ally_ban:
                            if champion_id not in state.ally_bans:
                                state.ally_bans.append(champion_id)
                        else:
                            if champion_id not in state.enemy_bans:
                                state.enemy_bans.append(champion_id)

        # Find current actor (who's supposed to pick/ban now) and track player's champion
        # Reuse actions[] already fetched above
        for action_set in actions:
            for action in action_set:
                # Track player's champion selection
                if (
                    action.get("actorCellId") == state.local_player_cell_id
                    and action.get("type") == "pick"
                    and action.get("championId", 0) > 0
                ):
                    player_champion = self._display_name(action.get("championId"))

                if not action.get("completed", False):
                    state.current_actor = action.get("actorCellId")
                    break
            if state.current_actor:
                break

        # SPEC-04 B4 §4.3: infer roles for both teams, recalculated on every
        # parse so the picture sharpens as the draft fills in. Allies with a
        # known assignedPosition are fixed; enemies are purely inferred
        # (their assignedPosition is hidden by the LCU).
        if state.ally_picks:
            known_positions = {
                player.get("championId"): state.ally_positions[player.get("cellId")]
                for player in my_team
                if player.get("championId", 0) > 0 and player.get("cellId") in state.ally_positions
            }
            ally_assignment = infer_team_roles(
                state.ally_picks, lane_distributions, known_positions=known_positions
            )
            state.inferred_roles.update(ally_assignment.roles)
            state.role_confidence.update(ally_assignment.confidence)
            state.role_source.update(ally_assignment.source)

        if state.enemy_picks:
            enemy_assignment = infer_team_roles(state.enemy_picks, lane_distributions)
            state.inferred_roles.update(enemy_assignment.roles)
            state.role_confidence.update(enemy_assignment.confidence)
            state.role_source.update(enemy_assignment.source)

        # SPEC-04 B5: user-forced roles override the fresh inference above and
        # survive recalculation as long as the champion stays in the draft.
        for champion_id, lane in list(forced_roles.items()):
            if champion_id in state.ally_picks or champion_id in state.enemy_picks:
                state.inferred_roles[champion_id] = lane
                state.role_confidence[champion_id] = 1.0
                state.role_source[champion_id] = "user"
            else:
                del forced_roles[champion_id]

        return state, player_champion
