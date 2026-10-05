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


# ---------- un clic pendant la transition n'est pas perdu (écart relevé par la vérification) ----------

HARNESS = r"""
const fs = require('fs');
const handlers = {};
const calls = { ajax: [], pushed: [], prevented: 0 };
const node = () => ({
  style: {}, animate: () => ({}), getAnimations: () => [], querySelector: () => node(), querySelectorAll: () => [],
  setAttribute() {}, getAttribute: () => 'outerHTML swap:30ms', appendChild() {}, isConnected: true, id: 'view',
});
const meta = { content: JSON.stringify({ darken: 5, swap: 20, open: 30, slide: 5, runes: 4, nav_width: 220 }) };
global.document = {
  addEventListener: (name, fn) => (handlers[name] = [...(handlers[name] || []), fn]),
  querySelector: (sel) => (sel.startsWith('meta') ? meta : null),
  getElementById: () => node(),
  createElement: () => ({ ...node(), innerHTML: '', querySelector: () => node() }),
  body: { appendChild() {} },
};
global.addEventListener = () => {};
global.matchMedia = () => ({ addEventListener() {} });
global.history = { pushState: (...args) => calls.pushed.push(args[2]) };
global.htmx = { ajax: (...args) => calls.ajax.push(args.slice(0, 2).join(' ')) };
global.Motion = {
  opts: () => ({ sp: 1, reduced: false }), trace() {}, fixRings() {}, center: () => [0, 0], converge() {}, burst() {},
  flash() {}, shake() {}, E: {}, C: {},
};
eval(fs.readFileSync(process.argv[1], 'utf8'));
const fire = (name, detail, target) => {
  const event = { detail, target: target || {}, preventDefault: () => calls.prevented++ };
  (handlers[name] || []).forEach((fn) => fn(event));
};
const boosted = (path) => ({ requestConfig: { boosted: true, path }, pathInfo: { requestPath: path } });
(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  fire('htmx:beforeRequest', boosted('/a'));          // clic A : la transition démarre
  await wait(5);
  fire('htmx:beforeRequest', boosted('/b'));          // clic B pendant la transition
  fire('htmx:beforeRequest', boosted('/c'));          // clic C : seul le dernier est gardé
  const afterClicks = { ...calls, ajax: [...calls.ajax] };
  await wait(20);
  fire('htmx:load', {}, { id: 'view' });              // la page A est en place
  await wait(60);                                     // fin de l'ouverture
  console.log(JSON.stringify({ afterClicks, calls }));
})();
"""


def test_un_clic_pendant_la_transition_est_rejoue_apres_pas_perdu():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    done = subprocess.run(
        [node, "-e", HARNESS, str(STATIC / "transition.js")],
        capture_output=True,
        text=True,
        check=True,
    )
    result = json.loads(done.stdout)
    assert (
        result["afterClicks"]["prevented"] == 2
    )  # B et C n'ont pas lancé de requête qui viserait un #view détaché
    assert result["afterClicks"]["ajax"] == []  # rien n'est parti avant la fin de l'ouverture
    assert result["calls"]["ajax"] == ["GET /c"] and result["calls"]["pushed"] == ["/c"]


def test_refus_du_joueur_ne_rouvre_pas_l_overlay():
    source = (STATIC / "found.js").read_text(encoding="utf-8")
    assert 'response !== "Declined"' in source
    assert (
        "acceptation automatique à 4 s" not in source
    )  # le Live Coach accepte dès le tick suivant
