"""Écran Social du client (SPEC-21 tâche 82) : amis, statuts, conversations, strictement en lecture seule."""

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.draft_view import Champions
from src.client.lcu_proxy import ForbiddenEndpoint, LcuProxy
from src.client.social import social_view
from tests.support_lcu_nav import FauxLcuNav, fixture, make_assets

LOCAL = "http://127.0.0.1"


@pytest.fixture
def champions(tmp_path):
    return Champions(make_assets(tmp_path))


def view(champions, **changes):
    parts = {
        "me": fixture("chat_me"),
        "friends": fixture("chat_friends"),
        "conversations": fixture("chat_conversations"),
    }
    parts.update(changes)
    return social_view(champions=champions, **parts)


def web(temp_db, tmp_path, lcu):
    app = create_app(temp_db, lcu=lcu, assets=make_assets(tmp_path))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


# ---------- vue ----------


def test_les_amis_sont_ranges_par_etat(champions):
    v = view(champions)
    assert [f["name"] for f in v["in_game"]] == ["Bravo"]
    assert [f["name"] for f in v["online"]] == ["Alpha", "Charlie", "Delta"]
    assert len(v["offline"]) == 2
    assert v["summary"] == "6 amis · 4 connectés · 1 en partie"


def test_un_ami_en_partie_montre_la_file_le_champion_et_le_rang(champions):
    bravo = view(champions)["in_game"][0]
    assert bravo["activity"] == "En partie · Classée solo/duo · Champion 64"
    assert bravo["rank"] == "Émeraude IV" and bravo["status"] == "Ne pas déranger"


def test_le_message_de_statut_est_l_activite_d_un_ami_en_ligne(champions):
    alpha = next(f for f in view(champions)["online"] if f["name"] == "Alpha")
    assert alpha["activity"] == "Dispo pour une flex" and alpha["status"] == "En ligne"


def test_profil_de_chat_et_conversations(champions):
    v = view(champions)
    assert v["me"]["name"] == "Invocateur" and v["me"]["rank"] == "Diamant II"
    assert v["me"]["message"] == "Dernier PO avant le split"
    assert [(c["name"], c["unread"], c["muted"]) for c in v["conversations"]] == [
        ("Alpha", 2, False),
        ("Bravo", 0, True),
    ]
    assert v["unread"] == 2


def test_un_long_message_est_tronque(champions):
    conversations = fixture("chat_conversations")
    conversations[0]["lastMessage"] = "x" * 500
    last = view(champions, conversations=conversations)["conversations"][0]["last"]
    assert len(last) == 80 and last.endswith("…")


def test_donnees_incompletes_sans_erreur(champions):
    v = view(champions, me={"availability": "chat"}, friends=[{"id": "x"}], conversations=[{}])
    assert v["offline"][0]["name"] == "Inconnu" and v["conversations"][0]["unread"] == 0


# ---------- route ----------


def test_route_et_lecture_seule(temp_db, tmp_path):
    lcu = FauxLcuNav()
    response = web(temp_db, tmp_path, lcu).get("/social")
    assert response.status_code == 200
    for text in ("Alpha", "Bravo", "Conversations", "Dernier PO avant le split", "Lecture seule"):
        assert text in response.text
    assert lcu.writes == []
    assert {call[1] for call in lcu.calls if "chat" in call[1]} == {
        "/lol-chat/v1/me",
        "/lol-chat/v1/friends",
        "/lol-chat/v1/conversations",
    }


def test_pseudo_et_message_echappes(temp_db, tmp_path):
    text = web(temp_db, tmp_path, FauxLcuNav()).get("/social").text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text


def test_client_ferme_et_sans_reponse(temp_db, tmp_path):
    assert "Client LoL fermé" in web(temp_db, tmp_path, None).get("/social").text
    response = web(temp_db, tmp_path, FauxLcuNav({"/lol-chat/v1/me": None})).get("/social")
    assert response.status_code == 200 and "ne répond pas" in response.text


def test_amis_illisibles_n_empechent_pas_le_profil(temp_db, tmp_path):
    lcu = FauxLcuNav({"/lol-chat/v1/friends": None, "/lol-chat/v1/conversations": None})
    response = web(temp_db, tmp_path, lcu).get("/social")
    assert response.status_code == 200 and "0 amis" in response.text


def test_aucune_route_n_ecrit_dans_le_social(temp_db, tmp_path):
    lcu = FauxLcuNav()
    client = web(temp_db, tmp_path, lcu)
    headers = {"X-Session-Token": client.app.state.session_token}
    for path in ("/social", "/social/message", "/social/invitation", "/social/amis"):
        assert client.post(path, headers=headers).status_code in (404, 405)
    assert lcu.writes == []


# ---------- liste blanche ----------


@pytest.mark.parametrize("name", ["me", "friends", "conversations"])
def test_lectures_du_chat_autorisees(name):
    assert LcuProxy(FauxLcuNav()).get(f"/lol-chat/v1/{name}")


@pytest.mark.parametrize(
    "method, endpoint",
    [
        ("POST", "/lol-chat/v1/conversations"),
        ("POST", "/lol-chat/v1/conversations/ami/messages"),
        ("PUT", "/lol-chat/v1/me"),
        ("DELETE", "/lol-chat/v1/friends/ami"),
        ("POST", "/lol-chat/v1/friend-requests"),
    ],
)
def test_aucune_ecriture_sur_le_chat(method, endpoint):
    with pytest.raises(ForbiddenEndpoint):
        LcuProxy(FauxLcuNav()).send(method, endpoint, {})
    with pytest.raises(ForbiddenEndpoint):
        LcuProxy(FauxLcuNav()).get("/lol-chat/v1/friend-groups")  # lecture non listée
