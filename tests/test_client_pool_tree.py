"""SPEC-54 tâche 271 : arbre du pool côté client (`src/client/pool_tree.py`), route `/pool/arbre`,
lane d'un pool et fragment chargé par l'écran Pool. Bases sous tmp_path, `tree_view` patché sur la route.
"""

import pytest
from fastapi.testclient import TestClient

from src import pool_manager, user_prefs
from src.analysis.pool_tree import PoolTree, TreeChoice
from src.client import app as client_app
from src.client import pool_tree as client_pool_tree
from src.client.app import create_app
from src.client.draft_view import Champions
from src.config_client import client_config
from src.config_constants import pool_stats_config
from src.db import Database
from src.pool_manager import PoolManager
from src.user_prefs import save_role_pool
from tests.support_lcu_nav import make_assets

LOCAL = "http://127.0.0.1"


@pytest.fixture(autouse=True)
def cache_vide():
    """Le cache de l'arbre est un lru_cache de module : vidé avant et après chaque test."""
    client_pool_tree._tree.cache_clear()
    yield
    client_pool_tree._tree.cache_clear()


@pytest.fixture
def seeded_db(temp_db, insert_duel):
    """Lane top : Ahri perd contre Garen, Darius le bat ; Zed est neutre."""
    insert_duel("Ahri", "Garen", 40.0, -2.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Ahri", "Zed", 50.0, 0.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Ahri", "Darius", 50.0, 0.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Darius", "Garen", 60.0, 2.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Darius", "Zed", 55.0, 1.0, 0.0, 10.0, 1000, lane="top")
    insert_duel("Garen", "Zed", 50.0, 0.0, 0.0, 10.0, 1000, lane="top")
    return temp_db


@pytest.fixture
def prefs_tmp(tmp_path, monkeypatch):
    """Pools et préférences sous tmp_path (jamais le dépôt)."""
    monkeypatch.setattr(pool_manager, "get_user_data_path", lambda f: str(tmp_path / f))
    monkeypatch.setattr(user_prefs, "get_user_data_path", lambda f: str(tmp_path / f))
    return tmp_path


@pytest.fixture
def web(seeded_db, prefs_tmp):
    app = create_app(seeded_db, assets=make_assets(prefs_tmp))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def post(web, path, data=None):
    headers = {client_config.TOKEN_HEADER: web.app.state.session_token}
    return web.post(path, headers=headers, data=data)


def portraits(tmp_path):
    return Champions(make_assets(tmp_path))


def arbre_factice() -> PoolTree:
    """Blind Ahri > Garen ; Zed (5 %) et Solo (4 %) joués, Rare (0,5 %) sous le seuil."""
    blind = (TreeChoice("Ahri", 1.0), TreeChoice("Garen", 0.5))
    counters = (
        ("Zed", 0.05, (TreeChoice("Garen", 2.0), TreeChoice("Ahri", -1.0))),
        ("Solo", 0.04, (TreeChoice("Ahri", 3.0),)),
        (
            "Rare",
            pool_stats_config.POOL_SWIPE_MIN_POPULARITY / 2,
            (TreeChoice("Ahri", 3.0), TreeChoice("Garen", 1.0)),
        ),
    )
    return PoolTree(lane="top", blind=blind, counters=counters)


def test_tree_payload_seuil_repli_et_pool_d_un_champion(tmp_path):
    payload = client_pool_tree.tree_payload(arbre_factice(), portraits(tmp_path))
    assert [b["name"] for b in payload["blind"]] == ["Ahri", "Garen"]
    assert [row["enemy"]["name"] for row in payload["rows"]] == ["Zed", "Solo"]
    zed = payload["rows"][0]
    assert zed["popularity"] == "5,0 %"
    assert zed["choice"]["name"] == "Garen" and zed["fallback"]["name"] == "Ahri"
    solo = payload["rows"][1]
    assert solo["fallback"] is None and solo["fallback_value"] is None


def test_tree_view_sans_poste_ou_sans_champion_est_none(seeded_db, tmp_path):
    assert client_pool_tree.tree_view(seeded_db, None, ["Ahri"], portraits(tmp_path)) is None
    assert client_pool_tree.tree_view(seeded_db, "top", [], portraits(tmp_path)) is None


def test_tree_view_base_illisible_est_none(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_text("pas une base", encoding="utf-8")
    assert client_pool_tree.tree_view(bad, "top", ["Ahri"], portraits(tmp_path)) is None


def test_tree_view_calcule_une_fois_par_version(seeded_db, tmp_path, monkeypatch):
    opened = []

    class Compte(Database):
        def connect_read_only(self):
            opened.append(self.path)
            super().connect_read_only()

    monkeypatch.setattr(client_pool_tree, "Database", Compte)
    first = client_pool_tree.tree_view(seeded_db, "top", ["Ahri", "Garen"], portraits(tmp_path))
    second = client_pool_tree.tree_view(seeded_db, "top", ["Ahri", "Garen"], portraits(tmp_path))
    assert first is not None and first == second
    assert len(opened) == 1


def test_pool_lane_role_puis_designation_puis_dominant(seeded_db, prefs_tmp):
    manager = PoolManager()
    manager.create_pool("Adc", ["Ahri"], "", role="adc")
    manager.create_pool("Libre", ["Ahri"], "", role="custom")
    adc, libre = manager.get_pool("Adc"), manager.get_pool("Libre")
    assert client_pool_tree.pool_lane(adc, seeded_db) == "bottom"
    assert client_pool_tree.pool_lane(libre, seeded_db) == "top"
    save_role_pool("jungle", "Libre")
    assert client_pool_tree.pool_lane(libre, seeded_db) == "jungle"


def test_route_arbre_200_avec_la_lane_du_pool_et_404_si_inconnu(web, monkeypatch):
    post(web, "/pool/creer", data={"arg": "Main"})
    post(web, "/pool/ajouter?name=Main&arg=Ahri")
    appels = []

    def faux(db_path, lane, champions, portraits_):
        appels.append((lane, tuple(champions)))
        return client_pool_tree.tree_payload(arbre_factice(), portraits_)

    monkeypatch.setattr(client_app, "tree_view", faux)
    reply = web.get("/pool/arbre?nom=Main")
    assert reply.status_code == 200 and "Arbre de décision" in reply.text
    assert appels == [("top", ("Ahri",))]
    assert web.get("/pool/arbre?nom=Inconnu").status_code == 404


def test_route_explique_l_absence_de_poste_ou_de_base(web, monkeypatch):
    post(web, "/pool/creer", data={"arg": "Main"})
    post(web, "/pool/ajouter?name=Main&arg=Ahri")
    monkeypatch.setattr(client_app, "tree_view", lambda *args: None)
    monkeypatch.setattr(client_app, "pool_lane", lambda *args: None)
    assert "Aucun poste pour ce pool" in web.get("/pool/arbre?nom=Main").text
    monkeypatch.setattr(client_app, "pool_lane", lambda *args: "top")
    assert "Base de données indisponible" in web.get("/pool/arbre?nom=Main").text


def test_ecran_pool_charge_l_arbre_apres_l_affichage(web):
    post(web, "/pool/creer", data={"arg": "Main"})
    page = web.get("/pool?nom=Main").text
    assert 'hx-get="/pool/arbre?nom=Main"' in page
    assert 'hx-trigger="load"' in page and 'hx-select="unset"' in page
