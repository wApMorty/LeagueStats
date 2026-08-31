"""Tests du peuplement de DraftState.ally_positions depuis le LCU (SPEC-04 B3).

`_parse_draft_state` doit exposer, pour chaque allié dont la file assigne un
rôle, sa lane normalisée (cellId -> lane). L'inférence complète des rôles
(B4) et son branchement dans le scoring viennent dans un chantier séparé.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor
from src.lcu_client import LCUClient


@pytest.fixture
def monitor():
    """DraftMonitor avec un vrai LCUClient (aucun accès réseau : la lecture
    d'assignedPosition est du pur traitement de dict) et un Assistant simulé."""
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        monitor = DraftMonitor(verbose=False, auto_hover=False)
    monitor.lcu = LCUClient()
    return monitor


def test_ally_positions_filled_from_lcu(monitor):
    champ_select_data = {
        "timer": {"phase": "BAN_PICK"},
        "localPlayerCellId": 0,
        "myTeam": [
            {"cellId": 0, "championId": 84, "assignedPosition": "middle"},
            {"cellId": 1, "championId": 64, "assignedPosition": "jungle"},
            {"cellId": 2, "championId": 0, "assignedPosition": "utility"},
        ],
        "theirTeam": [],
        "actions": [],
    }

    state = monitor._parse_draft_state(champ_select_data)

    assert state.ally_positions == {0: "middle", 1: "jungle", 2: "support"}


def test_ally_positions_empty_when_queue_does_not_assign_roles(monitor):
    """File sans sélection de rôle (ex: normal blind pick) -> dict vide, pas d'exception."""
    champ_select_data = {
        "timer": {"phase": "BAN_PICK"},
        "localPlayerCellId": 0,
        "myTeam": [{"cellId": 0, "championId": 84, "assignedPosition": ""}],
        "theirTeam": [],
        "actions": [],
    }

    state = monitor._parse_draft_state(champ_select_data)

    assert state.ally_positions == {}


def test_draft_state_defaults_are_empty_dicts():
    """Les nouveaux champs de DraftState (B3/B4) ont des defaults vides, pas None."""
    from src.draft_monitor import DraftState

    state = DraftState()

    assert state.ally_positions == {}
    assert state.inferred_roles == {}
    assert state.role_confidence == {}
