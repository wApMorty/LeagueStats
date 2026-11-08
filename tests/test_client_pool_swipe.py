"""SPEC-49, SPEC-50, SPEC-51 tâche 255 : panneau latéral de la Méta du poste (routes `/meta/*`,
vue, accepter, passer, générer, créer, exclure) et redirection de l'ancien écran Suggestions."""

import json
import sqlite3
from datetime import date

import pytest
from fastapi.testclient import TestClient

from src import pool_manager, user_prefs
from src.analysis.pool_swipe import SwapCard
from src.client import pool_swipe as client_pool_swipe
from src.client.app import create_app
from src.client.bus import EventBus
from src.client.donnees import UpdateJob
from src.client.draft_view import Champions
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


@pytest.fixture(autouse=True)
def cache_generateur_vide():
    """Le cache du générateur est un dict de module : vidé avant et après chaque test."""
    client_pool_swipe._GENERATED.clear()
    yield
    client_pool_swipe._GENERATED.clear()


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


def vue(web, size=None, mode=None):
    """Vue du panneau pour le top (portraits factices, sous tmp_path)."""
    champions = Champions(make_assets(web.pools_file.parent))
    return client_pool_swipe.aside_view(
        PoolManager(), web.db, "top", champions, size=size, mode=mode
    )


def noms_generes(web, size=3, mode="actuel"):
    generated = vue(web, size, mode)["generated"]
    return [c["name"] for c in generated["champions"]] if generated else None


def test_la_page_affiche_la_carte_et_les_boutons_sans_js(web):
    designer_main_top(web)
    page = web.get("/meta?poste=top")
    assert page.status_code == 200
    assert 'id="meta-aside"' in page.text and 'id="swipe-body"' in page.text
    assert 'data-incoming="Darius"' in page.text and 'data-outgoing="Ahri"' in page.text
    assert 'data-swipe="take"' in page.text and 'data-swipe="pass"' in page.text
    assert "/meta/prendre?poste=top&amp;entrant=Darius&amp;sortant=Ahri" in page.text
    assert "données du 2 nov." in page.text


def test_accepter_remplace_le_sortant_et_efface_les_bans(web):
    designer_main_top(web)
    with sqlite3.connect(web.db) as db:
        db.execute(
            "INSERT INTO pool_ban_recommendations (pool_name, enemy_champion, threat_score,"
            " best_response_delta2, best_response_champion, matchups_count)"
            " VALUES ('Main', 'Zed', 1, 1, 'Ahri', 1)"
        )
    reply = post(web, "/meta/prendre?poste=top&entrant=Darius&sortant=Ahri")
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
    post(web, "/meta/prendre?poste=top&entrant=Darius&sortant=Ahri")
    assert lines == ["pool Main"]


def test_carte_perimee_refusee_sans_ecriture(web):
    designer_main_top(web)
    before = web.pools_file.read_text("utf-8")
    reply = post(web, "/meta/prendre?poste=top&entrant=Darius&sortant=Zed")
    assert reply.status_code == 200 and "Suggestion périmée" in reply.text
    assert web.pools_file.read_text("utf-8") == before


def test_pool_systeme_sans_carte_et_accepter_refuse(web):
    page = web.get("/meta?poste=top")
    assert page.status_code == 200
    assert "Pool système : duplique-le sur l&#39;écran Pool" in page.text
    assert 'data-swipe="take"' not in page.text
    reply = post(web, "/meta/prendre?poste=top&entrant=Darius&sortant=Ahri")
    assert "Pool système : duplique-le" in reply.text
    assert not web.pools_file.exists()


def test_passer_memorise_la_passe_par_version_et_la_carte_revient_au_nouveau_scrape(web):
    designer_main_top(web)
    reply = post(web, "/meta/passer?poste=top&entrant=Darius")
    assert reply.status_code == 200 and "Darius passé" in reply.text
    assert 'data-incoming="Darius"' not in reply.text
    prefs = json.loads(web.prefs_file.read_text("utf-8"))
    assert prefs["pool_swipe"] == {
        "version": "2026-11-02T10:00:00+00:00",
        "passed": {"top": ["Darius"]},
    }
    assert 'data-incoming="Darius"' not in web.get("/meta?poste=top").text

    with sqlite3.connect(web.db) as db:
        db.execute(
            "UPDATE db_meta SET value = '2026-11-03T10:00:00+00:00' WHERE key = 'last_scrape_utc'"
        )
    assert 'data-incoming="Darius"' in web.get("/meta?poste=top").text


def test_prendre_et_passer_ne_rendent_que_le_panneau(web):
    """Critère 7 : la réponse est le panneau seul, pas la page (ni la matrice)."""
    designer_main_top(web)
    for reply in (
        post(web, "/meta/passer?poste=top&entrant=Garen"),
        post(web, "/meta/prendre?poste=top&entrant=Darius&sortant=Ahri"),
    ):
        assert reply.status_code == 200
        assert 'id="meta-aside-body"' in reply.text and 'id="swipe-body"' in reply.text
        assert "role-matrix" not in reply.text and "<html" not in reply.text


def test_routes_meta_declarees_et_suggestions_redirige_vers_meta(web):
    designer_main_top(web)
    for path in ("/meta/generer", "/meta/creer", "/meta/exclure", "/meta/prendre", "/meta/passer"):
        assert post(web, path + "?poste=top", token=False).status_code == 403
    reply = post(web, "/meta/passer?poste=top&entrant=Garen")
    assert "Action inconnue" not in reply.text and 'id="swipe-body"' in reply.text
    for path in ("/pool/suggestions/accepter", "/pool/suggestions/passer"):
        assert post(web, path + "?poste=top&entrant=Garen").status_code == 404


def test_pool_suggestions_redirige_en_303_vers_meta(web):
    redirect = web.get("/pool/suggestions?poste=top", follow_redirects=False)
    assert redirect.status_code == 303 and redirect.headers["location"] == "/meta?poste=top"
    redirect = web.get("/pool/suggestions?poste=inconnu", follow_redirects=False)
    assert redirect.status_code == 303 and redirect.headers["location"] == "/meta"
    assert web.get("/pool/suggestions", follow_redirects=False).headers["location"] == "/meta"


def test_ecritures_sans_jeton_refusees(web):
    designer_main_top(web)
    for path in (
        "/meta/prendre?poste=top&entrant=Darius&sortant=Ahri",
        "/meta/passer?poste=top&entrant=Darius",
    ):
        assert post(web, path, token=False).status_code == 403
    assert saved(web)["Main"]["champions"] == ["Ahri"]
    assert not web.prefs_file.exists() or "pool_swipe" not in web.prefs_file.read_text("utf-8")


def test_page_charge_le_script_et_pose_le_seuil_de_glisser(web):
    designer_main_top(web)
    page = web.get("/meta?poste=top").text
    assert '<script src="/static/pool_swipe.js" defer></script>' in page
    assert f'data-drag="{pool_stats_config.POOL_SWIPE_DRAG_PX}"' in page


def test_ecran_pool_lien_meta_pour_pool_perso_designe_seulement(web):
    designer_main_top(web)
    assert 'href="/meta?poste=top"' in web.get("/pool?nom=Main").text
    assert "Méta du poste" in web.get("/pool?nom=Main").text
    assert 'href="/meta?poste=' not in web.get("/pool?nom=All%20Top%20Champions").text


def test_lien_meta_de_donnees_apres_un_run_ok(seeded_db, tmp_path):
    bus = EventBus()
    bus.publish("phase", {"kind": "closed"})
    job = UpdateJob(run=lambda progress, stop: PipelineResult(status="ok"), clock=lambda: 0.0)
    app = create_app(seeded_db, bus=bus, assets=make_assets(tmp_path), update_job=job)
    web = TestClient(app, base_url=LOCAL, raise_server_exceptions=False)
    assert "Voir la méta du poste" not in web.get("/donnees").text
    token = {client_config.TOKEN_HEADER: web.app.state.session_token}
    assert web.post("/donnees/actualiser", headers=token).status_code == 200
    assert job.cancel(5.0)
    assert 'href="/meta"' in web.get("/donnees").text


def test_accepter_garde_la_taille_et_la_place_du_sortant(web, monkeypatch):
    """L'entrant prend la place du sortant au milieu du pool (pile figée pour choisir le sortant)."""
    post(web, "/pool/creer", data={"arg": "Main"})
    for champion in ("Zed", "Garen", "Ahri"):
        post(web, f"/pool/ajouter?name=Main&arg={champion}")
    post(web, "/pool/role?name=Main&arg=top")
    card = SwapCard("top", "Darius", "Garen", 1.0, 0.5, 0.5, False, (), ())
    monkeypatch.setattr(client_pool_swipe, "_stack", lambda *args: ([card], None, None))
    post(web, "/meta/prendre?poste=top&entrant=Darius&sortant=Garen")
    assert saved(web)["Main"]["champions"] == ["Zed", "Darius", "Ahri"]


def test_routes_generateur_gardees_par_jeton(web):
    designer_main_top(web)
    for path in ("/meta/generer", "/meta/creer", "/meta/exclure"):
        assert post(web, path + "?poste=top", token=False).status_code == 403
    assert not web.prefs_file.exists() or "pool_exclusions" not in web.prefs_file.read_text("utf-8")


def test_generer_rend_le_pool_et_le_second_clic_ne_recalcule_pas(web, monkeypatch):
    calls = []
    original = client_pool_swipe.generate_pool

    def counting(*args):
        calls.append(args)
        return original(*args)

    monkeypatch.setattr(client_pool_swipe, "generate_pool", counting)
    designer_main_top(web)
    reply = post(web, "/meta/generer?poste=top&taille=3&mode=actuel")
    assert reply.status_code == 200
    assert len(noms_generes(web)) == 3
    assert len(calls) == 1
    post(web, "/meta/generer?poste=top&taille=3&mode=actuel")
    assert len(calls) == 1


def test_creer_ecrit_le_pool_genere_le_designe_au_top_et_suffixe_le_second(web):
    designer_main_top(web)
    post(web, "/meta/generer?poste=top&taille=3&mode=actuel")
    nom = f"TOP GÉNÉRÉ {date.today().isoformat()}"
    reply = post(web, "/meta/creer?poste=top&taille=3&mode=actuel")
    assert reply.status_code == 200 and f"« {nom} » créé" in reply.text
    assert len(saved(web)[nom]["champions"]) == 3
    prefs = json.loads(web.prefs_file.read_text("utf-8"))
    assert prefs["pools_by_role"]["top"] == nom

    post(web, "/meta/creer?poste=top&taille=3&mode=actuel")
    assert f"{nom} (2)" in saved(web)


def test_creer_sans_generation_possible_donne_une_notice(web):
    designer_main_top(web)
    for champion in ("Zed", "Darius", "Ahri"):
        post(web, f"/meta/exclure?poste=top&champion={champion}")
    reply = post(web, "/meta/creer?poste=top&taille=3&mode=actuel")
    assert "Pas assez de champions" in reply.text
    assert set(saved(web)) == {"Main"}


def test_exclure_retire_le_champion_des_cartes_et_du_generateur(web):
    designer_main_top(web)
    reply = post(web, "/meta/exclure?poste=top&champion=darius")
    assert reply.status_code == 200 and "Darius exclu du générateur" in reply.text
    assert 'data-incoming="Darius"' not in reply.text
    assert vue(web)["exclusions"][0]["name"] == "Darius"

    post(web, "/meta/generer?poste=top&taille=3&mode=actuel")
    assert "Darius" not in noms_generes(web)

    accept = post(web, "/meta/prendre?poste=top&entrant=Darius&sortant=Ahri")
    assert "Suggestion périmée" in accept.text
    assert saved(web)["Main"]["champions"] == ["Ahri"]

    post(web, "/meta/exclure?poste=top&champion=Darius&retirer=1")
    assert 'data-incoming="Darius"' in web.get("/meta?poste=top").text


def test_exclus_restent_exclus_apres_une_mise_a_jour_des_donnees(web):
    designer_main_top(web)
    post(web, "/meta/exclure?poste=top&champion=Darius")
    with sqlite3.connect(web.db) as db:
        db.execute(
            "UPDATE db_meta SET value = '2026-11-03T10:00:00+00:00' WHERE key = 'last_scrape_utc'"
        )
    post(web, "/meta/generer?poste=top&taille=3&mode=actuel")
    assert "Darius" not in noms_generes(web)
    assert 'data-incoming="Darius"' not in web.get("/meta?poste=top").text


def test_champion_inconnu_refuse_sans_ecriture(web):
    designer_main_top(web)
    reply = post(web, "/meta/exclure?poste=top&champion=Yone")
    assert "Champion inconnu" in reply.text
    assert "pool_exclusions" not in web.prefs_file.read_text("utf-8")


def test_taille_et_mode_invalides_ramenes_au_defaut(web):
    designer_main_top(web)
    reply = post(web, "/meta/generer?poste=top&taille=9&mode=inconnu")
    assert f"Pas assez de champions pour un pool de {pool_stats_config.POOL_GEN_DEFAULT_SIZE}" in (
        reply.text
    )
    view = vue(web, size="9", mode="inconnu")
    assert view["size"] == pool_stats_config.POOL_GEN_DEFAULT_SIZE
    assert view["mode"] == "moyenne"
    assert view["sizes"] == [3, 4, 5, 6]


def test_generer_lit_le_corps_et_le_corps_l_emporte_sur_la_query(web):
    designer_main_top(web)
    reply = post(
        web,
        "/meta/generer?poste=top&taille=4&mode=moyenne",
        data={"poste": "top", "taille": "3", "mode": "actuel"},
    )
    assert reply.status_code == 200
    assert len(noms_generes(web, size=3, mode="actuel")) == 3
    assert noms_generes(web, size=4, mode="moyenne") is None


def test_creer_lit_le_corps_taille_et_mode(web):
    designer_main_top(web)
    post(
        web,
        "/meta/creer",
        data={"poste": "top", "taille": "3", "mode": "actuel"},
    )
    nom = f"TOP GÉNÉRÉ {date.today().isoformat()}"
    assert len(saved(web)[nom]["champions"]) == 3


def test_exclure_lit_le_champion_et_le_retrait_dans_le_corps(web):
    designer_main_top(web)
    reply = post(
        web,
        "/meta/exclure?poste=top&champion=Ahri",
        data={"poste": "top", "champion": "Darius"},
    )
    assert "Darius exclu du générateur" in reply.text
    assert vue(web)["exclusions"][0]["name"] == "Darius"
    reply = post(
        web,
        "/meta/exclure",
        data={"poste": "top", "champion": "Darius", "retirer": "1"},
    )
    assert "Darius rétabli dans le générateur" in reply.text
    assert vue(web)["exclusions"] == []


def test_section_generer_presente_sans_generation(web):
    designer_main_top(web)
    page = web.get("/meta?poste=top").text
    assert "Générer un pool" in page
    assert 'hx-post="/meta/generer"' in page
    assert 'name="taille"' in page and 'name="mode" value="moyenne"' in page
    assert 'name="mode" value="actuel"' in page
    assert 'class="htmx-indicator' in page and "Calcul…" in page
    assert 'list="gen-champions"' in page and '<datalist id="gen-champions">' in page
    assert "Créer le pool" not in page


def test_resultat_generer_affiche_pool_et_creer(web):
    designer_main_top(web)
    reply = post(web, "/meta/generer?poste=top&taille=3&mode=actuel")
    assert all(f"<b>{name}</b>" in reply.text for name in noms_generes(web))
    assert "Créer le pool" in reply.text
    assert 'hx-post="/meta/creer"' in reply.text
    assert '<table class="gen-table">' in reply.text and 'scope="col"' in reply.text


def test_puce_exclu_a_son_bouton_de_retablissement(web):
    designer_main_top(web)
    post(web, "/meta/exclure?poste=top&champion=Darius")
    page = web.get("/meta?poste=top").text
    assert 'aria-label="Rétablir Darius"' in page
    assert "retirer=1" in page


def test_aside_expose_l_arbre_du_pool_utilisateur_et_du_pool_systeme(web):
    designer_main_top(web)
    user = vue(web)
    assert user["tree"] is not None
    assert [c["name"] for c in user["tree"]["blind"]] == ["Ahri"]
    page = web.get("/meta?poste=top").text
    assert "Arbre de décision" in page and "Matrices du scrape actuel, sans maîtrise." in page
    post(web, "/pool/supprimer?name=Main")
    system = vue(web)
    assert system["pool"]["editable"] is False and system["tree"] is not None
    assert system["card"] is None


def test_pool_genere_expose_un_arbre_et_plus_de_counters(web):
    designer_main_top(web)
    post(web, "/meta/generer?poste=top&taille=3&mode=actuel")
    generated = vue(web, 3, "actuel")["generated"]
    assert generated is not None
    assert "counters" not in generated
    assert {row["enemy"]["name"] for row in generated["tree"]["rows"]} <= {
        "Garen",
        "Zed",
        "Darius",
        "Ahri",
    }
