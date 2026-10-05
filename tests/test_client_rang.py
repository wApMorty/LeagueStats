"""Écran Rang du client (SPEC-21 tâche 51) : séries, ignorance visible, cartes, route en lecture seule."""

import re
import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.data import rank_view, scale_label, tier_name
from src.coaching.progression import lp_scale

LOCAL = "http://127.0.0.1"
SOLO, FLEX = "RANKED_SOLO_5x5", "RANKED_FLEX_SR"


def snap(day, queue=SOLO, tier="EMERALD", division="II", lp=47, wins=62, losses=55, **extra):
    """Une photo de rang telle que `rank_history()` la rend (jour d'octobre 2026, midi)."""
    row = {
        "captured": f"2026-10-{day:02d} 12:00:00",
        "queue": queue,
        "tier": tier,
        "division": division,
        "lp": lp,
        "wins": wins,
        "losses": losses,
        "lp_delta": None,
        "game_id": None,
    }
    row.update(extra)
    return row


def insert(db, rows):
    for r in rows:
        db.connection.execute(
            "INSERT INTO rank_snapshots (captured_utc, queue, tier, division, lp, wins, losses, "
            "lp_delta, game_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            tuple(
                r[k] for k in "captured queue tier division lp wins losses lp_delta game_id".split()
            ),
        )
    db.connection.commit()


def client(temp_db):
    return TestClient(create_app(temp_db), base_url=LOCAL, raise_server_exceptions=False)


def two_queues():
    return [
        snap(1, lp=10),
        snap(2, lp=40),
        snap(3, division="I", lp=20),
        snap(3, FLEX, "PLATINUM", "I", 22, 14, 9),
        snap(5, FLEX, "PLATINUM", "I", 60, 15, 9),
    ]


# ---------- données ----------


def test_base_vide():
    view = rank_view([])
    assert view["empty"] and view["chart"] is None and view["bars"] is None
    assert [c["empty"] for c in view["cards"]] == [True, True]


def test_une_courbe_par_file_avec_le_dernier_point_etiquete():
    view = rank_view(two_queues())
    svg = str(view["chart"])
    assert svg.count('class="ch-line"') == 2
    assert (
        "Émeraude I · 20 LP" in svg
    )  # étiquette de la file principale, rang et LP du dernier point
    assert "Platine I · 60 LP" not in svg  # un seul dernier point étiqueté
    assert "5 oct." in svg and "1 oct." in svg  # graduations de dates


def test_sous_deux_photos_une_file_n_a_pas_de_courbe():
    history = [snap(1), snap(2, lp=60), snap(3, FLEX, "PLATINUM", "I", 22)]
    view = rank_view(history)
    solo, flex = view["cards"]
    assert solo["curve"] and not flex["curve"]
    assert str(view["chart"]).count('class="ch-line"') == 1
    assert "pas assez de photos" not in solo["note"]
    assert flex["photos"] == 1 and flex["tier"] == "Platine I"  # la carte reste, sans delta


def test_aucune_file_avec_assez_de_photos_pas_de_graphique():
    view = rank_view([snap(1)])
    assert not view["empty"] and view["chart"] is None


def test_un_plateau_de_photos_identiques_ne_charge_pas_la_courbe():
    history = [snap(d, lp=47) for d in range(1, 6)] + [snap(6, lp=60)]
    points = re.findall(r'class="ch-dot"', str(rank_view(history)["chart"]))
    # 5 photos identiques : seules la première et la dernière du plateau restent (+ le dernier point)
    assert len(points) == 2


def test_carte_de_file_victoires_defaites_et_delta():
    card = rank_view(two_queues())["cards"][0]
    assert card["tier"] == "Émeraude I" and card["lp"] == 20
    assert card["stats"] == [
        ("62 V", "victoires"),
        ("55 D", "défaites"),
        ("53 %", "taux de victoire"),
    ]
    expected = lp_scale("EMERALD", "I", 20) - lp_scale("EMERALD", "II", 10)
    assert card["note"] == f"+{expected} LP depuis le 1 oct. · 3 photos"


def test_le_delta_se_borne_a_la_fenetre_de_30_jours():
    history = [
        snap(1, lp=0, tier="GOLD", division="I"),
        {**snap(1, lp=0), "captured": "2026-12-01 12:00:00"},
        {**snap(1, lp=50), "captured": "2026-12-20 12:00:00"},
    ]
    note = rank_view(history)["cards"][0]["note"]
    assert note == "+50 LP sur 30 jours · 3 photos"


def test_victoires_inconnues_pas_de_statistiques():
    card = rank_view([snap(1, wins=None, losses=None), snap(2, wins=None, losses=None)])["cards"][0]
    assert "stats" not in card


def test_histogramme_des_lp_seulement_pour_le_solo_et_les_parties_avec_variation():
    history = [
        snap(1),
        snap(2, lp_delta=19, game_id=1),
        snap(3, lp_delta=-15, game_id=2),
        snap(3, FLEX, lp_delta=30, game_id=3),
        snap(4, lp_delta=None, game_id=None),
    ]
    bars = rank_view(history)["bars"]
    assert bars["title"] == "LP par partie · 2 dernières en solo/duo"
    assert bars["mean"] == "Moyenne +2,0 LP"
    assert str(bars["svg"]).count("<rect") == 2
    assert "+19 LP" in str(bars["svg"]) and "−15 LP" in str(bars["svg"])


def test_histogramme_limite_aux_vingt_dernieres_parties():
    history = [snap(1)] + [snap(2, lp_delta=i, game_id=i) for i in range(30)]
    bars = rank_view(history)["bars"]
    assert str(bars["svg"]).count("<rect") == 20


def test_sans_variation_pas_d_histogramme():
    assert rank_view([snap(1), snap(2)])["bars"] is None


def test_noms_de_paliers_et_graduations():
    assert tier_name({"tier": "EMERALD", "division": "II"}) == "Émeraude II"
    assert tier_name({"tier": "MASTER", "division": "I"}) == "Maître"  # pas de division en Maître+
    assert tier_name({"tier": "UNKNOWN", "division": None}) == "Unknown"
    assert scale_label(lp_scale("PLATINUM", "III", 0)) == "Platine III"
    assert scale_label(lp_scale("EMERALD", "I", 0)) == "Émeraude I"
    assert scale_label(lp_scale("MASTER", None, 0)) == "Maître"


# ---------- route ----------


def test_route_sur_base_vide_repond_200_avec_l_etat_vide(temp_db):
    response = client(temp_db).get("/rang")
    assert response.status_code == 200
    assert "Aucune photo de rang" in response.text


def test_route_sur_base_non_migree_repond_200(tmp_path):
    path = tmp_path / "vide.db"
    sqlite3.connect(path).close()
    response = client(path).get("/rang")
    assert response.status_code == 200 and "Aucune photo de rang" in response.text


def test_route_trace_les_deux_courbes(db, temp_db):
    insert(db, two_queues())
    page = client(temp_db).get("/rang").text
    assert page.count('class="ch-line"') == 2
    assert "Classée solo/duo" in page and "Classée flexible" in page
    assert 'aria-current="page"' in page.split("Rang</span></a>")[0].rsplit("<a ", 1)[1]


def test_route_une_file_sans_courbe_le_dit(db, temp_db):
    insert(db, [snap(1), snap(2, lp=60), snap(3, FLEX, "PLATINUM", "I", 22)])
    page = client(temp_db).get("/rang").text
    assert page.count('class="ch-line"') == 1
    assert "pas assez de photos pour une courbe" in page


def test_la_consultation_n_ecrit_pas_dans_la_base(db, temp_db):
    insert(db, two_queues())
    before = (temp_db.stat().st_mtime_ns, temp_db.read_bytes())
    assert client(temp_db).get("/rang").status_code == 200
    assert (temp_db.stat().st_mtime_ns, temp_db.read_bytes()) == before


def test_entree_de_navigation_active(temp_db):
    page = client(temp_db).get("/rang").text
    assert '<a class="nav-item" href="/rang"' in page
