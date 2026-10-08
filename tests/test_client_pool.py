"""Écran Pool du client : choisir le pool actif, créer et éditer les pools perso."""

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src import pool_manager, user_prefs
from src.client.app import create_app
from src.config_client import client_config
from tests.support_lcu_nav import make_assets

LOCAL = "http://127.0.0.1"


@pytest.fixture
def web(temp_db, tmp_path, monkeypatch):
    """Client de test dont pools et préférences vivent dans tmp_path (jamais le dépôt)."""
    monkeypatch.setattr(pool_manager, "get_user_data_path", lambda f: str(tmp_path / f))
    monkeypatch.setattr(user_prefs, "get_user_data_path", lambda f: str(tmp_path / f))
    with sqlite3.connect(temp_db) as db:
        db.executemany("INSERT INTO champions (name) VALUES (?)", [("Ahri",), ("Garen",), ("Zed",)])
    app = create_app(temp_db, assets=make_assets(tmp_path))
    client = TestClient(app, base_url=LOCAL, raise_server_exceptions=False)
    client.pools_file = tmp_path / "champion_pools.json"
    client.prefs_file = tmp_path / "user_prefs.json"
    client.db = temp_db
    return client


def post(web, path, data=None, token=True):
    headers = {client_config.TOKEN_HEADER: web.app.state.session_token} if token else {}
    return web.post(path, headers=headers, data=data)


def saved(web):
    return {p["name"]: p for p in json.loads(web.pools_file.read_text("utf-8"))["custom_pools"]}


def test_la_page_liste_les_pools_systeme_et_sert_la_nav(web):
    page = web.get("/pool")
    assert page.status_code == 200
    assert "All Top Champions" in page.text and 'href="/pool"' in page.text


def test_creer_puis_ajouter_et_retirer_un_champion_sont_enregistres(web):
    assert "Pool « Main » créé" in post(web, "/pool/creer", data={"arg": "Main"}).text
    assert "Ahri ajouté" in post(web, "/pool/ajouter?name=Main&arg=ahri").text
    post(web, "/pool/ajouter?name=Main&arg=Zed")
    assert saved(web)["Main"]["champions"] == ["Ahri", "Zed"]
    post(web, "/pool/retirer?name=Main&arg=Ahri")
    assert saved(web)["Main"]["champions"] == ["Zed"]


def test_champion_inconnu_refuse_sans_ecriture(web):
    post(web, "/pool/creer", data={"arg": "Main"})
    reply = post(web, "/pool/ajouter?name=Main&arg=Inconnu")
    assert reply.status_code == 200 and "Champion inconnu" in reply.text
    assert saved(web)["Main"]["champions"] == []


def test_un_pool_systeme_ne_se_modifie_pas_mais_se_duplique(web):
    reply = post(web, "/pool/ajouter?name=All Top Champions&arg=Zed")
    assert "duplique-le" in reply.text and not web.pools_file.exists()
    post(web, "/pool/dupliquer?name=All Top Champions", data={"arg": "Ma copie"})
    assert "Ma copie" in saved(web)


def test_supprimer_retire_le_pool(web):
    post(web, "/pool/creer", data={"arg": "Main"})
    post(web, "/pool/supprimer?name=Main")
    assert "Main" not in saved(web)


def test_choisir_le_pool_actif_ecrit_les_preferences_et_garde_motion(web):
    post(web, "/prefs/motion?mode=reduit")
    reply = post(web, "/pool/actif?name=Meta Picks")
    assert "prochain lancement" in reply.text
    prefs = json.loads(web.prefs_file.read_text("utf-8"))
    assert prefs["pool_name"] == "Meta Picks" and prefs["motion"] == "reduit"
    assert user_prefs.load_user_prefs().pool_name == "Meta Picks"
    assert "Pool actif : <b>Meta Picks</b>" in web.get("/pool").text


def test_editer_un_pool_efface_ses_bans_precalcules(web):
    post(web, "/pool/creer", data={"arg": "Main"})
    with sqlite3.connect(web.db) as db:
        db.execute(
            "INSERT INTO pool_ban_recommendations (pool_name, enemy_champion, threat_score,"
            " best_response_delta2, best_response_champion, matchups_count)"
            " VALUES ('Main', 'Zed', 1, 1, 'Ahri', 1)"
        )
    post(web, "/pool/ajouter?name=Main&arg=Ahri")
    with sqlite3.connect(web.db) as db:
        assert db.execute("SELECT COUNT(*) FROM pool_ban_recommendations").fetchone()[0] == 0


def test_une_ecriture_sans_jeton_est_refusee(web):
    assert post(web, "/pool/creer", data={"arg": "Main"}, token=False).status_code == 403
    assert not web.pools_file.exists()
