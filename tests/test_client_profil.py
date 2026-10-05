"""Écran Profil du client (SPEC-21 tâche 77), sur les fixtures du relevé de la tâche 76."""

import copy

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.profil import profile_view
from src.client.lcu_proxy import ForbiddenEndpoint, LcuProxy
from tests.support_lcu_nav import FauxLcuNav, fixture, make_assets

LOCAL = "http://127.0.0.1"


def client(temp_db, tmp_path, lcu):
    app = create_app(temp_db, lcu=lcu, assets=make_assets(tmp_path))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def view(**changes):
    parts = {
        "summoner": fixture("current_summoner"),
        "ranked": fixture("ranked_stats"),
        "regalia": fixture("regalia"),
        "challenges": fixture("challenges_summary"),
    }
    parts.update(changes)
    return profile_view(**parts)


# ---------- vue ----------


def test_identite_et_progression():
    v = view()
    assert (v["name"], v["tag"], v["level"]) == ("Invocateur", "EUW", 670)
    assert v["icon"] == "/assets/profileicon/7048.png"
    assert v["xp"]["percent"] == 64 and v["privacy"] == "Profil public"


def test_cartes_de_rang_solo_et_flex_sans_tft():
    solo, flex = view()["queues"]
    assert (solo["name"], solo["tier"], solo["lp"]) == ("Classée solo/duo", "Diamant II", 49)
    assert solo["stats"] == [
        ("369", "victoires"),
        ("370", "défaites"),
        ("50 %", "taux de victoire"),
    ]
    assert (flex["tier"], flex["lp"]) == ("Émeraude I", 75)
    assert view()["queues"] == [solo, flex]  # la file TFT du LCU n'est pas affichée


def test_maitre_sans_division_et_non_classe():
    ranked = copy.deepcopy(fixture("ranked_stats"))
    ranked["queues"][0].update(tier="MASTER", division="NA", leaguePoints=211)
    ranked["queues"][1].update(
        tier="", division="NA", isProvisional=True, provisionalGamesRemaining=3
    )
    solo, flex = view(ranked=ranked)["queues"]
    assert solo["tier"] == "Maître"
    assert flex["empty"] and "3 parties à jouer" in flex["note"]


def test_serie_de_promotion():
    ranked = copy.deepcopy(fixture("ranked_stats"))
    ranked["queues"][0]["miniSeriesProgress"] = "WLN"
    assert view(ranked=ranked)["queues"][0]["note"] == "Série de promotion : V D ·"


def test_defis_categories_et_meilleurs_defis():
    c = view()["challenges"]
    assert c["level"] == "Diamant" and c["title"] == "Masterful"
    collection = c["categories"][0]
    assert collection["name"] == "Collection" and collection["percent"] == 84
    assert collection["current"] == "3\u202f535"
    assert len(c["top"]) == 3 and c["top"][0]["name"]


def test_une_section_absente_est_indisponible_pas_une_erreur():
    v = view(ranked=None, regalia=None, challenges=None)
    assert v["queues"] is None and v["regalia"] is None and v["challenges"] is None


def test_regalia():
    labels = dict(view()["regalia"])
    assert labels["Rang le plus élevé"] == "Diamant II"
    assert labels["Saison précédente"] == "Maître"


# ---------- route ----------


def test_route_avec_le_client_ouvert(temp_db, tmp_path):
    lcu = FauxLcuNav()
    response = client(temp_db, tmp_path, lcu).get("/profil")
    assert response.status_code == 200
    for text in ("Invocateur", "Diamant II", "Émeraude I", "Défis", "Masterful"):
        assert text in response.text
    assert lcu.writes == []  # lecture seule


def test_route_client_ferme(temp_db, tmp_path):
    response = client(temp_db, tmp_path, None).get("/profil")
    assert response.status_code == 200 and "Client LoL fermé" in response.text


def test_route_client_qui_ne_repond_pas(temp_db, tmp_path):
    lcu = FauxLcuNav({"/lol-summoner/v1/current-summoner": None})
    response = client(temp_db, tmp_path, lcu).get("/profil")
    assert response.status_code == 200 and "ne répond pas" in response.text


def test_route_forme_inattendue_apres_un_patch(temp_db, tmp_path):
    lcu = FauxLcuNav({"/lol-summoner/v1/current-summoner": {"displayName": "x"}})
    response = client(temp_db, tmp_path, lcu).get("/profil")
    assert response.status_code == 200 and "ne répond pas" in response.text


def test_route_sans_les_sections_secondaires(temp_db, tmp_path):
    lcu = FauxLcuNav(
        {
            "/lol-ranked/v1/current-ranked-stats": None,
            "/lol-regalia/v2/current-summoner/regalia": None,
            "/lol-challenges/v1/summary-player-data/local-player": None,
        }
    )
    response = client(temp_db, tmp_path, lcu).get("/profil")
    assert response.status_code == 200
    assert "Rangs indisponibles" in response.text and "Défis indisponibles" in response.text


# ---------- liste blanche ----------


@pytest.mark.parametrize(
    "endpoint",
    [
        "/lol-ranked/v1/current-ranked-stats",
        "/lol-regalia/v2/current-summoner/regalia",
        "/lol-challenges/v1/summary-player-data/local-player",
    ],
)
def test_lectures_du_profil_autorisees(endpoint):
    assert LcuProxy(FauxLcuNav()).get(endpoint) is not None


def test_une_ecriture_sur_le_profil_est_refusee():
    proxy = LcuProxy(FauxLcuNav())
    with pytest.raises(ForbiddenEndpoint):
        proxy.send("PUT", "/lol-summoner/v1/current-summoner/icon", {"profileIconId": 1})
