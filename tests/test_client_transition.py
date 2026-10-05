"""Transition de page signature (SPEC-21 tâche 94) : ce que le serveur pose pour `transition.js`."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.config_client import client_config
from src.user_prefs import save_motion

LOCAL = "http://127.0.0.1"
STATIC = Path(__file__).parent.parent / "src" / "client" / "static"


@pytest.fixture(autouse=True)
def _prefs_isolees(monkeypatch, tmp_path):
    monkeypatch.setattr("src.user_prefs.get_user_prefs_path", lambda: str(tmp_path / "prefs.json"))


@pytest.fixture
def client(temp_db):
    return TestClient(create_app(temp_db), base_url=LOCAL, raise_server_exceptions=False)


def hx_swap(html):
    return re.search(r'<div id="view"[^>]*hx-swap="([^"]*)"', html).group(1)


def test_durees_de_la_transition_lues_depuis_la_config(client):
    html = client.get("/").text
    config = json.loads(re.search(r"name=\"page-transition\" content='([^']*)'", html).group(1))
    assert config == client_config.transition()
    assert (
        config["swap"] == 860
        and config["open"] == 820
        and config["runes"] == 44
        and config["slide"] == 520
    )
    assert (
        config["darken"] < config["swap"]
    )  # le contenu a fini de s'assombrir quand le cercle implose


def test_le_remplacement_attend_la_fin_de_l_implosion(client):
    assert hx_swap(client.get("/").text) == f"outerHTML swap:{client_config.TRANSITION_SWAP_MS}ms"


def test_mode_reduit_remplacement_instantane(client):
    save_motion("reduit")
    assert hx_swap(client.get("/").text) == "outerHTML"


@pytest.mark.parametrize("mode", ["complet", "systeme"])
def test_les_autres_modes_gardent_le_delai(client, mode):
    save_motion(mode)  # « Système » est ramené à l'instantané par le script si Windows le demande
    assert "swap:" in hx_swap(client.get("/").text)


def test_plus_de_view_transitions(client):
    html = client.get("/").text
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    assert "transition:true" not in html and "view-transition" not in css


def test_le_voile_ne_capte_aucun_clic():
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.tr-veil \{([^}]*)\}", css).group(1)
    assert "pointer-events: none" in rule and "position: fixed" in rule


def test_script_servi_et_charge_apres_motion(client):
    html = client.get("/").text
    assert client.get("/static/transition.js").status_code == 200
    assert html.index("motion.js") < html.index("transition.js")


def test_transition_js_sans_erreur_de_syntaxe():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    assert (
        subprocess.run(
            [node, "--check", str(STATIC / "transition.js")], capture_output=True
        ).returncode
        == 0
    )


def test_la_transition_ne_touche_que_les_navigations_boostees():
    source = (STATIC / "transition.js").read_text(encoding="utf-8")
    assert "requestConfig?.boosted" in source  # les fragments (pastille, draft) ne déclenchent rien
    assert 'event.target.id !== "view"' in source
