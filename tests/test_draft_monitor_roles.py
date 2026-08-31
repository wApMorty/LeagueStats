"""Tests du peuplement de DraftState.ally_positions/inferred_roles/role_confidence
(SPEC-04 B3 pour ally_positions, B4 pour l'inférence et son branchement au scoring).
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


# Ornn (90) et Thresh (85) ont chacun une lane dominante nette ; utilisés
# pour vérifier que l'inférence retrouve l'affectation évidente.
LANE_DISTRIBUTIONS = {
    2350: {"top": 90.0, "jungle": 5.0, "middle": 2.0, "bottom": 1.0, "support": 2.0},  # Ornn
    412: {"top": 2.0, "jungle": 3.0, "middle": 2.0, "bottom": 8.0, "support": 85.0},  # Thresh
}


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


class TestRoleInferenceInParseDraftState:
    """SPEC-04 B4 §4.3 : _parse_draft_state appelle infer_team_roles() pour
    les deux équipes et peuple inferred_roles/role_confidence."""

    def test_allies_and_enemies_get_inferred_roles(self, monitor):
        monitor.lane_distributions = dict(LANE_DISTRIBUTIONS)
        champ_select_data = {
            "timer": {"phase": "BAN_PICK"},
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "championId": 2350, "assignedPosition": ""}],
            "theirTeam": [{"cellId": 5, "championId": 412}],
            "actions": [],
        }

        state = monitor._parse_draft_state(champ_select_data)

        assert state.inferred_roles[2350] == "top"
        assert state.inferred_roles[412] == "support"
        assert state.role_confidence[2350] > 0.5
        assert state.role_confidence[412] > 0.5

    def test_lcu_known_position_overrides_dominant_lane(self, monitor):
        # Ornn's own distribution favors top, but the queue assigned jungle.
        monitor.lane_distributions = dict(LANE_DISTRIBUTIONS)
        champ_select_data = {
            "timer": {"phase": "BAN_PICK"},
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "championId": 2350, "assignedPosition": "jungle"}],
            "theirTeam": [],
            "actions": [],
        }

        state = monitor._parse_draft_state(champ_select_data)

        assert state.inferred_roles[2350] == "jungle"
        assert state.role_confidence[2350] == 1.0

    def test_recomputed_as_more_champions_are_picked(self, monitor):
        monitor.lane_distributions = dict(LANE_DISTRIBUTIONS)
        base_data = {
            "timer": {"phase": "BAN_PICK"},
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "championId": 2350, "assignedPosition": ""}],
            "actions": [],
        }

        state_early = monitor._parse_draft_state({**base_data, "theirTeam": []})
        state_later = monitor._parse_draft_state(
            {**base_data, "theirTeam": [{"cellId": 5, "championId": 412}]}
        )

        assert 412 not in state_early.inferred_roles
        assert state_later.inferred_roles[412] == "support"

    def test_missing_lane_distributions_does_not_crash(self, monitor):
        """lane_distributions vide (pas encore chargée / échec) -> pas d'exception."""
        champ_select_data = {
            "timer": {"phase": "BAN_PICK"},
            "localPlayerCellId": 0,
            "myTeam": [{"cellId": 0, "championId": 2350, "assignedPosition": ""}],
            "theirTeam": [{"cellId": 5, "championId": 412}],
            "actions": [],
        }

        state = monitor._parse_draft_state(champ_select_data)

        assert 2350 in state.inferred_roles
        assert 412 in state.inferred_roles


class TestLaneWiringIntoScoring:
    """SPEC-04 B4 §4.3 : _provide_recommendations transmet notre lane et les
    lanes inférées des ennemis au scoring (matchup et synergie)."""

    @pytest.fixture
    def scoring_monitor(self):
        from src.models import Matchup

        assistant = Mock()
        assistant.db = Mock()
        assistant.get_matchups_for_draft.return_value = [
            Matchup(
                enemy_name="Thresh",
                winrate=52.0,
                delta1=10.0,
                delta2=15.0,
                pickrate=5.0,
                games=1000,
            )
        ]

        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            with patch("src.draft_monitor.Assistant", return_value=assistant):
                monitor = DraftMonitor(verbose=False, auto_hover=False)

        monitor.current_pool = ["Ornn"]
        monitor.champion_id_to_name = {2350: "Ornn", 412: "Thresh"}
        return monitor

    def test_player_lane_and_enemy_lanes_reach_scoring(self, scoring_monitor):
        from src.draft_monitor import DraftState

        state = DraftState(
            phase="BAN_PICK", enemy_picks=[412], ally_picks=[], local_player_cell_id=0
        )
        state.ally_positions = {0: "top"}
        state.inferred_roles = {412: "support"}

        with (
            patch.object(
                scoring_monitor, "_calculate_score_against_team", return_value=10.0
            ) as mock_matchup,
            patch.object(
                scoring_monitor, "_calculate_synergy_score", return_value=0.0
            ) as mock_synergy,
        ):
            scoring_monitor._provide_recommendations(state)

        assert mock_matchup.call_args.kwargs["player_lane"] == "top"
        assert mock_matchup.call_args.kwargs["enemy_lanes"] == {"Thresh": "support"}
        assert mock_synergy.call_args.kwargs["lane"] == "top"

    def test_no_assigned_position_means_no_player_lane(self, scoring_monitor):
        """File sans sélection de rôle -> pas de lane à transmettre (None), pas de crash."""
        from src.draft_monitor import DraftState

        state = DraftState(
            phase="BAN_PICK", enemy_picks=[412], ally_picks=[], local_player_cell_id=0
        )

        with (
            patch.object(
                scoring_monitor, "_calculate_score_against_team", return_value=10.0
            ) as mock_matchup,
            patch.object(scoring_monitor, "_calculate_synergy_score", return_value=0.0),
        ):
            scoring_monitor._provide_recommendations(state)

        assert mock_matchup.call_args.kwargs["player_lane"] is None
