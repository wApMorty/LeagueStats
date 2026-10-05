"""File d'attente du client (SPEC-21 tâche 81) : état de la barre de titre, lancer, annuler."""

import copy
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.lcu_proxy import ForbiddenEndpoint, LcuProxy
from src.client.lobby import file_state
from src.config_client import client_config
from src.user_prefs import UserPrefs, save_user_prefs
from tests.support_lcu_nav import FauxLcuNav, fixture, make_assets

LOCAL = "http://127.0.0.1"
LOBBY = "/lol-lobby/v2/lobby"
SEARCH = f"{LOBBY}/matchmaking/search"
SEARCH_STATE = f"{SEARCH}-state"
STATIC = Path(__file__).parent.parent / "src" / "client" / "static"


@pytest.fixture(autouse=True)
def _prefs_isolees(monkeypatch, tmp_path):
    monkeypatch.setattr("src.user_prefs.get_user_prefs_path", lambda: str(tmp_path / "prefs.json"))


def web(temp_db, tmp_path, lcu):
    app = create_app(temp_db, lcu=lcu, assets=make_assets(tmp_path))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def post(client, path, token=True):
    headers = {client_config.TOKEN_HEADER: client.app.state.session_token} if token else {}
    return client.post(path, headers=headers)


def lcu_in(phase, **overrides):
    lcu = FauxLcuNav(overrides)
    lcu.phase = phase
    if phase == "Matchmaking":
        lcu.overrides.setdefault(SEARCH_STATE, fixture("search_state_searching"))
    return lcu


class FauxLcuRefuse(FauxLcuNav):
    def _make_request(self, endpoint, method="GET", data=None):
        result = super()._make_request(endpoint, method, data)
        return result if method == "GET" else None


# ---------- état ----------


def test_dans_le_lobby_le_chef_peut_lancer():
    state = file_state(LcuProxy(lcu_in("Lobby")))
    assert state["can_start"] and not state["searching"] and state["queue"] == "Classée solo/duo"


def test_en_file_le_temps_et_l_estimation_viennent_du_client():
    state = file_state(LcuProxy(lcu_in("Matchmaking")))
    assert state["searching"] and not state["can_start"]
    assert (state["elapsed"], state["estimated"]) == (47.5, 190.0)


def test_hors_lobby_rien_n_est_propose():
    lcu = lcu_in("None", **{LOBBY: None})
    state = file_state(LcuProxy(lcu))
    assert not state["can_start"] and not state["in_lobby"] and not state["searching"]
    assert (("GET", LOBBY, None)) not in lcu.calls  # lobby lu seulement dans le lobby ou en file


def test_un_membre_qui_n_est_pas_chef_ne_peut_pas_lancer():
    lobby = copy.deepcopy(fixture("lobby"))
    lobby["localMember"]["allowedStartActivity"] = False
    assert not file_state(LcuProxy(lcu_in("Lobby", **{LOBBY: lobby})))["can_start"]


def test_lobby_qui_ne_peut_pas_demarrer():
    lobby = copy.deepcopy(fixture("lobby"))
    lobby["canStartActivity"] = False
    assert not file_state(LcuProxy(lcu_in("Lobby", **{LOBBY: lobby})))["can_start"]


def test_auto_accept_du_live_coach_signale():
    assert file_state(LcuProxy(lcu_in("Lobby")))["auto_accept"] is False
    save_user_prefs(UserPrefs(auto_accept_queue=True))
    assert file_state(LcuProxy(lcu_in("Lobby")))["auto_accept"] is True


def test_route_etat(temp_db, tmp_path):
    state = web(temp_db, tmp_path, lcu_in("Matchmaking")).get("/file/state").json()
    assert state["searching"] and state["phase"] == "Matchmaking"


def test_etat_client_ferme(temp_db, tmp_path):
    state = web(temp_db, tmp_path, None).get("/file/state").json()
    assert state["phase"] is None and not state["can_start"]


# ---------- lancer et annuler ----------


def test_lancer_la_file_ecrit_la_recherche(temp_db, tmp_path):
    lcu = lcu_in("Lobby")
    assert post(web(temp_db, tmp_path, lcu), "/file/lancer").status_code == 200
    assert [w[:2] for w in lcu.writes] == [("POST", SEARCH)]


@pytest.mark.parametrize(
    "phase", ["Matchmaking", "None", "ReadyCheck", "ChampSelect", "InProgress"]
)
def test_lancer_hors_lobby_ou_deja_en_file_est_refuse(temp_db, tmp_path, phase):
    lcu = lcu_in(phase)
    assert post(web(temp_db, tmp_path, lcu), "/file/lancer").status_code == 409
    assert lcu.writes == []


def test_lancer_sans_etre_chef_est_refuse(temp_db, tmp_path):
    lobby = copy.deepcopy(fixture("lobby"))
    lobby["localMember"]["allowedStartActivity"] = False
    lcu = lcu_in("Lobby", **{LOBBY: lobby})
    response = post(web(temp_db, tmp_path, lcu), "/file/lancer")
    assert response.status_code == 409 and "chef" in response.json()["detail"]
    assert lcu.writes == []


def test_lancer_avec_une_restriction_dit_laquelle(temp_db, tmp_path):
    lobby = copy.deepcopy(fixture("lobby"))
    lobby.update(
        canStartActivity=False, restrictions=[{"restrictionCode": "PlayerLevelRestriction"}]
    )
    lcu = lcu_in("Lobby", **{LOBBY: lobby})
    response = post(web(temp_db, tmp_path, lcu), "/file/lancer")
    assert response.status_code == 409 and "PlayerLevelRestriction" in response.json()["detail"]
    assert lcu.writes == []


def test_le_client_refuse_de_lancer(temp_db, tmp_path):
    lcu = FauxLcuRefuse()
    lcu.phase = "Lobby"
    response = post(web(temp_db, tmp_path, lcu), "/file/lancer")
    assert response.status_code == 409 and "refusé" in response.json()["detail"]


def test_annuler_la_recherche(temp_db, tmp_path):
    lcu = lcu_in("Matchmaking")
    assert post(web(temp_db, tmp_path, lcu), "/file/annuler").status_code == 200
    assert [w[:2] for w in lcu.writes] == [("DELETE", SEARCH)]


@pytest.mark.parametrize("phase", ["Lobby", "None", "ReadyCheck", "ChampSelect"])
def test_annuler_hors_recherche_est_refuse(temp_db, tmp_path, phase):
    """Une partie trouvée ne s'annule pas : on la refuse par `/found/decline`."""
    lcu = lcu_in(phase)
    assert post(web(temp_db, tmp_path, lcu), "/file/annuler").status_code == 409
    assert lcu.writes == []


@pytest.mark.parametrize("path", ["/file/lancer", "/file/annuler"])
def test_sans_jeton_403_et_aucun_appel_lcu(temp_db, tmp_path, path):
    lcu = lcu_in("Lobby")
    assert post(web(temp_db, tmp_path, lcu), path, token=False).status_code == 403
    assert lcu.calls == []


# ---------- écran Lobby et liste blanche ----------


def test_l_ecran_lobby_propose_lancer_puis_annuler(temp_db, tmp_path):
    lobby = web(temp_db, tmp_path, lcu_in("Lobby")).get("/lobby").text
    assert "/file/lancer" in lobby and "/file/annuler" not in lobby
    searching = web(temp_db, tmp_path, lcu_in("Matchmaking")).get("/lobby").text
    assert "/file/annuler" in searching and "0:47" in searching and "3:10" in searching
    assert "/file/lancer" not in searching and "/lobby/quitter" not in searching


def test_la_liste_blanche_ouvre_la_recherche_du_lobby_et_rien_d_autre():
    lcu = FauxLcuNav()
    proxy = LcuProxy(lcu)
    proxy.send("POST", SEARCH)
    proxy.send("DELETE", SEARCH)
    for method, endpoint in [
        ("PUT", SEARCH),
        ("POST", "/lol-matchmaking/v1/search"),  # l'ancien chemin : non utilisé
        ("POST", f"{SEARCH}/accept"),
        ("POST", "/lol-lobby/v2/lobby/matchmaking/ready"),
    ]:
        with pytest.raises(ForbiddenEndpoint):
            proxy.send(method, endpoint)
    assert len(lcu.writes) == 2


def test_la_coque_porte_les_commandes_de_file_dans_la_barre_de_titre(temp_db, tmp_path):
    html = web(temp_db, tmp_path, None).get("/").text
    for text in ('id="tb-file-start" hidden', 'id="tb-file-search" hidden', 'id="tb-file-cancel"'):
        assert text in html
    assert html.index("sse.js") < html.index("file.js")


def test_file_js_sans_erreur_de_syntaxe():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    assert (
        subprocess.run([node, "--check", str(STATIC / "file.js")], capture_output=True).returncode
        == 0
    )


# ---------- forme inattendue du lobby (après un patch du client) ----------


@pytest.mark.parametrize("lobby", ["x", {"a": 1}, [1]])
def test_etat_de_la_file_sur_un_lobby_de_forme_inattendue_n_est_pas_une_500(
    temp_db, tmp_path, lobby
):
    response = web(temp_db, tmp_path, lcu_in("Lobby", **{LOBBY: lobby})).get("/file/state")
    assert response.status_code == 200 and response.json()["can_start"] is False


@pytest.mark.parametrize("path", ["/file/lancer", "/lobby/postes?first=TOP&second=JUNGLE"])
def test_action_sur_un_lobby_de_forme_inattendue_est_refusee_sans_ecriture(temp_db, tmp_path, path):
    lcu = lcu_in("Lobby", **{LOBBY: {"a": 1}})
    assert post(web(temp_db, tmp_path, lcu), path).status_code == 409
    assert lcu.writes == []
