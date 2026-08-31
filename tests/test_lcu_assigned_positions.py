"""Tests de LCUClient.get_assigned_positions() (SPEC-04 B3).

`assignedPosition` est la seule source certaine de lane : elle vient du LCU
et concerne les alliés en file avec sélection de rôle. `"utility"` doit être
traduit en `"support"` avant d'atteindre la moindre requête SQL (colonne
`lane`, qui ne connaît que la valeur LoLalytics).
"""

from src.lcu_client import LCUClient


def make_session(my_team):
    return {"myTeam": my_team}


def test_maps_utility_to_support():
    client = LCUClient()
    session = make_session([{"cellId": 0, "assignedPosition": "utility"}])
    assert client.get_assigned_positions(session) == {0: "support"}


def test_maps_all_standard_positions():
    client = LCUClient()
    session = make_session(
        [
            {"cellId": 0, "assignedPosition": "top"},
            {"cellId": 1, "assignedPosition": "jungle"},
            {"cellId": 2, "assignedPosition": "middle"},
            {"cellId": 3, "assignedPosition": "bottom"},
            {"cellId": 4, "assignedPosition": "utility"},
        ]
    )
    assert client.get_assigned_positions(session) == {
        0: "top",
        1: "jungle",
        2: "middle",
        3: "bottom",
        4: "support",
    }


def test_empty_assigned_position_is_ignored():
    """File sans sélection de rôle (ex: normal blind pick) -> assignedPosition == ""."""
    client = LCUClient()
    session = make_session([{"cellId": 0, "assignedPosition": ""}])
    assert client.get_assigned_positions(session) == {}


def test_missing_assigned_position_is_ignored():
    client = LCUClient()
    session = make_session([{"cellId": 0}])
    assert client.get_assigned_positions(session) == {}


def test_unknown_value_is_ignored():
    client = LCUClient()
    session = make_session([{"cellId": 0, "assignedPosition": "invoker"}])
    assert client.get_assigned_positions(session) == {}


def test_their_team_without_positions_does_not_pollute_result():
    """theirTeam n'a presque jamais assignedPosition (masqué par le client) :
    get_assigned_positions ne doit lire que myTeam."""
    client = LCUClient()
    session = {
        "myTeam": [{"cellId": 0, "assignedPosition": "top"}],
        "theirTeam": [{"cellId": 5, "assignedPosition": "jungle"}],
    }
    assert client.get_assigned_positions(session) == {0: "top"}


def test_no_my_team_returns_empty_dict():
    client = LCUClient()
    assert client.get_assigned_positions({}) == {}
