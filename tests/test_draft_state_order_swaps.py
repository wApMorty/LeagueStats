"""SPEC-24 tâche 99 : ordre de pick et échanges dans l'état et le snapshot de draft.

Formes réelles relevées en draft classée (`tests/fixtures/lcu_forms/`), aucun client LoL.
"""

import json
from unittest.mock import Mock, patch

from src.client.bus import EventBus
from src.draft.search import SearchResult
from src.draft.snapshot import TOPIC
from src.draft.state import Swap
from src.draft.state_parser import DraftStateParser
from tests.test_client_draft_actions import load
from tests.test_draft_snapshot import monitor  # noqa: F401  (fixture)


def parse(session):
    lcu = Mock()
    lcu.get_assigned_positions.return_value = {
        p["cellId"]: p["assignedPosition"] for p in session["myTeam"]
    }
    return DraftStateParser(lcu, str).parse(session, {}, {})[0]


def test_le_rang_de_pick_est_une_permutation_de_1_a_10():
    state = parse(load("session_swaps.json"))
    assert sorted(state.pick_order.values()) == list(range(1, 11))
    # Ordre des lots relevé : cellules 0, 5-6, 1-2, 7-8, 3-4, 9.
    assert state.pick_order == {0: 1, 5: 2, 6: 3, 1: 4, 2: 5, 7: 6, 8: 7, 3: 8, 4: 9, 9: 10}


def test_les_echanges_de_la_session_sont_lus_avec_leur_etat():
    state = parse(load("session_swaps.json"))
    assert Swap("pick_order", 26, 1, "RECEIVED") in state.swaps
    assert Swap("position", 8, 2, "AVAILABLE") in state.swaps
    assert len([s for s in state.swaps if s.kind == "pick_order"]) == 4
    sent = parse(load("session_swaps_sent.json"))
    assert Swap("pick_order", 46, 4, "SENT") in sent.swaps


def test_sans_actions_ni_echanges_rien_n_est_invente():
    state = parse({"timer": {"phase": "BAN_PICK"}, "myTeam": [], "theirTeam": []})
    assert state.pick_order == {} and state.swaps == []


def test_echanges_vides_apres_le_premier_pick():
    session = load("session_swaps.json")
    session["pickOrderSwaps"] = []
    session["positionSwaps"] = None
    assert parse(session).swaps == []


def snapshot_of(monitor, state):
    bus = EventBus()
    monitor.bus = bus
    monitor.champion_id_to_name = {}
    with bus.subscribe([TOPIC]) as subscription:
        with patch.object(
            monitor.search, "rank", return_value=[SearchResult("A", "top", 0.5, [], 1)]
        ):
            monitor._provide_recommendations(state)
        return subscription.get(1)[1]


def test_le_snapshot_porte_le_rang_l_anneau_et_les_echanges(monitor):
    state = parse(load("session_swaps.json"))  # cellules 1 et 2 en cours, moi : la cellule 4
    payload = snapshot_of(monitor, state)
    json.dumps(payload)
    players = {p["cell_id"]: p for p in payload["allies"] + payload["enemies"]}
    assert [players[c]["pick_order"] for c in range(10)] == [1, 4, 5, 8, 9, 2, 3, 6, 7, 10]
    assert {c for c, p in players.items() if p["is_acting"]} == {1, 2}
    assert payload["swaps"][0] == {"kind": "pick_order", "cell_id": 2, "state": "INVALID"}
    assert all("id" not in swap for swap in payload["swaps"])


def test_l_anneau_inclut_la_cellule_0(monitor):
    session = load("session_ban_simultane.json")  # bans simultanés : la cellule 0 joue
    payload = snapshot_of(monitor, parse(session))
    acting = {p["cell_id"] for p in payload["allies"] + payload["enemies"] if p["is_acting"]}
    assert 0 in acting and 4 in acting


def test_sans_actions_aucun_rang(monitor):
    session = load("session_pick.json")
    session["actions"] = []
    payload = snapshot_of(monitor, parse(session))
    assert all(p["pick_order"] is None for p in payload["allies"] + payload["enemies"])


def test_un_echange_accepte_republie_le_snapshot(monitor):
    """Mon numéro de cellule et les échanges font partie de l'empreinte du tick."""
    recommender = monitor.recommender
    before = parse(load("session_swaps.json"))
    after = parse(load("session_swaps_sent.json"))
    assert recommender._signature(before) != recommender._signature(after)
