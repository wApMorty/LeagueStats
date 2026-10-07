"""SPEC-25 tâche 116 : pastille de phase de la barre de titre, sujet `phase` par SSE, `LiveGame`.

Hermétique : bus en mémoire, base temporaire, serveur local de test. Aucun client LoL, aucune
fenêtre réelle : le rendu visuel est à voir par @pj35.
"""

import re
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from src.client import launch
from src.client.app import create_app
from src.client.bus import EventBus
from src.config_client import client_config
from src.config_constants import draft_config
from src.draft.phase_tracker import PhaseTracker
from tests.test_client_draft import LOCAL, assets, bus  # noqa: F401  (fixtures)
from tests.test_client_temps_reel import live, read_sse  # noqa: F401  (fixtures)

SIX_ETATS = {
    "idle": "Hors partie",
    "queue": "En file",
    "draft": "Champion select",
    "game": "En partie",
    "post": "Fin de partie",
    "closed": "Client LoL fermé",
}


@pytest.fixture
def client(temp_db, bus, assets):  # noqa: F811
    return TestClient(create_app(temp_db, bus=bus, assets=assets), base_url=LOCAL)


def pill(html):
    return re.search(r'<a class="chip [^"]*" id="tb-phase".*?</a>', html, re.S).group(0)


def test_les_six_etats_sont_rendus_avec_leur_libelle(client, bus):  # noqa: F811
    for kind, label in SIX_ETATS.items():
        bus.publish("phase", {"phase": "x", "kind": kind, "since": 0.0})
        html = pill(client.get("/").text)
        assert f'<span id="tb-phase-text">{label}</span>' in html, kind
        assert ("chip-closed" in html) == (kind == "closed"), kind


def test_sans_phase_publiee_la_pastille_dit_client_ferme(client):
    assert "Client LoL fermé</span>" in pill(client.get("/").text)


def test_sans_bus_la_pastille_dit_client_ferme(temp_db):
    page = TestClient(create_app(temp_db), base_url=LOCAL).get("/").text
    assert "Client LoL fermé</span>" in pill(page)


def test_chaque_famille_de_phase_a_un_libelle():
    kinds = set(draft_config.PHASE_KINDS.values()) | {"post", "closed", "unknown"}
    assert kinds <= set(client_config.PHASE_LABELS)
    assert set(SIX_ETATS.values()) <= set(client_config.PHASE_LABELS.values())


def test_le_script_suit_le_sujet_phase_sans_changer_de_page():
    source = open("src/client/static/en_partie.js", encoding="utf-8").read()
    assert '"phase"' in source and "tb-phase" in source
    assert "location" not in source and "hx-get" not in source


def test_sse_relaie_le_sujet_phase(live):  # noqa: F811
    bus, url, token = live
    charge = {"phase": "EndOfGame", "kind": "post", "since": 1.0}
    got = read_sse(url, token, "?topic=phase", lambda: bus.publish("phase", charge), 1)
    assert got == [{"event": "phase", "data": charge}]


def test_le_tracker_publie_sur_le_bus_ce_que_la_pastille_affiche(client, bus):  # noqa: F811
    tracker = PhaseTracker(lambda: None, bus=bus)
    tracker.observe("PreEndOfGame")
    assert "Fin de partie</span>" in pill(client.get("/").text)
    tracker.observe("Lobby")
    assert "Hors partie</span>" in pill(client.get("/").text)


def test_live_game_prend_la_phase_du_tracker_puis_de_la_sonde():
    bus = EventBus()
    lcu = Mock(credentials=None)
    lcu.find_lcu_credentials.return_value = None  # client fermé : la sonde ne répond rien
    read = launch._phase_source(bus, lcu)
    assert read() is None  # tracker muet, sonde muette
    bus.publish("phase", {"phase": "InProgress", "kind": "game", "since": 0.0})
    assert read() == "InProgress"
    bus.publish("phase", {"phase": None, "kind": "closed", "since": 1.0})
    assert read() is None
