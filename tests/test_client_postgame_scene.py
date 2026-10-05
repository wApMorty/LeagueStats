"""Mise en scène du post-game (SPEC-21 tâche 95) : sceau, courbe à l'encre, marqueurs, pile d'impact,
compteur de LP. Le motion n'est pas testable en pytest (SPEC-21 §4.9) : on vérifie ici le balisage que
`motion.js` lit (attributs `data-*`) et, sous node, le câblage de `coaching.js` avec un `Motion` factice.
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.assets import Assets
from tests.test_client_parties import capture, impact
from tests.test_client_postgame import modele  # noqa: F401 - fixture
from tests.test_coaching_capture import GAME_ID

LOCAL = "http://127.0.0.1"
STATIC = Path(__file__).parent.parent / "src" / "client" / "static"


@pytest.fixture
def web(temp_db, tmp_path):
    assets = Assets(tmp_path / "cache", fetch=lambda url: None)
    return TestClient(
        create_app(temp_db, assets=assets), base_url=LOCAL, raise_server_exceptions=False
    )


def lp(db, delta, after):
    db.insert_rank_snapshot(
        queue="RANKED_SOLO_5x5",
        tier="EMERALD",
        division="II",
        lp=after,
        wins=62,
        losses=55,
        lp_delta=delta,
        game_id=GAME_ID,
    )


# ---------- balisage ----------


def test_victoire_sceau_mint_anneaux_et_compteur(db, web, modele):  # noqa: F811
    capture(db, pid=1)
    impact(db)
    lp(db, 18, 65)
    page = web.get("/postgame").text
    assert 'class="seal win" data-seal="1"' in page
    assert page.count('data-shock="1"') == 2
    assert '+<span data-count="18" data-delay="700">18</span> LP' in page
    assert "Émeraude II · 65 LP" in page


def test_defaite_sceau_rose_et_compteur_negatif(db, web, modele):  # noqa: F811
    capture(db, pid=6)
    lp(db, -17, 47)
    page = web.get("/postgame").text
    assert 'class="seal loss" data-seal="1"' in page
    assert '−<span data-count="17" data-delay="700">17</span> LP' in page


def test_courbe_a_l_encre_et_marqueurs_qui_apparaissent(db, web, modele):  # noqa: F811
    capture(db, pid=1)
    impact(db)
    page = web.get("/postgame").text
    assert re.search(r'<path class="ch-line" data-trace="2600" data-delay="400"', page)
    marks = re.findall(r'<g class="ch-mark" data-pop="1" data-delay="(\d+)"', page)
    assert marks and all(
        300 <= int(delay) <= 2900 for delay in marks
    )  # le long du tracé (400 ms à 3 s)
    assert 'data-fade="1"' in page  # l'aire apparaît quand le tracé s'achève


def test_pile_d_impact_un_evenement_apres_l_autre(db, web, modele):  # noqa: F811
    capture(db, pid=1)
    impact(db)
    page = web.get("/postgame").text
    delays = [
        int(d) for d in re.findall(r'class="impact-row" data-stack="1" data-delay="(\d+)"', page)
    ]
    assert len(delays) >= 2
    assert delays == sorted(delays) and delays[1] - delays[0] == 110
    assert 'data-bar="x"' in page and "toi" in page  # barres divergentes, « toi » pour les miens


def test_rien_a_animer_sans_partie(web):
    page = web.get("/postgame").text
    assert "data-seal" not in page and "data-stack" not in page


# ---------- câblage de coaching.js sous node ----------

HARNESS = r"""
const fs = require("fs");
const [file, scenario] = process.argv.slice(1);
const sc = JSON.parse(scenario);
const listeners = {}, calls = [], timers = [];
const page = { tag: "page" }, wrap = { tag: "wrap" };
const seal = {
  classList: { contains: (name) => name === sc.className },
  closest: () => page,
  parentElement: wrap,
};
const root = { querySelector: () => seal, querySelectorAll: () => [] };
const context = {
  document: { addEventListener: (name, fn) => (listeners[name] = fn), getElementById: () => null },
  window: {},
  Motion: {
    opts: () => ({ sp: 1, reduced: sc.reduced }),
    E: { entree: "" },
    C: { mint: "mint", gold: "gold", white: "white", rose: "rose", copper: "copper" },
    seal: (el, options) => calls.push({ fn: "seal", el: el.tag, ...options, target: options.target.tag }),
    shake: (el, amplitude, duration) => calls.push({ fn: "shake", el: el.tag, amplitude, duration }),
  },
  setTimeout: (fn, ms) => timers.push({ fn, ms }),
};
require("vm").runInNewContext(fs.readFileSync(file, "utf8"), context);
const load = () => listeners["htmx:load"]({ target: root });
load();
if (sc.twice) load();
const queued = [];
while (timers.length) { const t = timers.shift(); queued.push(t.ms); t.fn(); }
console.log(JSON.stringify({ calls, queued }));
"""


def run_scene(**scenario):
    result = subprocess.run(
        ["node", "-e", HARNESS, str(STATIC / "coaching.js"), json.dumps(scenario)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node absent")


@needs_node
def test_le_sceau_de_victoire_est_appose_avec_la_secousse():
    out = run_scene(className="win", reduced=False)
    seal, shake = out["calls"]
    assert out["queued"] == [150, 440]
    assert (seal["fn"], seal["el"], seal["target"], seal["reduced"]) == (
        "seal",
        "wrap",
        "page",
        False,
    )
    assert seal["colors"] == ["mint", "gold", "white"]
    assert (shake["fn"], shake["el"], shake["amplitude"], shake["duration"]) == (
        "shake",
        "page",
        9,
        460,
    )


@needs_node
def test_le_sceau_de_defaite_est_rose_et_cuivre():
    out = run_scene(className="loss", reduced=False)
    assert out["calls"][0]["colors"] == ["rose", "copper", "white"]


@needs_node
def test_en_mode_reduit_le_sceau_est_pose_sans_secousse():
    out = run_scene(className="win", reduced=True)
    assert [c["fn"] for c in out["calls"]] == ["seal"]  # pas de secousse
    assert out["calls"][0]["reduced"] is True  # `Motion.seal` pose alors le sceau tout de suite


@needs_node
def test_le_sceau_n_est_appose_qu_une_fois():
    out = run_scene(className="win", reduced=False, twice=True)
    assert [c["fn"] for c in out["calls"]] == ["seal", "shake"]
