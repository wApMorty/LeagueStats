"""Régression client : le PC ralentit quand le client reste ouvert longtemps.

Symptôme (@pj35, 2026-10-30) : le client ouvert longtemps finit par faire ramer tout le PC. Mesuré sur
le vrai client : 52 % d'un cœur (renderer et GPU WebView2) fenêtre sans focus, y compris en pleine
partie, contre 2 % pour pythonw, dont la mémoire reste plate sur 95 sessions de plus de 2 h.

Cause racine : (1) `Motion.ambient` lance des animations `iterations: Infinity` (`data-spin`,
`data-glow`) sans jamais les annuler. Le moteur les garde vivantes après le remplacement de `#view`,
avec toute la page détachée, et continue de les calculer à chaque image : 16 538 nœuds retenus après
GC au lieu de 557, sur `/`, `/rang` et `/profil`. (2) Rien ne s'arrête sans focus : les braises
redessinent un canvas plein écran à chaque image (165 par seconde sur l'écran de @pj35).

Correctif : `Motion` suit ses animations sans fin, annule celles dont la cible a quitté le document à
chaque `ambient`, et `Motion.idle` les fige sans focus ; `shell.js` coupe aussi les braises et
`html[data-idle]` fige les animations CSS.

Prévention : ces tests exécutent le vrai `motion.js` et le vrai `shell.js` sous node, DOM factice.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC = Path(__file__).parent.parent.parent / "src" / "client" / "static"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node absent")

MOTION_HARNESS = r"""
const fs = require('fs');
global.window = global;
const attrs = new Set();
global.document = { documentElement: {
  hasAttribute: (name) => attrs.has(name),
  toggleAttribute: (name, on) => (on ? attrs.add(name) : attrs.delete(name), on),
} };
eval(fs.readFileSync(process.argv[1], 'utf8'));

const element = (dataset) => ({
  dataset, isConnected: true,
  animate(keyframes, timing) {
    const animation = { effect: { target: this }, timing, state: 'running',
      cancel() { this.state = 'cancelled'; }, pause() { this.state = 'paused'; }, play() { this.state = 'running'; } };
    this.animation = animation;
    return animation;
  },
});
const page = (...elements) => ({ querySelectorAll: (selector) => elements.filter(
  (el) => (selector === '[data-spin]' && el.dataset.spin) || (selector === '[data-glow]' && el.dataset.glow)) });

const spin = element({ spin: '90' }), glow = element({ glow: '2400' }), kept = element({ spin: '-90' });
Motion.ambient(page(spin, glow, kept), {});
const started = [spin, glow, kept].map((el) => el.animation.timing.iterations);
spin.isConnected = glow.isConnected = false;
Motion.ambient(page(), {});
const swept = [spin, glow, kept].map((el) => el.animation.state);
Motion.idle(true);
const paused = kept.animation.state;
const late = element({ spin: '45' });
Motion.ambient(page(late), {});
const pausedLate = late.animation.state;
Motion.idle(false);
const resumed = [kept.animation.state, late.animation.state];
console.log(JSON.stringify({ started, swept, paused, pausedLate, resumed }));
"""

SHELL_HARNESS = r"""
const fs = require('fs');
const handlers = {}, calls = [];
global.addEventListener = (name, fn) => (handlers[name] = fn);
global.window = global;
global.matchMedia = () => ({ matches: false, addEventListener() {} });
let focused = true, reduced = false;
const root = { dataset: {}, classList: { remove() {} } };
global.document = { documentElement: root, hasFocus: () => focused, addEventListener() {}, querySelector: () => null };
global.Motion = { opts: () => ({ reduced }), embers: (rate) => calls.push(['embers', rate]), idle: (on) => calls.push(['idle', on]) };
eval(fs.readFileSync(process.argv[1], 'utf8'));
const take = () => calls.splice(0);
const load = take();
focused = false; handlers.blur();
const blur = take();
focused = true; handlers.focus();
const focus = take();
reduced = true; handlers.focus();
const reducedCalls = take();
console.log(JSON.stringify({ load, blur, focus, reducedCalls }));
"""


def run(harness: str, script: str) -> dict:
    done = subprocess.run(
        ["node", "-e", harness, str(STATIC / script)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


@pytest.fixture(scope="module")
def motion() -> dict:
    return run(MOTION_HARNESS, "motion.js")


def test_les_animations_sans_fin_detachees_sont_annulees(motion):
    assert motion["started"] == [None, None, None]  # JSON sérialise Infinity en null
    assert motion["swept"] == ["cancelled", "cancelled", "running"]


def test_sans_focus_les_animations_sans_fin_sont_figees(motion):
    assert motion["paused"] == "paused"
    assert motion["pausedLate"] == "paused"  # page chargée pendant que la fenêtre est sans focus
    assert motion["resumed"] == ["running", "running"]


def test_shell_coupe_les_braises_sans_focus():
    shell = run(SHELL_HARNESS, "shell.js")
    assert shell["load"] == [["embers", 0.35], ["idle", False]]
    assert shell["blur"] == [["embers", 0], ["idle", True]]
    assert shell["focus"] == [["embers", 0.35], ["idle", False]]
    assert shell["reducedCalls"][0] == ["embers", 0]
