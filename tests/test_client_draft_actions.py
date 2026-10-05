"""Actions de draft du client (SPEC-21 tâche 74) : garde de phase et de tour, liste blanche du LCU."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client import draft_actions
from src.client.app import create_app
from src.client.draft_actions import Refusal
from src.client.lcu_proxy import READS, WRITES, ForbiddenEndpoint, LcuProxy
from src.config_client import client_config

FIXTURES = Path(__file__).parent / "fixtures" / "lcu_forms"
LOCAL = "http://127.0.0.1"
SESSION = "/lol-champ-select/v1/session"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FauxLCU:
    """`LCUClient` réduit à `_make_request` : lit des réponses prévues, note chaque écriture."""

    def __init__(self, session=None, pickable=None, bannable=None, refuses=False):
        self.credentials = object()
        self.reads = {
            SESSION: session,
            "/lol-champ-select/v1/pickable-champion-ids": pickable,
            "/lol-champ-select/v1/bannable-champion-ids": bannable,
        }
        self.refuses = refuses
        self.calls = []
        self.writes = []

    def find_lcu_credentials(self):
        return self.credentials

    def _make_request(self, endpoint, method="GET", data=None):
        self.calls.append((method, endpoint))
        if method == "GET":
            return self.reads.get(endpoint)
        self.writes.append((method, endpoint, data))
        return None if self.refuses else {}


@pytest.fixture
def pick():
    return FauxLCU(load("session_pick.json"), pickable=[1, 2, 3, 266, 122])


@pytest.fixture
def ban():
    return FauxLCU(load("session_ban.json"), bannable=[1, 2, 3, 266, 122])


# ---------- garde ----------


def test_survoler_ecrit_sur_l_action_en_cours(pick):
    result = draft_actions.run(LcuProxy(pick), "hover", 266)
    assert pick.writes == [
        (
            "PATCH",
            "/lol-champ-select/v1/session/actions/12",
            {"championId": 266, "completed": False},
        )
    ]
    assert result == {"action": "hover", "champion_id": 266, "completed": False}


def test_verrouiller_complete_l_action(pick):
    draft_actions.run(LcuProxy(pick), "lock", 266)
    assert pick.writes[0][2] == {"championId": 266, "completed": True}


def test_bannir_et_survoler_un_ban(ban):
    draft_actions.run(LcuProxy(ban), "hover_ban", 122)
    draft_actions.run(LcuProxy(ban), "ban", 122)
    assert [w[2]["completed"] for w in ban.writes] == [False, True]
    assert all(w[1] == "/lol-champ-select/v1/session/actions/0" for w in ban.writes)


@pytest.mark.parametrize("action", ["ban", "hover_ban"])
def test_bannir_pendant_les_picks_est_refuse(pick, action):
    with pytest.raises(Refusal, match="pas le moment de bannir"):
        draft_actions.run(LcuProxy(pick), action, 266)
    assert pick.writes == []


@pytest.mark.parametrize("action", ["hover", "lock"])
def test_picker_pendant_les_bans_est_refuse(ban, action):
    with pytest.raises(Refusal, match="pas le moment de picker"):
        draft_actions.run(LcuProxy(ban), action, 266)
    assert ban.writes == []


def test_pas_mon_tour_est_refuse(pick):
    session = load("session_pick.json")
    for action_set in session["actions"]:
        for action in action_set:
            if action["actorCellId"] == 0:
                action["isInProgress"] = False  # le tour d'un autre joueur
    pick.reads[SESSION] = session
    with pytest.raises(Refusal, match="pas ton tour"):
        draft_actions.run(LcuProxy(pick), "hover", 266)
    assert pick.writes == []


def test_apres_le_verrouillage_plus_d_action(pick):
    session = load("session_pick.json")
    for action_set in session["actions"]:
        for action in action_set:
            if action["actorCellId"] == 0:
                action["completed"] = True
    pick.reads[SESSION] = session
    with pytest.raises(Refusal, match="pas ton tour"):
        draft_actions.run(LcuProxy(pick), "lock", 266)
    assert pick.writes == []


def test_champion_indisponible_est_refuse(pick):
    with pytest.raises(Refusal, match="pas disponible"):
        draft_actions.run(LcuProxy(pick), "lock", 999)
    assert pick.writes == []


def test_liste_des_disponibles_illisible_laisse_decider_le_client(pick):
    pick.reads["/lol-champ-select/v1/pickable-champion-ids"] = None
    draft_actions.run(LcuProxy(pick), "hover", 999)
    assert len(pick.writes) == 1


def test_hors_champ_select_est_refuse_sans_ecriture():
    lcu = FauxLCU(session=None)
    with pytest.raises(Refusal, match="Pas de champ select"):
        draft_actions.run(LcuProxy(lcu), "hover", 266)
    assert lcu.writes == []


def test_client_ferme_est_refuse_sans_aucun_appel():
    lcu = FauxLCU()
    lcu.credentials = None
    lcu.find_lcu_credentials = lambda: None
    with pytest.raises(Refusal, match="Pas de champ select"):
        draft_actions.run(LcuProxy(lcu), "hover", 266)
    assert lcu.calls == []


def test_refus_du_client_lol_est_lisible(pick):
    pick.refuses = True
    with pytest.raises(Refusal, match="client LoL a refusé"):
        draft_actions.run(LcuProxy(pick), "lock", 266)


@pytest.mark.parametrize("name, champion", [("danse", 266), ("hover", 0), ("hover", -3)])
def test_action_ou_champion_invalide(pick, name, champion):
    with pytest.raises(Refusal):
        draft_actions.run(LcuProxy(pick), name, champion)
    assert pick.calls == []


# ---------- liste blanche ----------


@pytest.mark.parametrize(
    "endpoint",
    [
        "/lol-chat/v1/friends",
        "/lol-champ-select/v1/session/../x",
        "/lol-champ-select/v1/session?x=1",
        "/lol-champ-select/v1/session/actions/1",  # lecture non listée
    ],
)
def test_lecture_hors_liste_blanche_refusee_sans_appel(pick, endpoint):
    with pytest.raises(ForbiddenEndpoint):
        LcuProxy(pick).get(endpoint)
    assert pick.calls == []


@pytest.mark.parametrize(
    "method, endpoint",
    [
        ("POST", "/lol-chat/v1/conversations/x/messages"),  # pas de message
        ("POST", "/lol-lobby/v2/lobby/invitations"),  # pas d'invitation
        ("DELETE", "/lol-perks/v1/pages"),
        ("PUT", "/lol-champ-select/v1/session/actions/1"),
        ("PATCH", "/lol-champ-select/v1/session/actions/x"),
        ("PATCH", "/lol-champ-select/v1/session/actions/1/../2"),
    ],
)
def test_ecriture_hors_liste_blanche_refusee_sans_appel(pick, method, endpoint):
    with pytest.raises(ForbiddenEndpoint):
        LcuProxy(pick).send(method, endpoint, {})
    assert pick.calls == []


def test_les_ecritures_listees_sont_celles_de_la_draft_seulement():
    """Critère 6 : lobby, file et draft, rien d'autre (aucune route de message ni d'invitation)."""
    allowed_prefixes = ("/lol-champ-select/", "/lol-lobby/", "/lol-matchmaking/", "/lol-perks/")
    assert all(pattern.pattern.startswith(allowed_prefixes) for _, pattern in WRITES)
    assert not any(
        "chat" in pattern.pattern or "invitation" in pattern.pattern for _, pattern in WRITES
    )


# ---------- routes ----------


def make_client(temp_db, lcu, commands=None):
    app = create_app(temp_db, lcu=lcu, commands=commands)
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def post(client, path, token=True, **params):
    headers = {client_config.TOKEN_HEADER: client.app.state.session_token} if token else {}
    return client.post(path, params=params, headers=headers)


def test_route_survol(temp_db, pick):
    response = post(make_client(temp_db, pick), "/draft/action/hover", champion_id=266)
    assert response.status_code == 200 and response.json()["completed"] is False
    assert len(pick.writes) == 1


def test_route_sans_jeton_403_et_aucun_appel_lcu(temp_db, pick):
    response = post(make_client(temp_db, pick), "/draft/action/lock", token=False, champion_id=266)
    assert response.status_code == 403
    assert pick.calls == []


def test_route_refus_409_lisible(temp_db, pick):
    response = post(make_client(temp_db, pick), "/draft/action/ban", champion_id=266)
    assert response.status_code == 409
    assert "pas le moment de bannir" in response.json()["detail"]
    assert pick.writes == []


def test_route_champion_id_invalide_422(temp_db, pick):
    assert (
        post(make_client(temp_db, pick), "/draft/action/hover", champion_id="x").status_code == 422
    )
    assert pick.calls == []


def test_route_correction_de_role_depose_la_commande(temp_db, pick):
    lignes = []
    client = make_client(temp_db, pick, commands=lambda line: lignes.append(line) or True)
    assert post(client, "/draft/role", champion="LeeSin", lane="support").status_code == 204
    assert lignes == ["r LeeSin support"]


@pytest.mark.parametrize(
    "champion, lane", [("LeeSin", "mid"), ("Lee Sin", "top"), ("", "top"), ("Lee\nSin", "top")]
)
def test_route_correction_de_role_invalide_409(temp_db, pick, champion, lane):
    lignes = []
    client = make_client(temp_db, pick, commands=lambda line: lignes.append(line) or True)
    assert post(client, "/draft/role", champion=champion, lane=lane).status_code == 409
    assert lignes == []


def test_route_correction_de_role_sans_live_coach_503(temp_db, pick):
    assert (
        post(make_client(temp_db, pick), "/draft/role", champion="LeeSin", lane="top").status_code
        == 503
    )
    client = make_client(temp_db, pick, commands=lambda line: False)
    assert post(client, "/draft/role", champion="LeeSin", lane="top").status_code == 503


def test_route_correction_de_role_sans_jeton_403(temp_db, pick):
    lignes = []
    client = make_client(temp_db, pick, commands=lambda line: lignes.append(line) or True)
    assert (
        post(client, "/draft/role", token=False, champion="LeeSin", lane="top").status_code == 403
    )
    assert lignes == []
