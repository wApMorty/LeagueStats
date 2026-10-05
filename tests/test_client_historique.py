"""Écran Historique du client (SPEC-21 tâche 78) : la liste du LCU, son détail, le lien vers l'analyse."""

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.draft_view import Champions
from src.client.historique import game_view, history_view
from src.client.lcu_proxy import ForbiddenEndpoint, LcuProxy
from src.repositories.coaching import CoachingRepository
from tests.support_lcu_nav import GAME_ID, FauxLcuNav, fixture, make_assets

LOCAL = "http://127.0.0.1"
NOW = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
PUUID = "puuid-test-0001"


@pytest.fixture
def champions(tmp_path):
    return Champions(make_assets(tmp_path))


def client(temp_db, tmp_path, lcu):
    app = create_app(temp_db, lcu=lcu, assets=make_assets(tmp_path))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


# ---------- liste ----------


def test_la_liste_donne_resultat_kda_sbires_et_file(champions):
    view = history_view(fixture("match_history"), set(), champions, NOW)
    first, second, third = view["rows"]
    stats = fixture("match_history")["games"]["games"][0]["participants"][0]["stats"]
    assert first["win"] and not second["win"]
    assert first["kda"] == f"{stats['kills']} / {stats['deaths']} / {stats['assists']}"
    assert first["queue"] == "Classée solo/duo" and third["queue"] == "ARAM"
    assert first["duration"] == "27:27" and first["champion"] == "Sion"
    assert "/min" in first["cs"]
    assert view["summary"] == "3 parties · 2 V · 1 D"


def test_une_partie_capturee_est_marquee(champions):
    view = history_view(fixture("match_history"), {GAME_ID}, champions, NOW)
    assert [r["captured"] for r in view["rows"]] == [True, False, False]
    assert view["captured"] == 1


def test_une_entree_illisible_ne_masque_pas_les_autres(champions):
    matches = fixture("match_history")
    matches["games"]["games"][1] = {"gameId": 1}
    view = history_view(matches, set(), champions, NOW)
    assert len(view["rows"]) == 2


def test_liste_vide(champions):
    matches = {"games": {"games": []}}
    assert history_view(matches, set(), champions, NOW)["empty"]


# ---------- détail ----------


def test_le_detail_porte_les_deux_equipes_et_repere_le_joueur(champions):
    view = game_view(fixture("game_detail"), PUUID, set(), champions, NOW)
    assert (
        view["result"] == "Victoire" and view["win"]
    )  # le participant 6 est dans l'équipe 200, gagnante
    blue, red = view["teams"]
    assert (blue["name"], blue["win"], len(blue["players"])) == ("Équipe bleue", False, 5)
    assert red["win"] and [p["mine"] for p in red["players"]] == [True, False, False, False, False]
    assert red["players"][0]["name"] == "Invocateur" and red["players"][0]["champion"] == "Sion"
    assert ("tours", 1) not in blue["objectives"] and any(
        label == "dragons" for _, label in blue["objectives"]
    )


def test_un_joueur_inconnu_donne_une_page_sans_resultat(champions):
    view = game_view(fixture("game_detail"), "puuid-inconnu", set(), champions, NOW)
    assert view["result"] is None and not any(
        p["mine"] for t in view["teams"] for p in t["players"]
    )


def test_le_detail_calcule_les_barres_de_degats_et_les_objets(champions):
    view = game_view(fixture("game_detail"), PUUID, set(), champions, NOW)
    players = [p for team in view["teams"] for p in team["players"]]
    assert max(p["damage_percent"] for p in players) == 100
    assert all(0 not in p["build"] for p in players)  # un emplacement vide n'est pas un objet


def test_les_bans_vides_sont_omis(champions):
    detail = fixture("game_detail")
    detail["teams"][0]["bans"].append({"championId": -1, "pickTurn": 6})
    view = game_view(detail, PUUID, set(), champions, NOW)
    assert len(view["teams"][0]["bans"]) == len(fixture("game_detail")["teams"][0]["bans"])


# ---------- routes ----------


def test_route_liste(temp_db, tmp_path):
    lcu = FauxLcuNav()
    response = client(temp_db, tmp_path, lcu).get("/historique")
    assert response.status_code == 200
    assert "3 parties" in response.text and f"/historique/{GAME_ID}" in response.text
    assert "<script>alert(1)</script>" not in response.text  # nom de champion échappé
    assert "&lt;script&gt;" in response.text
    assert lcu.writes == []


def test_la_liste_demande_vingt_parties_au_plus(temp_db, tmp_path):
    lcu = FauxLcuNav()
    client(temp_db, tmp_path, lcu).get("/historique")
    assert any("endIndex=19" in call[1] for call in lcu.calls)


def test_route_liste_client_ferme(temp_db, tmp_path):
    response = client(temp_db, tmp_path, None).get("/historique")
    assert response.status_code == 200 and "Client LoL fermé" in response.text


def test_route_liste_forme_inattendue(temp_db, tmp_path):
    lcu = FauxLcuNav(
        {
            "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=19": {
                "x": 1
            }
        }
    )
    response = client(temp_db, tmp_path, lcu).get("/historique")
    assert response.status_code == 200 and "ne répond pas" in response.text


def test_route_detail(temp_db, tmp_path):
    response = client(temp_db, tmp_path, FauxLcuNav()).get(f"/historique/{GAME_ID}")
    assert response.status_code == 200
    assert (
        "Victoire" in response.text
        and "Équipe rouge" in response.text
        and "Joueur1#EUW" in response.text
    )
    assert "/parties/" not in response.text  # pas capturée : pas de lien d'analyse


def test_route_detail_partie_inconnue_du_client(temp_db, tmp_path):
    response = client(temp_db, tmp_path, FauxLcuNav()).get("/historique/42")
    assert response.status_code == 200 and "ne répond pas" in response.text


def test_la_partie_capturee_renvoie_vers_son_analyse(db, temp_db, tmp_path):
    db.insert_game_record(
        game_id=GAME_ID,
        queue_id=420,
        game_creation_utc="2026-10-05 16:00:00",
        duration_s=1647,
        player_participant_id=6,
        raw_game=json.dumps({"participants": []}),
        raw_timeline=None,
        raw_eog=None,
    )
    assert CoachingRepository(db).captured_game_ids() == {GAME_ID}
    web = client(temp_db, tmp_path, FauxLcuNav())
    assert f"/parties/{GAME_ID}" in web.get(f"/historique/{GAME_ID}").text
    assert "Capturée" in web.get("/historique").text


def test_historique_sur_base_vide_sans_lcu_ni_erreur(temp_db, tmp_path):
    web = client(temp_db, tmp_path, FauxLcuNav())
    assert web.get("/historique").status_code == 200  # tables du coaching absentes ou vides


# ---------- liste blanche ----------


def test_lectures_de_l_historique_autorisees_et_ecriture_refusee():
    proxy = LcuProxy(FauxLcuNav())
    assert proxy.get(
        "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=19"
    )
    assert proxy.get(f"/lol-match-history/v1/games/{GAME_ID}")
    with pytest.raises(ForbiddenEndpoint):
        proxy.get("/lol-match-history/v1/games/abc")
    with pytest.raises(ForbiddenEndpoint):
        proxy.send("DELETE", f"/lol-match-history/v1/games/{GAME_ID}")
