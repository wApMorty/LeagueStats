"""SPEC-49 tâche 243 : écran Suggestions de pool du client (routes, vue, accepter, passer)."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src import pool_manager, user_prefs
from src.analysis.pool_swipe import SwapCard
from src.client import pool_swipe as client_pool_swipe
from src.client.app import create_app
from src.client.bus import EventBus
from src.client.donnees import UpdateJob
from src.config_constants import pool_stats_config
from src.pipeline import PipelineResult
from src.config_client import client_config
from src.pool_manager import PoolManager
from tests.support_lcu_nav import make_assets

LOCAL = "http://127.0.0.1"


@pytest.fixture
def seeded_db(temp_db, insert_duel):
    """Lane top : Ahri perd contre Garen, Darius le bat ; Zed est neutre. Scrape du 2 novembre."""
    insert_duel("Ahri", "Garen", 40.0, -2.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Ahri", "Zed", 50.0, 0.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Ahri", "Darius", 50.0, 0.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Darius", "Garen", 60.0, 2.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Darius", "Zed", 55.0, 1.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Garen", "Zed", 50.0, 0.0, 0.0, 10.0, 1000, lane="top")
    with sqlite3.connect(temp_db) as db:
        db.execute(
            "INSERT INTO db_meta (key, value) VALUES ('last_scrape_utc', '2026-11-02T10:00:00+00:00')"
        )
    return temp_db


@pytest.fixture
def web(seeded_db, tmp_path, monkeypatch):
    """Client de test : pools et préférences sous tmp_path, base de test (jamais data/db.db)."""
    monkeypatch.setattr(pool_manager, "get_user_data_path", lambda f: str(tmp_path / f))
    monkeypatch.setattr(user_prefs, "get_user_data_path", lambda f: str(tmp_path / f))
    app = create_app(seeded_db, assets=make_assets(tmp_path))
    client = TestClient(app, base_url=LOCAL, raise_server_exceptions=False)
    client.pools_file = tmp_path / "champion_pools.json"
    client.prefs_file = tmp_path / "user_prefs.json"
    client.db = seeded_db
    return client


def post(web, path, data=None, token=True):
    headers = {client_config.TOKEN_HEADER: web.app.state.session_token} if token else {}
    return web.post(path, headers=headers, data=data)


def saved(web):
    return {p["name"]: p for p in json.loads(web.pools_file.read_text("utf-8"))["custom_pools"]}


def designer_main_top(web):
    """Pool perso « Main » = [Ahri], désigné pour le poste top (pas de pool par défaut)."""
    post(web, "/pool/creer", data={"arg": "Main"})
    post(web, "/pool/ajouter?name=Main&arg=Ahri")
    post(web, "/pool/role?name=Main&arg=top")


def test_la_page_affiche_la_carte_et_les_boutons_sans_js(web):
    designer_main_top(web)
    page = web.get("/pool/suggestions?poste=top")
    assert page.status_code == 200
    assert 'data-incoming="Darius"' in page.text and 'data-outgoing="Ahri"' in page.text
    assert 'data-swipe="take"' in page.text and 'data-swipe="pass"' in page.text
    assert "/pool/suggestions/accepter?poste=top&amp;entrant=Darius&amp;sortant=Ahri" in page.text
    assert "données du 2 nov." in page.text


def test_accepter_remplace_le_sortant_et_efface_les_bans(web):
    designer_main_top(web)
    with sqlite3.connect(web.db) as db:
        db.execute(
            "INSERT INTO pool_ban_recommendations (pool_name, enemy_champion, threat_score,"
            " best_response_delta2, best_response_champion, matchups_count)"
            " VALUES ('Main', 'Zed', 1, 1, 'Ahri', 1)"
        )
    reply = post(web, "/pool/suggestions/accepter?poste=top&entrant=Darius&sortant=Ahri")
    assert reply.status_code == 200 and "Darius remplace Ahri dans « Main »" in reply.text
    assert saved(web)["Main"]["champions"] == ["Darius"]
    with sqlite3.connect(web.db) as db:
        assert db.execute("SELECT COUNT(*) FROM pool_ban_recommendations").fetchone()[0] == 0


def test_accepter_depose_la_commande_pool_si_c_est_le_pool_par_defaut(
    seeded_db, tmp_path, monkeypatch
):
    monkeypatch.setattr(pool_manager, "get_user_data_path", lambda f: str(tmp_path / f))
    monkeypatch.setattr(user_prefs, "get_user_data_path", lambda f: str(tmp_path / f))
    lines = []
    app = create_app(
        seeded_db,
        assets=make_assets(tmp_path),
        commands=lambda line: lines.append(line) or True,
    )
    web = TestClient(app, base_url=LOCAL, raise_server_exceptions=False)
    web.pools_file = tmp_path / "champion_pools.json"
    designer_main_top(web)
    post(web, "/pool/actif?name=Main")
    lines.clear()
    post(web, "/pool/suggestions/accepter?poste=top&entrant=Darius&sortant=Ahri")
    assert lines == ["pool Main"]


def test_carte_perimee_refusee_sans_ecriture(web):
    designer_main_top(web)
    before = web.pools_file.read_text("utf-8")
    reply = post(web, "/pool/suggestions/accepter?poste=top&entrant=Darius&sortant=Zed")
    assert reply.status_code == 200 and "Suggestion périmée" in reply.text
    assert web.pools_file.read_text("utf-8") == before


def test_pool_systeme_sans_carte_et_accepter_refuse(web):
    page = web.get("/pool/suggestions?poste=top")
    assert page.status_code == 200
    assert "Pool système : duplique-le sur l&#39;écran Pool" in page.text
    assert 'data-swipe="take"' not in page.text
    reply = post(web, "/pool/suggestions/accepter?poste=top&entrant=Darius&sortant=Ahri")
    assert "Pool système : duplique-le" in reply.text
    assert not web.pools_file.exists()


def test_passer_memorise_la_passe_par_version_et_la_carte_revient_au_nouveau_scrape(web):
    designer_main_top(web)
    reply = post(web, "/pool/suggestions/passer?poste=top&entrant=Darius")
    assert reply.status_code == 200 and "Darius passé" in reply.text
    assert 'data-incoming="Darius"' not in reply.text
    prefs = json.loads(web.prefs_file.read_text("utf-8"))
    assert prefs["pool_swipe"] == {
        "version": "2026-11-02T10:00:00+00:00",
        "passed": {"top": ["Darius"]},
    }
    assert 'data-incoming="Darius"' not in web.get("/pool/suggestions?poste=top").text

    with sqlite3.connect(web.db) as db:
        db.execute(
            "UPDATE db_meta SET value = '2026-11-03T10:00:00+00:00' WHERE key = 'last_scrape_utc'"
        )
    assert 'data-incoming="Darius"' in web.get("/pool/suggestions?poste=top").text


def test_routes_suggestions_declarees_avant_pool_action(web):
    paths = [getattr(route, "path", None) for route in web.app.routes]
    action = paths.index("/pool/{action}")
    for path in ("/pool/suggestions", "/pool/suggestions/accepter", "/pool/suggestions/passer"):
        assert paths.index(path) < action
    reply = post(web, "/pool/suggestions/passer?poste=top&entrant=Garen")
    assert "Action inconnue" not in reply.text and 'id="swipe-body"' in reply.text


def test_ecritures_sans_jeton_refusees(web):
    designer_main_top(web)
    for path in (
        "/pool/suggestions/accepter?poste=top&entrant=Darius&sortant=Ahri",
        "/pool/suggestions/passer?poste=top&entrant=Darius",
    ):
        assert post(web, path, token=False).status_code == 403
    assert saved(web)["Main"]["champions"] == ["Ahri"]
    assert not web.prefs_file.exists() or "pool_swipe" not in web.prefs_file.read_text("utf-8")


def test_page_charge_le_script_et_pose_le_seuil_de_glisser(web):
    designer_main_top(web)
    page = web.get("/pool/suggestions?poste=top").text
    assert '<script src="/static/pool_swipe.js" defer></script>' in page
    assert f'data-drag="{pool_stats_config.POOL_SWIPE_DRAG_PX}"' in page


def test_ecran_pool_lien_suggestions_pour_pool_perso_designe_seulement(web):
    designer_main_top(web)
    assert 'href="/pool/suggestions?poste=top"' in web.get("/pool?nom=Main").text
    assert "/pool/suggestions" not in web.get("/pool?nom=All%20Top%20Champions").text


def test_lien_suggestions_de_donnees_apres_un_run_ok(seeded_db, tmp_path):
    bus = EventBus()
    bus.publish("phase", {"kind": "closed"})
    job = UpdateJob(run=lambda progress, stop: PipelineResult(status="ok"), clock=lambda: 0.0)
    app = create_app(seeded_db, bus=bus, assets=make_assets(tmp_path), update_job=job)
    web = TestClient(app, base_url=LOCAL, raise_server_exceptions=False)
    assert 'href="/pool/suggestions"' not in web.get("/donnees").text
    token = {client_config.TOKEN_HEADER: web.app.state.session_token}
    assert web.post("/donnees/actualiser", headers=token).status_code == 200
    assert job.cancel(5.0)
    assert 'href="/pool/suggestions"' in web.get("/donnees").text


def test_accepter_garde_la_taille_et_la_place_du_sortant(web, monkeypatch):
    """L'entrant prend la place du sortant au milieu du pool (pile figée pour choisir le sortant)."""
    post(web, "/pool/creer", data={"arg": "Main"})
    for champion in ("Zed", "Garen", "Ahri"):
        post(web, f"/pool/ajouter?name=Main&arg={champion}")
    post(web, "/pool/role?name=Main&arg=top")
    card = SwapCard("top", "Darius", "Garen", 1.0, 0.5, 0.5, False, (), ())
    monkeypatch.setattr(client_pool_swipe, "_stack", lambda *args: ([card], None))
    post(web, "/pool/suggestions/accepter?poste=top&entrant=Darius&sortant=Garen")
    assert saved(web)["Main"]["champions"] == ["Zed", "Darius", "Ahri"]
