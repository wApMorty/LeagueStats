"""Partie trouvée du client (SPEC-21 tâche 93) : état de la file, accepter / refuser, liste blanche."""

import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.lcu_proxy import ForbiddenEndpoint, LcuProxy
from src.config_client import client_config
from src.user_prefs import UserPrefs, save_user_prefs
from tests.support_found_js import run_found, served

LOCAL = "http://127.0.0.1"
STATIC = Path(__file__).parent.parent / "src" / "client" / "static"


class FauxLcuFile:
    """LCU de la file : phase du client et ready-check ; chaque écriture est notée."""

    def __init__(self, phase="ReadyCheck", timer=3.0, refuses=False):
        self.credentials = object()
        self.phase = phase
        self.check = {"state": "InProgress", "playerResponse": "None", "timer": timer}
        self.refuses = refuses
        self.calls = []

    def find_lcu_credentials(self):
        return self.credentials

    def _make_request(self, endpoint, method="GET", data=None):
        self.calls.append((method, endpoint))
        if method != "GET":
            return None if self.refuses else {}
        if endpoint == "/lol-gameflow/v1/gameflow-phase":
            return self.phase
        if endpoint == "/lol-matchmaking/v1/ready-check":
            return self.check
        return None


@pytest.fixture(autouse=True)
def _prefs_isolees(monkeypatch, tmp_path):
    monkeypatch.setattr("src.user_prefs.get_user_prefs_path", lambda: str(tmp_path / "prefs.json"))


def make(temp_db, lcu):
    app = create_app(temp_db, lcu=lcu)
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def post(client, path, token=True):
    headers = {client_config.TOKEN_HEADER: client.app.state.session_token} if token else {}
    return client.post(path, headers=headers)


def writes(lcu):
    return [call for call in lcu.calls if call[0] != "GET"]


# ---------- état ----------


def test_partie_trouvee_compte_a_rebours_depuis_le_timer_du_lcu(temp_db):
    lcu = FauxLcuFile(timer=3.5)
    state = make(temp_db, lcu).get("/found/state").json()
    assert state["phase"] == "ReadyCheck" and state["total"] == client_config.FOUND_SECONDS
    assert state["remaining"] == pytest.approx(client_config.FOUND_SECONDS - 3.5)
    assert state["ready_check"] == {"state": "InProgress", "response": "None"}


def test_l_etat_porte_le_garde_fou_et_l_attente_d_entree(temp_db):
    state = make(temp_db, FauxLcuFile()).get("/found/state").json()
    assert state["hold_max"] == client_config.FOUND_HOLD_MAX_S == 30.0
    assert state["enter_wait"] == client_config.FOUND_ENTER_WAIT_S == 1.5


def test_le_compte_a_rebours_ne_devient_jamais_negatif(temp_db):
    state = make(temp_db, FauxLcuFile(timer=99.0)).get("/found/state").json()
    assert state["remaining"] == 0.0


def test_hors_file_trouvee_pas_de_ready_check(temp_db):
    lcu = FauxLcuFile(phase="ChampSelect")
    state = make(temp_db, lcu).get("/found/state").json()
    assert state["phase"] == "ChampSelect" and state["ready_check"] is None
    assert (
        "GET",
        "/lol-matchmaking/v1/ready-check",
    ) not in lcu.calls  # lu seulement en file trouvée


def test_client_ferme_phase_inconnue_sans_erreur(temp_db):
    state = make(temp_db, None).get("/found/state").json()
    assert state["phase"] is None and state["ready_check"] is None


def test_auto_accept_du_live_coach_signale(temp_db):
    assert make(temp_db, FauxLcuFile()).get("/found/state").json()["auto_accept"] is False
    save_user_prefs(UserPrefs(auto_accept_queue=True))
    assert make(temp_db, FauxLcuFile()).get("/found/state").json()["auto_accept"] is True


# ---------- réponse ----------


def test_accepter_ecrit_sur_le_ready_check(temp_db):
    lcu = FauxLcuFile()
    response = post(make(temp_db, lcu), "/found/accept")
    assert response.status_code == 200 and response.json() == {"answer": "accept"}
    assert writes(lcu) == [("POST", "/lol-matchmaking/v1/ready-check/accept")]


def test_refuser(temp_db):
    lcu = FauxLcuFile()
    assert post(make(temp_db, lcu), "/found/decline").status_code == 200
    assert writes(lcu) == [("POST", "/lol-matchmaking/v1/ready-check/decline")]


@pytest.mark.parametrize("phase", ["Lobby", "Matchmaking", "ChampSelect", "None"])
def test_repondre_hors_file_trouvee_est_refuse_sans_ecriture(temp_db, phase):
    lcu = FauxLcuFile(phase=phase)
    response = post(make(temp_db, lcu), "/found/accept")
    assert response.status_code == 409 and "Aucune partie trouvée" in response.json()["detail"]
    assert writes(lcu) == []


def test_reponse_inconnue_refusee_sans_appel(temp_db):
    lcu = FauxLcuFile()
    response = post(make(temp_db, lcu), "/found/state")
    assert response.status_code == 409 and lcu.calls == []


def test_sans_jeton_403_et_aucun_appel_lcu(temp_db):
    lcu = FauxLcuFile()
    assert post(make(temp_db, lcu), "/found/accept", token=False).status_code == 403
    assert lcu.calls == []


def test_le_client_refuse_la_reponse(temp_db):
    response = post(make(temp_db, FauxLcuFile(refuses=True)), "/found/accept")
    assert response.status_code == 409 and "refusé" in response.json()["detail"]


def test_client_ferme_la_reponse_est_refusee(temp_db):
    assert post(make(temp_db, None), "/found/accept").status_code == 409


def test_liste_blanche_n_ouvre_que_accepter_et_refuser():
    lcu = FauxLcuFile()
    proxy = LcuProxy(lcu)
    proxy.send("POST", "/lol-matchmaking/v1/ready-check/accept")
    for method, endpoint in [
        ("POST", "/lol-matchmaking/v1/ready-check/other"),
        ("POST", "/lol-matchmaking/v1/search"),  # lancer la file : tâche 81
        ("DELETE", "/lol-matchmaking/v1/ready-check/accept"),
    ]:
        with pytest.raises(ForbiddenEndpoint):
            proxy.send(method, endpoint)
    assert len(writes(lcu)) == 1


# ---------- coque et scripts ----------


def test_la_coque_porte_la_pastille_champ_select_et_les_scripts(temp_db):
    html = make(temp_db, None).get("/").text
    assert 'id="tb-center" hidden' in html and "Champ select en cours" in html
    for script in ("sse.js", "found.js"):
        assert f'src="/static/{script}"' in html
    assert html.index("sse.js") < html.index("draft.js")  # le flux est défini avant ses clients


@pytest.mark.parametrize("script", ["sse.js", "found.js", "draft.js"])
def test_scripts_sans_erreur_de_syntaxe(script):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    assert (
        subprocess.run([node, "--check", str(STATIC / script)], capture_output=True).returncode == 0
    )


# ---------- overlay accepté (SPEC-26) : le vrai found.js sous node ----------

ACCEPTED = [served("ReadyCheck"), {"click": "accept"}, {"advance": 2000}]


def test_echec_apres_acceptation_message_puis_retrait_sans_navigation():
    result = run_found([*ACCEPTED, served("Matchmaking"), {"advance": 1000}])
    leaving = result["snaps"][3]
    assert leaving["overlays"] == 1 and "Un joueur n'a pas accepté" in leaving["sub"]
    assert result["snaps"][-1]["overlays"] == 0
    assert result["ajax"] == [] and result["pushed"] == [] and result["created"] == 1


def test_client_ferme_apres_acceptation_efface_l_overlay():
    result = run_found([*ACCEPTED, {"state": {**served("None")["state"], "phase": None}}])
    assert "Un joueur n'a pas accepté" in result["snaps"][3]["sub"]
    assert result["ajax"] == []


@pytest.mark.parametrize("kwargs", [{"no_check": True}, {"check_state": "Invalid"}])
def test_ready_check_absent_ou_autre_etat_apres_acceptation_l_overlay_est_tenu(kwargs):
    result = run_found([*ACCEPTED, served("ReadyCheck", "Accepted", **kwargs), {"advance": 3000}])
    assert result["created"] == 1 and result["seals"] == 1
    assert result["snaps"][-1]["overlays"] == 1 and result["snaps"][-1]["buttons_hidden"] is True
    assert result["snaps"][-1]["title"] == "Acceptée"


def test_garde_fou_hold_max_efface_l_overlay_sans_le_rouvrir():
    over = int(client_config.FOUND_HOLD_MAX_S * 1000) + 1000
    result = run_found(
        [*ACCEPTED, served("ReadyCheck", "Accepted"), {"advance": over}, {"advance": 5000}]
    )
    assert result["snaps"][4]["overlays"] == 0  # effacé après 30 s sans changement de phase
    assert (
        result["snaps"][5]["overlays"] == 0 and result["created"] == 1
    )  # le sondage ne le rouvre pas
    assert result["ajax"] == []


def test_tenu_avant_le_garde_fou():
    result = run_found([*ACCEPTED, served("ReadyCheck", "Accepted"), {"advance": 25000}])
    assert result["snaps"][-1]["overlays"] == 1


def test_auto_accept_reponse_deja_acceptee_un_overlay_une_sequence():
    result = run_found(
        [served("ReadyCheck", "Accepted"), {"advance": 2000}, served("ReadyCheck", "Accepted")]
    )
    assert result["created"] == 1 and result["seals"] == 1
    assert result["snaps"][-1]["overlays"] == 1 and result["snaps"][-1]["buttons_hidden"] is True


def test_champ_select_avant_la_reponse_du_navigateur_joue_la_sequence_puis_entre():
    result = run_found([served("ReadyCheck"), served("ChampSelect"), {"advance": 5000}])
    assert result["seals"] == 1 and result["ajax"] == ["GET /draft"]
    assert result["snaps"][-1]["overlays"] == 0


def test_entree_en_draft_attend_le_chargement_de_la_page():
    result = run_found([*ACCEPTED, served("ChampSelect"), {"advance": 300}])
    assert (
        result["ajax"] == ["GET /draft"] and result["snaps"][-1]["overlays"] == 1
    )  # sous l'overlay
    result = run_found([*ACCEPTED, served("ChampSelect"), {"htmx_load": True}, {"advance": 700}])
    assert (
        result["snaps"][-1]["overlays"] == 0
    )  # effondrement dès le chargement, avant `enter_wait`


def test_deja_sur_la_draft_pas_de_navigation_et_l_overlay_se_retire():
    result = run_found([*ACCEPTED, served("ChampSelect"), {"advance": 700}], path="/draft")
    assert result["ajax"] == [] and result["snaps"][-1]["overlays"] == 0


def test_refus_du_joueur_retire_l_overlay_sans_le_rouvrir():
    result = run_found(
        [
            served("ReadyCheck"),
            {"click": "decline"},
            {"advance": 1000},
            served("ReadyCheck", "Declined"),
        ]
    )
    assert result["snaps"][-1]["overlays"] == 0 and result["created"] == 1
    assert result["posts"] == ["/found/decline"]


def test_mode_reduit_aucune_animation_navigation_et_retrait_immediats():
    result = run_found([*ACCEPTED, served("ChampSelect")], reduced=True)
    assert result["seals"] == 0 and result["ajax"] == ["GET /draft"]
    assert result["snaps"][-1]["overlays"] == 0
