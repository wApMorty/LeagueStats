"""
Regression test for ban parsing from actions[] instead of bans{}.

Bug: The draft_monitor was parsing bans from champ_select_data["bans"]["myTeamBans"]
and champ_select_data["bans"]["theirTeamBans"], but these are often empty or unreliable
in the LCU API. The actual bans are in champ_select_data["actions"] with type="ban".

This caused ALL bans to be undetected, making the draft coach recommend banned champions.

Fixed in: PR #27 commit XXXXXX

Test ensures:
1. Bans are correctly parsed from actions[] array
2. Ally and enemy bans are correctly differentiated
3. Only completed bans are included
4. The old bans{} parsing is no longer used
"""

import pytest
from src.draft_monitor import DraftMonitor, DraftState


def test_parse_bans_from_actions_array():
    """
    Regression test: Bans must be parsed from actions[] with type="ban".

    Bug: Original code parsed from bans.myTeamBans[] and bans.theirTeamBans[],
    which are often empty in the real LCU API. This caused zero bans to be detected,
    breaking all ban filtering.

    Expected: Bans are parsed from completed actions with type="ban".
    """
    # Create draft monitor instance
    monitor = DraftMonitor(verbose=False, auto_select_pool=True, auto_hover=False)

    # Simulated LCU API response with bans in actions[]
    champ_select_data = {
        "localPlayerCellId": 0,
        "myTeam": [
            {"cellId": 0, "championId": 0},
            {"cellId": 1, "championId": 0},
            {"cellId": 2, "championId": 0},
            {"cellId": 3, "championId": 0},
            {"cellId": 4, "championId": 0},
        ],
        "theirTeam": [
            {"cellId": 5, "championId": 0},
            {"cellId": 6, "championId": 0},
            {"cellId": 7, "championId": 0},
            {"cellId": 8, "championId": 0},
            {"cellId": 9, "championId": 0},
        ],
        "bans": {
            # These are EMPTY (as they are in real API) - the bug!
            "myTeamBans": [],
            "theirTeamBans": [],
        },
        "actions": [
            [
                # Ally team bans (cellId 0-4)
                {"type": "ban", "championId": 157, "completed": True, "actorCellId": 0},  # Yasuo
                {"type": "ban", "championId": 777, "completed": True, "actorCellId": 1},  # Yone
                # Enemy team bans (cellId 5-9)
                {"type": "ban", "championId": 238, "completed": True, "actorCellId": 5},  # Zed
                {"type": "ban", "championId": 103, "completed": True, "actorCellId": 6},  # Ahri
                # Incomplete ban (should be ignored)
                {
                    "type": "ban",
                    "championId": 84,
                    "completed": False,
                    "actorCellId": 2,
                },  # Akali (not completed)
            ],
            [
                # Pick phase (should be ignored for ban parsing)
                {"type": "pick", "championId": 64, "completed": True, "actorCellId": 0},  # Lee Sin
            ],
        ],
        "timer": {"phase": "BAN_PICK"},
    }

    # Parse the draft state using the monitor's method
    state = monitor._parse_draft_state(champ_select_data)

    # Assert ally bans are correctly detected
    assert 157 in state.ally_bans, "Yasuo (157) should be in ally_bans"
    assert 777 in state.ally_bans, "Yone (777) should be in ally_bans"
    assert len(state.ally_bans) == 2, f"Expected 2 ally bans, got {len(state.ally_bans)}"

    # Assert enemy bans are correctly detected
    assert 238 in state.enemy_bans, "Zed (238) should be in enemy_bans"
    assert 103 in state.enemy_bans, "Ahri (103) should be in enemy_bans"
    assert len(state.enemy_bans) == 2, f"Expected 2 enemy bans, got {len(state.enemy_bans)}"

    # Assert incomplete bans are NOT included
    assert (
        84 not in state.ally_bans and 84 not in state.enemy_bans
    ), "Akali (84) incomplete ban should not be in any ban list"

    # Assert picks are NOT in ban lists
    assert (
        64 not in state.ally_bans and 64 not in state.enemy_bans
    ), "Lee Sin (64) pick should not be in ban lists"


def test_old_bans_structure_ignored():
    """
    Regression test: The old bans{} structure should be ignored.

    Bug: If the old code path is still active, it would parse from bans.myTeamBans
    which are empty, resulting in zero bans detected.

    Expected: Even if bans{} contains data, it should be ignored in favor of actions[].
    """
    monitor = DraftMonitor(verbose=False, auto_select_pool=True, auto_hover=False)

    # Simulated API with BOTH structures (should only use actions[])
    champ_select_data = {
        "localPlayerCellId": 0,
        "myTeam": [{"cellId": 0, "championId": 0}],
        "theirTeam": [{"cellId": 5, "championId": 0}],
        "bans": {
            # Old structure (should be IGNORED)
            "myTeamBans": [999],  # Fake ID that shouldn't appear
            "theirTeamBans": [888],  # Fake ID that shouldn't appear
        },
        "actions": [
            [
                # Real bans from actions[] (should be USED)
                {"type": "ban", "championId": 157, "completed": True, "actorCellId": 0},  # Yasuo
                {"type": "ban", "championId": 238, "completed": True, "actorCellId": 5},  # Zed
            ]
        ],
        "timer": {"phase": "BAN_PICK"},
    }

    state = monitor._parse_draft_state(champ_select_data)

    # Assert actions[] data is used
    assert 157 in state.ally_bans, "Yasuo from actions[] should be detected"
    assert 238 in state.enemy_bans, "Zed from actions[] should be detected"

    # Assert bans{} data is NOT used
    assert 999 not in state.ally_bans, "Fake ID from bans.myTeamBans should be ignored"
    assert 888 not in state.enemy_bans, "Fake ID from bans.theirTeamBans should be ignored"


def test_empty_actions_no_bans():
    """
    Regression test: Empty actions[] should result in no bans (not crash).

    Expected: If no ban actions exist, ban lists should be empty.
    """
    monitor = DraftMonitor(verbose=False, auto_select_pool=True, auto_hover=False)

    champ_select_data = {
        "localPlayerCellId": 0,
        "myTeam": [{"cellId": 0, "championId": 0}],
        "theirTeam": [{"cellId": 5, "championId": 0}],
        "bans": {},
        "actions": [],  # No actions at all
        "timer": {"phase": "BAN_PICK"},
    }

    state = monitor._parse_draft_state(champ_select_data)

    assert len(state.ally_bans) == 0, "No ally bans should be detected"
    assert len(state.enemy_bans) == 0, "No enemy bans should be detected"
