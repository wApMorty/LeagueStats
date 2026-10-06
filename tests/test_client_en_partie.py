"""SPEC-24 tâche 108 : écran « En partie », cadre, navigation, pastille, face-à-face de la draft.

Hermétique : bus en mémoire, base temporaire, analyse construite par `build_final_analysis` sur
l'évaluateur factice de `test_final_analysis_face_off`. Aucun client LoL, aucun test d'interface réel.
"""

import re

import pytest
from fastapi.testclient import TestClient

from src.client import en_partie
from src.client.app import create_app
from src.client.assets import Assets
from src.client.bus import EventBus
from src.draft.final_analysis import build_final_analysis
from tests import test_final_analysis_face_off as fo
from tests.test_client_draft import LOCAL, assets, bus  # noqa: F401  (fixtures)


@pytest.fixture
def client(temp_db, bus, assets):  # noqa: F811
    app = create_app(temp_db, bus=bus, assets=assets)
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def analysis(**kwargs):
    monitor = fo.make_monitor(**kwargs)
    return build_final_analysis(monitor, fo.ALLY_IDS, fo.ENEMY_IDS, fo.LANES_BY_ID).to_payload()


LIVE = {"state": "live", "game_time": 754.0, "p": 0.612, "delta": 0.031, "series": [[750.0, 0.6]]}


def stage(client):
    response = client.get("/en-partie/stage")
    assert response.status_code == 200
    return response.text


@pytest.mark.parametrize("payload", [None, {"state": "idle"}, LIVE, {**LIVE, "state": "ended"}])
def test_la_page_et_le_fragment_repondent_dans_les_trois_etats(client, bus, payload):  # noqa: F811
    if payload:
        bus.publish("ingame", payload)
    page = client.get("/en-partie")
    assert page.status_code == 200 and 'id="en-partie-body"' in page.text
    assert "<html" not in stage(client)


def test_etat_vide_hors_partie(client):
    assert "Pas de partie en cours" in stage(client)


def test_en_partie_horloge_win_chance_et_variation(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    html = stage(client)
    assert "12:34" in html and "61 %" in html and "+3 pts / min" in html
    assert "Partie en cours" in html and "Partie terminée" not in html


def test_partie_terminee(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "state": "ended"})
    assert "Partie terminée" in stage(client)


def test_sans_modele_l_ecran_dit_comment_l_entrainer(client, bus):  # noqa: F811
    bus.publish(
        "ingame", {"state": "live", "game_time": 60.0, "p": None, "delta": None, "series": []}
    )
    html = stage(client)
    assert "python -m src.winprob.retrain --force" in html and 'class="ig-chance"' not in html


def test_face_a_face_de_la_draft(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    bus.publish("game", analysis())
    html = stage(client)
    names = re.findall(r'class="ig-side ig-(?:ally|foe)-ink">([^<]+)<', html)
    assert names == [
        "Garen",
        "Darius",
        "Vi",
        "Lee Sin",
        "Ahri",
        "Syndra",
        "Jinx",
        "Draven",
        "Rell",
        "Nautilus",
    ]
    assert "Avantage de draft majeur" in html and "55.0 %" in html
    assert "‹‹‹ +3.4" in html  # Garen / Darius : trois chevrons vers l'allié
    assert "›› -2.5" in html  # Jinx / Draven : deux chevrons vers l'ennemi
    assert "ig-duel-none" in html and "peu de données" not in html


def test_analyse_indisponible_sans_la_draft(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    html = stage(client)
    assert "Analyse indisponible" in html and "n'a pas vu la draft" in html


def test_champion_aux_donnees_minces(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    bus.publish("game", analysis(thin={"Garen"}))
    assert "peu de données" in stage(client)


def test_reset_de_la_draft_retire_l_analyse(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    bus.publish("game", analysis())
    bus.publish("game", None)
    assert "Analyse indisponible" in stage(client)


def test_aucune_route_d_ecriture_sous_en_partie(client):
    routes = [r for r in client.app.routes if getattr(r, "path", "").startswith("/en-partie")]
    assert {r.path for r in routes} == {"/en-partie", "/en-partie/stage"}
    assert all(r.methods == {"GET"} for r in routes)


def test_navigation_entree_active_et_pastille(client, bus):  # noqa: F811
    html = client.get("/en-partie").text
    assert re.search(r'<a class="nav-item" href="/en-partie"[^>]*aria-current="page"', html)
    assert 'id="tb-ingame"' in html and re.search(r'id="tb-ingame"[^>]*\bhidden\b', html)
    bus.publish("ingame", LIVE)
    live = client.get("/").text
    assert 'id="tb-ingame"' in live and not re.search(r'id="tb-ingame"[^>]*\bhidden\b', live)


def test_script_servi_et_charge(client):
    assert client.get("/static/en_partie.js").status_code == 200
    assert "en_partie.js" in client.get("/").text


def test_aucune_bascule_automatique_de_page():
    source = open("src/client/static/en_partie.js", encoding="utf-8").read()
    assert "pushState" not in source and "htmx.ajax" not in source and "location" not in source


def test_horloge():
    assert en_partie.clock(754.9) == "12:34" and en_partie.clock(None) == "0:00"
