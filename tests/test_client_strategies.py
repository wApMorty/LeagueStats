"""Écran Stratégies du client : choisir la stratégie active, dupliquer, régler et supprimer les perso."""

import json

import pytest
from fastapi.testclient import TestClient

from src import user_prefs
from src.client.app import create_app
from src.client.strategies import SYSTEM_HINT
from src.config_client import client_config
from src.config_constants import draft_config
from tests.support_lcu_nav import make_assets

LOCAL = "http://127.0.0.1"
VALID = {"force": "1", "duel": "1", "other": "1", "synergy": "0", "mastery": "1", "search": "1"}


@pytest.fixture
def web(temp_db, tmp_path, monkeypatch):
    """Client de test dont les préférences vivent dans tmp_path ; `commands` est enregistré."""
    monkeypatch.setattr(user_prefs, "get_user_data_path", lambda f: str(tmp_path / f))
    lines = []
    app = create_app(
        temp_db,
        assets=make_assets(tmp_path),
        commands=lambda line: lines.append(line) or True,
    )
    client = TestClient(app, base_url=LOCAL, raise_server_exceptions=False)
    client.prefs_file = tmp_path / "user_prefs.json"
    client.lines = lines
    return client


def post(web, path, data=None, token=True):
    headers = {client_config.TOKEN_HEADER: web.app.state.session_token} if token else {}
    return web.post(path, headers=headers, data=data)


def prefs(web):
    return json.loads(web.prefs_file.read_text("utf-8"))


def custom(web):
    return {p["name"]: p for p in prefs(web).get("strategies", [])}


def snapshot(web):
    return web.prefs_file.read_text("utf-8") if web.prefs_file.exists() else None


def test_la_page_liste_les_strategies_systeme_et_sert_la_nav(web):
    page = web.get("/strategies")
    assert page.status_code == 200
    for name in ("Simple", "Counter", "Complet", "Arbre"):
        assert name in page.text
    assert 'href="/strategies"' in page.text


def test_le_mode_a_recherche_s_appelle_anticipation(web):
    system = web.get("/strategies", params={"nom": "Complet"}).text
    assert "Anticipation" in system and "Anticipe le vis-à-vis." in system
    assert "Recherche" not in system

    post(web, "/strategies/dupliquer?name=Complet", data={"nom": "Mon complet"})
    page = web.get("/strategies", params={"nom": "Mon complet"}).text
    assert "Anticiper le vis-à-vis" in page and "Recherche minimax" not in page


def test_dupliquer_un_systeme_garde_poids_et_recherche_sans_system(web):
    reply = post(web, "/strategies/dupliquer?name=Complet", data={"nom": "Mon complet"})
    assert "« Complet » dupliqué en « Mon complet »" in reply.text
    copy = custom(web)["Mon complet"]
    assert copy == {
        "name": "Mon complet",
        "force": 1.0,
        "duel": 1.0,
        "other": 1.0,
        "synergy": 1.0,
        "mastery": 1.0,
        "search": True,
    }


def test_modifier_enregistre_les_poids_et_la_recherche(web):
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Perso"})
    data = {"force": "2", "duel": "0.5", "other": "1", "synergy": "0", "mastery": "1.5"}
    reply = post(web, "/strategies/modifier?name=Perso", data=data)
    assert "Stratégie « Perso » enregistrée" in reply.text
    saved = custom(web)["Perso"]
    assert (saved["force"], saved["duel"], saved["mastery"]) == (2.0, 0.5, 1.5)
    assert saved["search"] is False  # case non cochée


def test_un_refus_s_affiche_sans_ecriture(web):
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Perso"})
    before = snapshot(web)
    refusals = [
        ("/strategies/dupliquer?name=Simple", {"nom": "   "}, "le nom de la stratégie est vide"),
        ("/strategies/dupliquer?name=Simple", {"nom": "x" * 15}, "plus de 14 caractères"),
        ("/strategies/dupliquer?name=Simple", {"nom": "perso"}, "Nom déjà pris"),
        ("/strategies/dupliquer?name=Simple", {"nom": "counter"}, "stratégie de base"),
        ("/strategies/modifier?name=Perso", {**VALID, "force": "nan"}, "fini"),
        ("/strategies/modifier?name=Perso", {**VALID, "force": "inf"}, "fini"),
        ("/strategies/modifier?name=Perso", {**VALID, "force": "4"}, "entre 0 et 3"),
        ("/strategies/modifier?name=Perso", {**VALID, "duel": "-1"}, "entre 0 et 3"),
        ("/strategies/modifier?name=Perso", {**VALID, "duel": "abc"}, "doit être un nombre"),
        (
            "/strategies/modifier?name=Perso",
            {"force": "0", "duel": "0", "other": "0", "synergy": "0", "mastery": "0"},
            "au moins un poids",
        ),
        ("/strategies/modifier?name=Complet", VALID, SYSTEM_HINT),
        ("/strategies/supprimer?name=Complet", {}, SYSTEM_HINT),
        ("/strategies/inventer?name=Perso", {}, "Action inconnue"),
    ]
    for path, data, message in refusals:
        reply = post(web, path, data=data)
        assert reply.status_code == 200, path
        assert message in reply.text, (path, data)
    assert snapshot(web) == before


def test_nombre_maximal_de_strategies_refuse_la_copie(web):
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Un"})
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Deux"})
    before = snapshot(web)
    reply = post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Trois"})
    assert f"{draft_config.STRATEGY_MAX_COUNT} stratégies au plus" in reply.text
    assert snapshot(web) == before


def test_supprimer_la_strategie_active_rebascule_sur_le_defaut(web):
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Perso"})
    post(web, "/strategies/actif?name=Perso")
    reply = post(web, "/strategies/supprimer?name=Perso")
    assert "Stratégie « Perso » supprimée" in reply.text
    defaut = draft_config.STRATEGY_DEFAULT
    assert prefs(web)["active_strategy"] == defaut and prefs(web)["strategies"] == []
    assert web.lines == ["strategy Perso", f"strategy {defaut}"]


def test_commands_seulement_pour_les_seuls_cas_prevus(web):
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Perso"})
    post(web, "/strategies/dupliquer?name=Counter", data={"nom": "Copie"})
    assert web.lines == []
    post(web, "/strategies/modifier?name=Copie", data=VALID)  # inactive : rien
    assert web.lines == []
    post(web, "/strategies/actif?name=Perso")
    assert web.lines == ["strategy Perso"]
    post(web, "/strategies/modifier?name=Perso", data=VALID)  # active : recharge
    assert web.lines == ["strategy Perso", "strategy Perso"]
    post(web, "/strategies/actif?name=Inconnue")  # refus : rien
    assert web.lines == ["strategy Perso", "strategy Perso"]


def test_motion_et_designations_de_poste_sont_conservees(web):
    post(web, "/prefs/motion?mode=reduit")
    user_prefs.save_role_pool("middle", "Meta Picks")
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Perso"})
    post(web, "/strategies/actif?name=Perso")
    post(web, "/strategies/supprimer?name=Perso")
    data = prefs(web)
    assert data["motion"] == "reduit"
    assert data["pools_by_role"] == {"middle": "Meta Picks"}


def test_une_ecriture_sans_jeton_est_refusee(web):
    reply = post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Perso"}, token=False)
    assert reply.status_code == 403
    assert not web.prefs_file.exists()


def test_la_bascule_de_draft_garde_son_chemin(web):
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Perso"})
    reply = post(web, "/strategies/active?name=Perso")
    assert reply.status_code == 204
    assert prefs(web)["active_strategy"] == "Perso"


def test_bornes_du_gabarit_lues_de_draft_config(web, monkeypatch):
    monkeypatch.setattr(draft_config, "STRATEGY_WEIGHT_MAX", 5.0)
    monkeypatch.setattr(draft_config, "STRATEGY_WEIGHT_STEP", 0.5)
    monkeypatch.setattr(draft_config, "STRATEGY_NAME_MAX", 9)
    monkeypatch.setattr(draft_config, "STRATEGY_MAX_COUNT", 8)
    post(web, "/strategies/dupliquer?name=Simple", data={"nom": "Perso"})
    page = web.get("/strategies?nom=Perso").text
    assert 'max="5.0"' in page and 'step="0.5"' in page
    assert 'maxlength="9"' in page and "/ 8 stratégies" in page


def test_arbre_se_lit_sans_poids_ni_duplicata(web):
    page = web.get("/strategies", params={"nom": "Arbre"}).text
    assert "Arbre · " in page
    assert "plus le pire counter attendu des lanes ennemies pas encore choisies" in page
    assert 'hx-post="/strategies/dupliquer?name=Arbre"' not in page
    assert 'type="range"' not in page


def test_arbre_refuse_la_copie_sans_ecriture(web):
    before = snapshot(web)
    reply = post(web, "/strategies/dupliquer?name=Arbre", data={"nom": "Copie"})
    assert reply.status_code == 200
    assert "La stratégie Arbre ne se duplique pas" in reply.text
    assert snapshot(web) == before
