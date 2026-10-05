"""Écran Lobby du client (SPEC-21 tâche 80) : files proposées, lobby, postes, créer et quitter."""

import copy
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.lcu_proxy import WRITES, ForbiddenEndpoint, LcuProxy
from src.client.lobby import lobby_view, queue_choices
from src.config_client import client_config
from tests.support_lcu_nav import FauxLcuNav, fixture, make_assets

LOCAL = "http://127.0.0.1"
LOBBY = "/lol-lobby/v2/lobby"
POSITIONS = f"{LOBBY}/members/localMember/position-preferences"


def web(temp_db, tmp_path, lcu):
    app = create_app(temp_db, lcu=lcu, assets=make_assets(tmp_path))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def post(client, path, token=True):
    headers = {client_config.TOKEN_HEADER: client.app.state.session_token} if token else {}
    return client.post(path, headers=headers)


def lcu_in(phase, **overrides):
    lcu = FauxLcuNav(overrides)
    lcu.phase = phase
    return lcu


def lcu_out(phase="None"):
    return lcu_in(phase, **{LOBBY: None})


class FauxLcuRefuse(FauxLcuNav):
    """Le client LoL répond aux lectures mais refuse toute écriture."""

    def _make_request(self, endpoint, method="GET", data=None):
        result = super()._make_request(endpoint, method, data)
        return result if method == "GET" else None


# ---------- files proposées ----------


def test_les_files_proposees_sont_celles_de_la_faille_et_de_l_aram():
    groups = queue_choices(fixture("queues"))
    names = {g["label"]: [q["name"] for q in g["queues"]] for g in groups}
    assert names["Joueur contre joueur"] == [
        "ARAM",
        "Classée flexible",
        "Classée solo/duo",
        "Normale (draft)",
        "Partie rapide",
    ]
    assert names["Contre l'IA"] == ["Beginner"]


def test_files_personnalisees_tft_et_indisponibles_exclues():
    ids = {q["id"] for g in queue_choices(fixture("queues")) for q in g["queues"]}
    assert not ids & {3100, 1100, 721}  # personnalisée, TFT, désactivée par la plateforme


def test_les_postes_sont_signales_sur_les_files_qui_en_demandent():
    queues = {q["id"]: q for g in queue_choices(fixture("queues")) for q in g["queues"]}
    assert queues[420]["positions"] and not queues[450]["positions"]


# ---------- vue ----------


def test_vue_sans_lobby():
    view = lobby_view(None, fixture("queues"), "None")
    assert not view["in_lobby"] and view["can_create"] and view["choices"]


def test_vue_dans_un_lobby():
    view = lobby_view(fixture("lobby"), fixture("queues"), "Lobby")
    assert view["in_lobby"] and view["queue"] == "Classée solo/duo"
    assert [m["name"] for m in view["members"]] == ["Invocateur", "Joueur2"]
    assert view["members"][0]["mine"] and view["members"][0]["leader"]
    assert view["members"][0]["first"] == "Top" and view["members"][1]["second"] == "Bot"
    assert view["free_slots"] == 3 and view["positions"]["shown"] and view["can_leave"]


def test_pas_de_selecteur_de_poste_en_aram():
    lobby = copy.deepcopy(fixture("lobby"))
    lobby["gameConfig"].update(queueId=450, showPositionSelector=False)
    assert not lobby_view(lobby, fixture("queues"), "Lobby")["positions"]["shown"]


# ---------- routes ----------


def test_route_hors_lobby_propose_les_files(temp_db, tmp_path):
    lcu = lcu_out()
    response = web(temp_db, tmp_path, lcu).get("/lobby")
    assert response.status_code == 200
    assert "/lobby/creer?queue_id=420" in response.text and "Classée solo/duo" in response.text
    assert lcu.writes == []


def test_route_dans_un_lobby(temp_db, tmp_path):
    response = web(temp_db, tmp_path, lcu_in("Lobby")).get("/lobby")
    assert response.status_code == 200
    for text in ("Invocateur", "Joueur2", "Quitter le lobby", "Mes postes", "chef du groupe"):
        assert text in response.text


def test_le_fragment_n_est_pas_une_page(temp_db, tmp_path):
    response = web(temp_db, tmp_path, lcu_in("Lobby")).get("/lobby/etat")
    assert response.status_code == 200
    assert "<html" not in response.text and "Joueur2" in response.text


def test_client_ferme_et_file_illisible(temp_db, tmp_path):
    assert "Client LoL fermé" in web(temp_db, tmp_path, None).get("/lobby").text
    lcu = lcu_out()
    lcu.overrides["/lol-game-queues/v1/queues"] = None  # liste vide, pas d'erreur
    assert web(temp_db, tmp_path, lcu).get("/lobby").status_code == 200


def test_nom_de_joueur_echappe(temp_db, tmp_path):
    lobby = copy.deepcopy(fixture("lobby"))
    lobby["members"][1]["summonerName"] = "<script>alert(1)</script>"
    text = web(temp_db, tmp_path, lcu_in("Lobby", **{LOBBY: lobby})).get("/lobby").text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text


# ---------- actions ----------


def test_creer_un_lobby_ecrit_la_file_choisie(temp_db, tmp_path):
    lcu = lcu_out()
    response = post(web(temp_db, tmp_path, lcu), "/lobby/creer?queue_id=420")
    assert response.status_code == 200
    assert lcu.writes == [("POST", LOBBY, {"queueId": 420})]


@pytest.mark.parametrize("queue_id", [3100, 1100, 721, 999999])
def test_creer_une_file_hors_liste_est_refuse_sans_ecriture(temp_db, tmp_path, queue_id):
    lcu = lcu_out()
    response = post(web(temp_db, tmp_path, lcu), f"/lobby/creer?queue_id={queue_id}")
    assert response.status_code == 409 and lcu.writes == []


@pytest.mark.parametrize("phase", ["Matchmaking", "ReadyCheck", "ChampSelect", "InProgress"])
def test_creer_pendant_la_file_ou_la_partie_est_refuse(temp_db, tmp_path, phase):
    lcu = lcu_in(phase)
    response = post(web(temp_db, tmp_path, lcu), "/lobby/creer?queue_id=420")
    assert response.status_code == 409 and lcu.writes == []


def test_le_client_refuse_d_ouvrir_le_lobby(temp_db, tmp_path):
    lcu = FauxLcuRefuse({LOBBY: None})
    response = post(web(temp_db, tmp_path, lcu), "/lobby/creer?queue_id=420")
    assert response.status_code == 409 and "refusé" in response.json()["detail"]


def test_quitter_le_lobby(temp_db, tmp_path):
    lcu = lcu_in("Lobby")
    assert post(web(temp_db, tmp_path, lcu), "/lobby/quitter").status_code == 200
    assert [w[:2] for w in lcu.writes] == [("DELETE", LOBBY)]


@pytest.mark.parametrize("phase", ["Matchmaking", "None", "ChampSelect"])
def test_quitter_hors_lobby_ou_pendant_la_file_est_refuse(temp_db, tmp_path, phase):
    lcu = lcu_in(phase)
    assert post(web(temp_db, tmp_path, lcu), "/lobby/quitter").status_code == 409
    assert lcu.writes == []


def test_choisir_ses_postes(temp_db, tmp_path):
    lcu = lcu_in("Lobby")
    response = post(web(temp_db, tmp_path, lcu), "/lobby/postes?first=MIDDLE&second=BOTTOM")
    assert response.status_code == 200
    assert lcu.writes == [
        ("PUT", POSITIONS, {"firstPreference": "MIDDLE", "secondPreference": "BOTTOM"})
    ]


@pytest.mark.parametrize(
    "query", ["first=MIDDLE&second=MIDDLE", "first=ADC&second=TOP", "first=TOP&second=%3Cx%3E"]
)
def test_postes_invalides_refuses_sans_ecriture(temp_db, tmp_path, query):
    lcu = lcu_in("Lobby")
    assert post(web(temp_db, tmp_path, lcu), f"/lobby/postes?{query}").status_code == 409
    assert lcu.writes == []


def test_postes_sur_une_file_sans_selecteur(temp_db, tmp_path):
    lobby = copy.deepcopy(fixture("lobby"))
    lobby["gameConfig"].update(queueId=450, showPositionSelector=False)
    lcu = lcu_in("Lobby", **{LOBBY: lobby})
    response = post(web(temp_db, tmp_path, lcu), "/lobby/postes?first=TOP&second=JUNGLE")
    assert response.status_code == 409 and lcu.writes == []


def test_deux_remplissages_sont_permis(temp_db, tmp_path):
    lcu = lcu_in("Lobby")
    response = post(web(temp_db, tmp_path, lcu), "/lobby/postes?first=FILL&second=FILL")
    assert response.status_code == 200


@pytest.mark.parametrize(
    "path", ["/lobby/creer?queue_id=420", "/lobby/quitter", "/lobby/postes?first=TOP&second=JUNGLE"]
)
def test_sans_jeton_403_et_aucun_appel_lcu(temp_db, tmp_path, path):
    lcu = lcu_in("Lobby")
    assert post(web(temp_db, tmp_path, lcu), path, token=False).status_code == 403
    assert lcu.calls == []


# ---------- liste blanche (critère 6) ----------


@pytest.mark.parametrize(
    "method, endpoint",
    [
        ("POST", f"{LOBBY}/invitations"),  # inviter : hors périmètre
        ("DELETE", f"{LOBBY}/members/abc/kick"),
        ("POST", f"{LOBBY}/members/abc/promote"),
        ("POST", "/lol-chat/v1/conversations/x/messages"),  # écrire à un ami
        ("POST", "/lol-chat/v1/friend-requests"),
        ("PUT", "/lol-chat/v1/me"),
        ("POST", f"{LOBBY}/custom"),
    ],
)
def test_la_liste_blanche_refuse_invitations_chat_et_gestion_du_groupe(method, endpoint):
    lcu = FauxLcuNav()
    with pytest.raises(ForbiddenEndpoint):
        LcuProxy(lcu).send(method, endpoint, {})
    assert lcu.writes == []


def test_aucune_ecriture_ne_vise_le_chat_ni_les_invitations():
    assert not any("chat" in p.pattern or "invit" in p.pattern for _, p in WRITES)


# ---------- coque et script ----------


def test_la_coque_charge_lobby_js_apres_le_flux(temp_db, tmp_path):
    html = web(temp_db, tmp_path, None).get("/").text
    assert 'src="/static/lobby.js"' in html and html.index("sse.js") < html.index("lobby.js")
    assert 'href="/lobby"' in html  # l'entrée de navigation n'est plus grisée


def test_lobby_js_sans_erreur_de_syntaxe():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    script = Path(__file__).parent.parent / "src" / "client" / "static" / "lobby.js"
    assert subprocess.run([node, "--check", str(script)], capture_output=True).returncode == 0
