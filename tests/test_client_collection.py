"""Écran Collection du client (SPEC-21 tâche 79) : champions, pages de runes, sets d'objets, lecture seule."""

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.collection import champions_view, items_view, runes_view
from src.client.draft_view import Champions
from src.client.lcu_proxy import ForbiddenEndpoint, LcuProxy
from tests.support_lcu_nav import FauxLcuNav, fixture, make_assets

LOCAL = "http://127.0.0.1"


@pytest.fixture
def champions(tmp_path):
    return Champions(make_assets(tmp_path))


def client(temp_db, tmp_path, lcu):
    app = create_app(temp_db, lcu=lcu, assets=make_assets(tmp_path))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


# ---------- vues ----------


def test_champions_par_ordre_alphabetique_avec_leur_portrait(champions):
    view = champions_view(fixture("owned_champions"), None, champions)
    names = [c["name"] for c in view["champions"]]
    assert names == sorted(names, key=str.casefold)
    sion = next(c for c in view["champions"] if c["name"] == "Sion")
    assert sion["portrait"] == "/assets/champion/Sion.png"
    assert view["summary"] == "8 champions sur 8 possédés"


def test_filtre_par_classe(champions):
    view = champions_view(fixture("owned_champions"), "mage", champions)
    assert view["role"] == "mage" and view["champions"]
    assert all("Mage" in c["roles"] for c in view["champions"])
    assert [r["key"] for r in view["roles"] if r["active"]] == ["mage"]


def test_classe_inconnue_ignoree(champions):
    assert champions_view(fixture("owned_champions"), "<script>", champions)["role"] is None


def test_pages_de_runes_la_page_active_d_abord():
    pages = fixture("../lcu_forms/pages")
    pages[-1]["isActive"] = True
    view = runes_view(pages)
    assert view["pages"][0]["active"] and view["pages"][0]["name"] == pages[-1]["name"]
    assert view["pages"][0]["icon"].startswith("/assets/perk/perk-images/Styles/")
    assert view["summary"] == f"{len(pages)} pages de runes"


def test_une_icone_de_rune_hors_forme_n_est_pas_servie():
    pages = fixture("../lcu_forms/pages")[:1]
    pages[0]["pageKeystone"]["iconPath"] = "http://exemple.invalide/x.png"
    assert runes_view(pages)["pages"][0]["icon"] is None


def test_sets_d_objets(champions):
    view = items_view(fixture("item_sets"), champions)
    first = view["sets"][0]
    assert first["title"] and first["champions"][0]["name"] == "Sion"
    assert all(isinstance(i, int) for b in first["blocks"] for i in b["items"])
    assert first["count"] == sum(len(b["items"]) for b in first["blocks"])


# ---------- routes ----------


def test_les_trois_vues_repondent_et_ne_font_que_lire(temp_db, tmp_path):
    lcu = FauxLcuNav()
    web = client(temp_db, tmp_path, lcu)
    for view, text in (("champions", "Sion"), ("runes", "Active"), ("objets", "Starters")):
        response = web.get(f"/collection?vue={view}")
        assert response.status_code == 200, view
        assert text in response.text or view == "runes"
    assert lcu.writes == []


def test_vue_par_defaut_et_filtre(temp_db, tmp_path):
    web = client(temp_db, tmp_path, FauxLcuNav())
    assert "champions sur" in web.get("/collection").text
    filtered = web.get("/collection?vue=champions&role=mage").text
    assert "Annie" in filtered and "Sion" not in filtered


def test_nom_de_champion_echappe(temp_db, tmp_path):
    lcu = FauxLcuNav()
    owned = fixture("owned_champions")
    owned[0]["name"] = "<script>alert(1)</script>"
    lcu.overrides["/lol-champions/v1/owned-champions-minimal"] = owned
    text = client(temp_db, tmp_path, lcu).get("/collection").text
    assert "<script>alert(1)</script>" not in text and "&lt;script&gt;" in text


def test_une_lecture_a_la_fois(temp_db, tmp_path):
    lcu = FauxLcuNav()
    client(temp_db, tmp_path, lcu).get("/collection?vue=runes")
    endpoints = [call[1] for call in lcu.calls]
    assert "/lol-perks/v1/pages" in endpoints
    assert "/lol-champions/v1/owned-champions-minimal" not in endpoints


def test_client_ferme_ou_sans_reponse(temp_db, tmp_path):
    assert "Client LoL fermé" in client(temp_db, tmp_path, None).get("/collection").text
    lcu = FauxLcuNav({"/lol-champions/v1/owned-champions-minimal": None})
    response = client(temp_db, tmp_path, lcu).get("/collection")
    assert response.status_code == 200 and "ne répond pas" in response.text


# ---------- liste blanche ----------


def test_liste_blanche_collection():
    proxy = LcuProxy(FauxLcuNav())
    assert proxy.get("/lol-champions/v1/owned-champions-minimal")
    assert proxy.get("/lol-item-sets/v1/item-sets/2001/sets")
    with pytest.raises(ForbiddenEndpoint):
        proxy.send("PUT", "/lol-item-sets/v1/item-sets/2001/sets", {})
    with pytest.raises(ForbiddenEndpoint):
        proxy.get("/lol-item-sets/v1/item-sets/abc/sets")
