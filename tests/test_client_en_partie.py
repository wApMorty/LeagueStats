"""SPEC-24 tâche 108 : écran « En partie », cadre, navigation, pastille, face-à-face de la draft.

Hermétique : bus en mémoire, base temporaire, analyse construite par `build_final_analysis` sur
l'évaluateur factice de `test_final_analysis_face_off`. Aucun client LoL, aucun test d'interface réel.
"""

import json
import re

import pytest
from fastapi.testclient import TestClient

from src.client import en_partie
from src.client.app import create_app
from src.client.assets import Assets
from src.client.bus import EventBus
from src.client.draft_view import Champions
from src.config_client import client_config
from src.draft.final_analysis import build_final_analysis
from tests import test_final_analysis_face_off as fo
from tests.test_client_draft import BASE, CHAMPIONS, LOCAL, assets, bus  # noqa: F401  (fixtures)


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
    names = re.findall(
        r'class="ig-side ig-(?:ally|foe)-ink">(?:<img[^>]*>)?([^<]+)(?:<img[^>]*>)?</td>', html
    )
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
    assert "<th>Mat</th>" not in html and "<th>Syn</th>" not in html
    assert "<th>Tot</th>" in html
    assert html.count('title="Matchups ') == 10  # un par champion chiffré
    assert "Synergies " in html


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
    # La pastille « En partie » est devenue la pastille de phase permanente (SPEC-25) : voir
    # tests/test_client_phase_pastille.py.
    assert 'id="tb-phase"' in html


def test_script_servi_et_charge(client):
    assert client.get("/static/en_partie.js").status_code == 200
    assert "en_partie.js" in client.get("/").text


def test_aucune_bascule_automatique_de_page():
    source = open("src/client/static/en_partie.js", encoding="utf-8").read()
    assert "pushState" not in source and "htmx.ajax" not in source and "location" not in source


def test_horloge():
    assert en_partie.clock(754.9) == "12:34" and en_partie.clock(None) == "0:00"


# ---------- courbe de win chance en direct (SPEC-24 tâche 109) ----------


def series(start=0.0, count=30, step=5.0):
    return [[start + i * step, 0.5 + 0.01 * i] for i in range(count)]


def objectives():
    return [
        {"t": 60.0, "kind": "dragon", "team": "ORDER"},
        {"t": 90.0, "kind": "turret", "team": "CHAOS"},
        {"t": 120.0, "kind": "baron", "team": "ORDER"},
    ]


def test_la_courbe_est_tracee_avec_les_reperes_d_objectifs(client, bus):  # noqa: F811
    bus.publish(
        "ingame",
        {**LIVE, "series": series(), "objectives": objectives(), "me": {"team": "ORDER"}},
    )
    html = stage(client)
    assert 'class="chart"' in html or "<svg" in html
    assert "Win chance en direct" in html and "+3 pts sur la dernière minute" in html
    assert ">Dragon<" in html and ">Nashor<" in html and "Tour adverse" in html
    assert "La courbe apparaît après" not in html


@pytest.mark.parametrize("points", [[], [[10.0, 0.5]]])
def test_moins_de_deux_points_un_message_et_pas_de_courbe(client, bus, points):  # noqa: F811
    bus.publish("ingame", {**LIVE, "series": points})
    html = stage(client)
    assert "La courbe apparaît après quelques secondes" in html
    assert "ch-line" not in html


def test_sans_modele_pas_de_courbe(client, bus):  # noqa: F811
    bus.publish(
        "ingame", {"state": "live", "game_time": 600.0, "p": None, "delta": None, "series": []}
    )
    assert "ch-line" not in stage(client)


def test_un_client_ouvert_en_cours_de_partie_le_dit(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "series": series(start=900.0)})
    html = stage(client)
    assert "ch-line" in html and "pas tracé" in html and "depuis 15:00" in html


def test_pas_de_note_quand_la_courbe_part_du_debut(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "series": series(start=0.0)})
    assert "pas tracé" not in stage(client)


def test_les_objectifs_hors_de_la_courbe_ne_sont_pas_reperes(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "series": series(start=900.0), "objectives": objectives()})
    assert ">Dragon<" not in stage(client)


def test_le_point_de_depart_de_la_draft_n_est_pas_sur_la_courbe(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "series": series()})
    bus.publish("game", analysis())
    html = stage(client)
    chart = html.split("Win chance en direct")[1].split("Face-à-face")[0]
    assert "55" not in chart.replace(
        "0.55", ""
    )  # la probabilité de la draft (55 %) n'est pas tracée


# ---------- portraits et infobulle du face-à-face (SPEC-30 tâche 138) ----------


@pytest.fixture
def champions(tmp_path, monkeypatch):
    """Un `Champions` dont le `champion.json` factice contient Wukong (id `MonkeyKing`) en plus."""
    monkeypatch.setattr(client_config, "DDRAGON_VERSION", "16.2.1")
    data = {
        **CHAMPIONS["data"],
        "MonkeyKing": {"key": "62", "id": "MonkeyKing", "name": "Wukong", "tags": []},
    }
    files = {f"{BASE}/cdn/16.2.1/data/fr_FR/champion.json": json.dumps({"data": data}).encode()}
    return Champions(Assets(tmp_path / "cache", fetch=files.get))


@pytest.mark.parametrize(
    "name, expected",
    [
        ("MonkeyKing", ("MonkeyKing", "Wukong")),
        ("Wukong", ("MonkeyKing", "Wukong")),
        ("Lee Sin", ("LeeSin", "Lee Sin")),
        ("lee sin", ("LeeSin", "Lee Sin")),
        ("LeeSin", ("LeeSin", "Lee Sin")),
    ],
)
def test_champions_by_name_rapproche_id_et_nom_data_dragon(champions, name, expected):
    ident, display = expected
    assert champions.by_name(name) == {"img": f"/assets/champion/{ident}.png", "name": display}


def test_champions_by_name_inconnu(champions):
    assert champions.by_name("Inconnu") is None
    assert champions.by_name("MonkeyKing")["name"] == "Wukong"


def test_face_a_face_portrait_nom_data_dragon_et_infobulle(champions):
    rows = en_partie.analysis_view(analysis(), champions)["rows"]
    darius, garen = rows[0]["enemy"], rows[0]["ally"]
    assert darius["img"] == "/assets/champion/Darius.png" and darius["name"] == "Darius"
    assert garen["img"] is None and garen["name"] == "Garen"  # inconnu de Data Dragon : nom gardé
    assert re.fullmatch(r"Matchups [+-]\d+\.\d · Synergies [+-]\d+\.\d", darius["detail"])
    assert darius["total"] is not None and darius["matchup"] and darius["synergy"]


def test_face_a_face_sans_champions_aucun_portrait():
    rows = en_partie.analysis_view(analysis())["rows"]
    assert all(r[side]["img"] is None for r in rows for side in ("ally", "enemy") if r[side])


def test_champion_aux_donnees_minces_sans_infobulle(champions):
    rows = en_partie.analysis_view(analysis(thin={"Garen"}), champions)["rows"]
    garen = rows[0]["ally"]
    assert garen["thin"] and garen["detail"] is None and garen["total"] is None


# ---------- gabarit à deux colonnes (SPEC-30 tâche 139) ----------


def test_fragment_bandeau_grille_et_ordre_des_panneaux(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "series": series(), "me": {"team": "ORDER"}})
    bus.publish("game", analysis())
    html = stage(client)
    assert 'class="ig-strip"' in html and 'class="ig-grid"' in html and "ig-head" not in html
    assert html.count('class="ig-col"') == 2
    build, curve, draft = (
        html.index(f'aria-label="{x}"')
        for x in ("Build", "Win chance en direct", "Analyse de la draft")
    )
    first, second = (m.start() for m in re.finditer('class="ig-col"', html))
    assert html.index("ig-strip") < html.index("ig-grid") < first < build < second < curve < draft


def test_chaque_champion_connu_a_son_portrait(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    bus.publish("game", analysis())
    html = stage(client)
    # Darius, Lee Sin, Ahri et Jinx sont dans le champion.json factice ; Garen, Vi, Syndra, etc. non.
    assert re.findall(r'<img class="ig-champ" src="(/assets/champion/[^"]+\.png)"', html) == [
        "/assets/champion/Darius.png",
        "/assets/champion/LeeSin.png",
        "/assets/champion/Ahri.png",
        "/assets/champion/Jinx.png",
    ]
    # allié : portrait avant le nom ; ennemi : nom avant le portrait
    assert 'ig-ally-ink"><img class="ig-champ" src="/assets/champion/Ahri.png" alt="">Ahri<' in html
    assert 'ig-foe-ink">Lee Sin<img class="ig-champ" src="/assets/champion/LeeSin.png"' in html
    assert 'ig-ally-ink">Garen<' in html  # inconnu de Data Dragon : ni portrait ni nom changé


def test_la_courbe_a_la_taille_de_la_colonne(client, bus):  # noqa: F811
    bus.publish("ingame", {**LIVE, "series": series()})
    assert 'viewBox="0 0 736 220"' in stage(client)


def test_tableau_a_cinq_colonnes_et_legende_courte(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    bus.publish("game", analysis(thin={"Garen"}))
    html = stage(client)
    assert len(re.findall(r"<th", html.split("<thead>")[1].split("</thead>")[0])) == 5
    assert "détail au survol" in html and "peu de données" in html


# ---------- ligne d'état des postes (SPEC-27 tâche 127, §4.6) ----------


def with_reality(reality):
    return {**analysis(), "reality": reality}


def mismatch(champion, predicted, real):
    return {"champion": champion, "predicted": predicted, "real": real}


def test_sans_charge_reality_aucune_ligne_ni_marque():
    view = en_partie.analysis_view(analysis())
    assert view["reality"] is None
    sides = [side for row in view["rows"] for side in (row["ally"], row["enemy"]) if side]
    assert sides and all(side["corrected"] is False for side in sides)


def test_reality_absent_ou_etat_inconnu_donne_none():
    assert en_partie.analysis_view(with_reality(None))["reality"] is None
    assert en_partie.analysis_view(with_reality({"state": "bizarre"}))["reality"] is None


def test_etat_ok_texte_exact():
    view = en_partie.analysis_view(with_reality({"state": "ok", "checked": 10, "mismatches": []}))
    assert view["reality"] == {
        "state": "ok",
        "text": "Postes vérifiés en partie : 10 sur 10 conformes",
    }


def test_etat_corrected_texte_exact_avec_deux_champions():
    reality = {
        "state": "corrected",
        "checked": 10,
        "mismatches": [mismatch("Ahri", "milieu", "bas"), mismatch("Jinx", "bas", "haut")],
    }
    view = en_partie.analysis_view(with_reality(reality))
    assert view["reality"] == {
        "state": "corrected",
        "text": "Postes corrigés en partie : Ahri (bas, prédit milieu), Jinx (haut, prédit bas). "
        "Face-à-face et build recalculés",
    }


def test_etat_corrected_au_dela_de_deux_champions_et_n_autres():
    reality = {
        "state": "corrected",
        "checked": 10,
        "mismatches": [
            mismatch("Ahri", "milieu", "bas"),
            mismatch("Jinx", "bas", "haut"),
            mismatch("Draven", "bas", "milieu"),
            mismatch("Rell", "support", "jungle"),
        ],
    }
    text = en_partie.analysis_view(with_reality(reality))["reality"]["text"]
    assert text == (
        "Postes corrigés en partie : Ahri (bas, prédit milieu), Jinx (haut, prédit bas) "
        "et 2 autres. Face-à-face et build recalculés"
    )
    assert "Draven" not in text and "Rell" not in text


def test_etat_partial_texte_exact():
    view = en_partie.analysis_view(
        with_reality({"state": "partial", "checked": 0, "mismatches": []})
    )
    assert view["reality"] == {
        "state": "partial",
        "text": "Postes adverses non lus en partie : analyse de la draft conservée",
    }


def test_les_lignes_corrigees_sont_marquees_des_deux_cotes_seulement():
    # Ahri est alliée (ligne 2), Draven ennemie (ligne 3) ; Garen (ligne 0) n'est pas corrigé.
    reality = {
        "state": "corrected",
        "checked": 10,
        "mismatches": [mismatch("Ahri", "milieu", "bas"), mismatch("Draven", "bas", "milieu")],
    }
    rows = en_partie.analysis_view(with_reality(reality))["rows"]
    assert rows[2]["ally"]["corrected"] is True and rows[2]["enemy"]["corrected"] is False
    assert rows[3]["enemy"]["corrected"] is True and rows[3]["ally"]["corrected"] is False
    assert rows[0]["ally"]["corrected"] is False and rows[0]["enemy"]["corrected"] is False


def test_marquage_sur_le_nom_et_pas_sur_le_portrait(champions):
    reality = {
        "state": "corrected",
        "checked": 10,
        "mismatches": [mismatch("Darius", "haut", "bas")],
    }
    rows = en_partie.analysis_view(with_reality(reality), champions)["rows"]
    assert rows[0]["enemy"]["name"] == "Darius" and rows[0]["enemy"]["corrected"] is True
    assert rows[0]["ally"]["corrected"] is False


def test_etat_ok_rendu_entre_panel_head_et_table(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    bus.publish("game", with_reality({"state": "ok", "checked": 10, "mismatches": []}))
    html = stage(client)
    line = '<p class="fine ig-reality">Postes vérifiés en partie : 10 sur 10 conformes</p>'
    draft = html.index('aria-label="Analyse de la draft"')
    assert html.index(line) > html.index("panel-head", draft)
    assert html.index(line) < html.index('<table class="ig-table">')
    assert html.count('class="fine ig-reality"') == 1


def test_sans_reality_pas_de_ligne_d_etat(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    bus.publish("game", analysis())
    html = stage(client)
    assert "ig-reality" not in html and "is-corrected" not in html and "poste corrigé" not in html


def test_etat_partial_rendu_sans_marque(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    bus.publish("game", with_reality({"state": "partial", "checked": 0, "mismatches": []}))
    html = stage(client)
    assert "Postes adverses non lus en partie : analyse de la draft conservée" in html
    assert "is-corrected" not in html


def test_lignes_corrigees_rendues_avec_poste_corrige_au_bon_cote(client, bus):  # noqa: F811
    bus.publish("ingame", LIVE)
    reality = {
        "state": "corrected",
        "checked": 10,
        "mismatches": [mismatch("Ahri", "milieu", "bas"), mismatch("Draven", "bas", "milieu")],
    }
    bus.publish("game", with_reality(reality))
    html = stage(client)
    assert html.count('<tr class="is-corrected">') == 2
    assert html.count("poste corrigé") == 2
    assert (
        'ig-ally-ink"><img class="ig-champ" src="/assets/champion/Ahri.png" alt="">Ahri <span class="fine">poste corrigé</span></td>'
        in html
    )
    assert 'ig-foe-ink"><span class="fine">poste corrigé</span> Draven' in html
    assert "Garen <span" not in html and "Darius <span" not in html


def test_etat_corrected_sans_build_recalculee_le_dit():
    reality = {
        "state": "corrected",
        "checked": 10,
        "mismatches": [mismatch("Ahri", "milieu", "bas")],
        "build": False,
    }
    text = en_partie.analysis_view(with_reality(reality))["reality"]["text"]
    assert text == (
        "Postes corrigés en partie : Ahri (bas, prédit milieu). Face-à-face recalculé, build conservée"
    )
