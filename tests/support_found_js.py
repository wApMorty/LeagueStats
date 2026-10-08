"""Banc `node` de `found.js` (SPEC-26) : exécute le vrai script avec un navigateur factice.

`document`, `Motion`, `htmx`, `Sse`, `fetch`, l'horloge et les minuteurs sont factices (horloge virtuelle :
une étape `advance` la fait avancer sans attendre). Aucun serveur, aucun client LoL. Les étapes :

- `{"state": {...}}` : sert cet état à `/found/state` puis relit (`Found.refresh`) ;
- `{"click": "accept" | "decline"}` : clic sur le bouton de l'overlay présent ;
- `{"advance": ms}` : avance l'horloge (minuteurs, sondage de 4 s, animations) ;
- `{"phase_event": {...}}` : événement du sujet `phase` du bus ;
- `{"htmx_load": true}` : le `#view` vient d'être remplacé.

`run_found` renvoie les compteurs et un instantané après chaque étape (`snaps`).
"""

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.config_client import client_config

STATIC = Path(__file__).parent.parent / "src" / "client" / "static"

HARNESS = r"""
const fs = require('fs');
const cfg = JSON.parse(fs.readFileSync(0, 'utf8'));
const def = (name, value) => Object.defineProperty(global, name, { value, configurable: true, writable: true });
const flush = () => new Promise((resolve) => setImmediate(resolve));

// Horloge virtuelle.
let now = 0, nextId = 1;
const timers = new Map();
def('performance', { now: () => now });
def('setTimeout', (fn, ms = 0) => (timers.set(nextId, { at: now + ms, fn, every: 0 }), nextId++));
def('setInterval', (fn, ms) => (timers.set(nextId, { at: now + ms, fn, every: ms }), nextId++));
const clear = (id) => timers.delete(id);
def('clearTimeout', clear);
def('clearInterval', clear);
async function advance(ms) {
  const end = now + ms;
  for (;;) {
    let best = null;
    for (const [id, t] of timers) if (t.at <= end && (!best || t.at < best.t.at)) best = { id, t };
    if (!best) break;
    now = Math.max(now, best.t.at);
    if (best.t.every) best.t.at += best.t.every;
    else timers.delete(best.id);
    best.t.fn();
    await flush();
  }
  now = end;
}

// DOM factice : `querySelector` renvoie toujours le même nœud pour un sélecteur donné.
const calls = { created: 0, seals: 0, ajax: [], pushed: [], go: [], posts: [] };
const body = { children: [], appendChild(node) { this.children.push(node); } };
const makeNode = () => {
  const found = {};
  return {
    className: '', style: {}, hidden: false, textContent: '', innerHTML: '', onclick: null, id: '', attrs: {},
    setAttribute(key, value) { this.attrs[key] = value; },
    querySelector(selector) { return (found[selector] ??= makeNode()); },
    querySelectorAll: () => [],
    getAnimations: () => [],
    animate(frames, options) {
      const animation = { onfinish: null, playbackRate: 1 };
      setTimeout(() => animation.onfinish?.(), (options?.delay ?? 0) + (options?.duration ?? 0));
      return animation;
    },
    remove() { body.children.splice(body.children.indexOf(this), 1); },
  };
};
const pill = makeNode();
const view = makeNode();
const handlers = {};
def('document', {
  body,
  querySelector: (selector) => (selector.startsWith('meta') ? { content: 'x' } : selector === '.view' ? view : null),
  getElementById: (id) => (id === 'tb-center' ? pill : null),
  createElement: () => (calls.created++, makeNode()),
  addEventListener: (name, fn) => (handlers[name] = [...(handlers[name] || []), fn]),
  removeEventListener: (name, fn) => (handlers[name] = (handlers[name] || []).filter((h) => h !== fn)),
});
def('window', global);
def('location', { pathname: cfg.path });
def('history', { pushState: (state, title, path) => (location.pathname = path, calls.pushed.push(path)) });
def('htmx', { ajax: (method, path) => calls.ajax.push(`${method} ${path}`) });
if (cfg.transition) def('Transition', { go: (path) => calls.go.push(path) });
def('Motion', {
  opts: () => ({ sp: 1, reduced: cfg.reduced }), intro() {}, ambient() {}, center: () => [0, 0], converge() {},
  impact() {}, burst() {}, flash() {}, shake() {}, seal: () => calls.seals++, E: {}, C: {},
});
const sse = [];
def('Sse', { open: (topic, fn) => (sse.push({ topic, fn }), { abort() {} }) });

let served = { phase: 'None', ready_check: null, remaining: 0, total: 10, auto_accept: false };
def('fetch', async (url, init) => {
  if (init?.method === 'POST') calls.posts.push(url);
  return { ok: true, json: async () => served };
});
const windowHandlers = {};
global.addEventListener = (name, fn) => (windowHandlers[name] = fn);

const snapshot = () => {
  const overlay = body.children[0];
  return {
    overlays: body.children.length,
    buttons_hidden: overlay ? overlay.querySelector('#f-buttons').hidden : null,
    title: overlay ? overlay.querySelector('#f-title').textContent : null,
    sub: overlay ? overlay.querySelector('#f-sub').textContent : null,
    path: location.pathname,
  };
};

eval(fs.readFileSync(process.argv[1], 'utf8'));
(async () => {
  await windowHandlers.load();
  await flush();
  const snaps = [];
  for (const step of cfg.steps) {
    if ('state' in step) { served = step.state; await Found.refresh(); }
    else if ('phase_event' in step) sse.filter((l) => l.topic === 'phase').forEach((l) => l.fn('phase', step.phase_event));
    else if ('click' in step) await body.children[0]?.querySelector(step.click === 'accept' ? '#f-accept' : '#f-decline').onclick();
    else if ('advance' in step) await advance(step.advance);
    else if (step.htmx_load) (handlers['htmx:load'] || []).forEach((fn) => fn({ target: { id: 'view' } }));
    await flush();
    snaps.push(snapshot());
  }
  console.log(JSON.stringify({ ...calls, snaps }));
})();
"""


def run_found(
    steps: List[Dict[str, Any]],
    *,
    path: str = "/",
    reduced: bool = False,
    transition: bool = True,
) -> Dict[str, Any]:
    """Joue `steps` contre le vrai `found.js` ; saute le test si `node` est absent."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    done = subprocess.run(
        [node, "-e", HARNESS, str(STATIC / "found.js")],
        input=json.dumps(
            {"steps": steps, "path": path, "reduced": reduced, "transition": transition}
        ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=60,
    )
    return json.loads(done.stdout)


def served(
    phase: str, response: str = "None", check_state: str = "InProgress", *, no_check: bool = False
) -> Dict[str, Dict[str, Any]]:
    """L'étape « le serveur sert cet état » : `ready_check` n'existe qu'en `ReadyCheck`."""
    ready = None
    if phase == "ReadyCheck" and not no_check:
        ready = {"state": check_state, "response": response}
    return {
        "state": {
            "phase": phase,
            "ready_check": ready,
            "remaining": 9.0,
            "total": client_config.FOUND_SECONDS,
            "auto_accept": False,
            "hold_max": client_config.FOUND_HOLD_MAX_S,
            "enter_wait": client_config.FOUND_ENTER_WAIT_S,
        }
    }
