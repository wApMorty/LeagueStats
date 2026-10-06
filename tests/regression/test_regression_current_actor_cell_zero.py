"""Régression SPEC-24 tâche 98 : la cellule 0 n'était pas reconnue comme acteur courant.

Symptôme : sur le premier pick d'une draft (ou un ban simultané), le Live Coach ne voit
pas le tour du joueur de la cellule 0 ; un « tour en cours » lu sur ``current_actor``
désigne un autre joueur.

Cause : ``DraftStateParser.parse`` sortait de la recherche avec ``if state.current_actor:``
(la cellule 0 est fausse) et la boucle continuait, écrasant l'acteur par celui d'une action
ultérieure ; ``phases.is_player_turn`` et ``is_player_ban_turn`` testaient aussi
``not state.local_player_cell_id``.

Correctif : tests sur ``is None`` (0 est une cellule), et ``DraftState.acting_cells`` lu sur
``isInProgress`` (plusieurs acteurs en bans simultanés).
"""

from unittest.mock import Mock

from src.draft import phases
from src.draft.state_parser import DraftStateParser


def _parse(actions, local_cell=0):
    lcu = Mock()
    lcu.get_assigned_positions.return_value = {}
    data = {
        "timer": {"phase": "BAN_PICK"},
        "localPlayerCellId": local_cell,
        "myTeam": [{"cellId": 0}, {"cellId": 1}],
        "theirTeam": [{"cellId": 5}],
        "actions": actions,
    }
    return DraftStateParser(lcu, str).parse(data, {}, {})[0]


def test_la_cellule_0_en_cours_est_l_acteur_courant():
    state = _parse(
        [
            [{"type": "pick", "actorCellId": 0, "completed": False, "isInProgress": True}],
            [{"type": "pick", "actorCellId": 5, "completed": False, "isInProgress": False}],
        ]
    )
    assert state.current_actor == 0
    assert state.acting_cells == {0}
    assert phases.is_player_turn(state) is True


def test_le_tour_du_joueur_de_la_cellule_0_en_phase_de_bans():
    state = _parse([[{"type": "ban", "actorCellId": 0, "completed": False, "isInProgress": True}]])
    assert phases.is_player_ban_turn(state) is True


def test_bans_simultanes_plusieurs_acteurs_en_cours():
    state = _parse(
        [
            [
                {"type": "ban", "actorCellId": 0, "completed": False, "isInProgress": True},
                {"type": "ban", "actorCellId": 5, "completed": False, "isInProgress": True},
                {"type": "ban", "actorCellId": 1, "completed": True, "isInProgress": False},
            ]
        ]
    )
    assert state.acting_cells == {0, 5}
    assert state.current_actor == 0


def test_sans_action_aucun_acteur():
    state = _parse([])
    assert state.current_actor is None and state.acting_cells == set()
    assert phases.is_player_turn(state) is False
