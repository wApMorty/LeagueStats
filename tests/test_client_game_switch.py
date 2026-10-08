"""Bascule automatique vers « En partie » à la fin de la draft (SPEC-26 tâche 120)."""

import re
import shutil
import subprocess

import pytest

from tests.support_found_js import STATIC, run_found


def phase(kind, name=None):
    return {"phase_event": {"phase": name or kind, "kind": kind, "since": 0}}


@pytest.mark.parametrize("path", ["/draft", "/historique"])
def test_draft_puis_game_bascule_une_fois_vers_en_partie(path):
    result = run_found(
        [phase("draft", "ChampSelect"), phase("game", "GameStart"), phase("game", "InProgress")],
        path=path,
    )
    assert result["go"] == ["/en-partie"]


@pytest.mark.parametrize(
    "events",
    [
        [phase("game"), phase("game")],  # premier événement vu en partie, puis reconnexion
        [phase("draft"), phase("queue")],  # esquive
        [phase("game")],  # client ouvert en pleine partie
        [phase("queue"), phase("game")],
        [phase("draft"), phase("draft")],
    ],
)
def test_aucune_bascule_hors_draft_vers_game(events):
    assert run_found(events)["go"] == []


def test_deja_sur_en_partie_rien_a_faire():
    assert run_found([phase("draft"), phase("game")], path="/en-partie")["go"] == []


def test_sans_transition_la_navigation_htmx_prend_le_relais():
    result = run_found([phase("draft"), phase("game")], path="/draft", transition=False)
    assert result["pushed"] == ["/en-partie"] and result["ajax"] == ["GET /en-partie"]


def test_une_deuxieme_partie_rebascule():
    result = run_found(
        [phase("draft"), phase("game"), phase("idle"), phase("draft"), phase("game")], path="/"
    )
    assert result["go"] == ["/en-partie", "/en-partie"]


def test_transition_expose_go_et_en_partie_js_ne_navigue_toujours_pas():
    assert "window.Transition = { go }" in (STATIC / "transition.js").read_text(encoding="utf-8")
    source = (STATIC / "en_partie.js").read_text(encoding="utf-8")
    assert not re.search(r"pushState|htmx\.ajax|location", source)


@pytest.mark.parametrize("script", ["found.js", "transition.js"])
def test_scripts_sans_erreur_de_syntaxe(script):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node absent")
    assert (
        subprocess.run([node, "--check", str(STATIC / script)], capture_output=True).returncode == 0
    )
