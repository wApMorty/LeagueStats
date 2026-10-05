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
