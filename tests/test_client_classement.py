"""Classement des dix joueurs par impact ΔP (SPEC-32 tâche 147) : fonctions pures, brut construit à la main."""

import json
import re
from datetime import datetime, timezone

import pytest

from src.client.assets import Assets
from src.client.classement import ranking
from src.client.draft_view import Champions
from src.client.review import game_page
from src.config_client import client_config
from src.repositories.coaching import CoachingRepository
from tests.test_client_parties import (  # noqa: F401 (fixture modele)
    capture,
    client,
    impact,
    modele,
    roles,
)

CHAMPIONS = {
    "data": {
        f"Champ{key}": {"key": str(key), "id": f"Champ{key}", "name": f"Champion {key}", "tags": []}
        for key in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10)
    }
}
ROLES = {1: "top", 2: "jungle", 3: "middle", 4: "bottom", 5: "support"}


@pytest.fixture
def champions(tmp_path):
    base = client_config.DDRAGON_BASE
    files = {
        f"{base}/api/versions.json": json.dumps(["16.2.1"]).encode(),
        f"{base}/cdn/16.2.1/data/fr_FR/champion.json": json.dumps(CHAMPIONS).encode(),
    }
    return Champions(Assets(tmp_path / "cache", fetch=files.get))


def game(win_blue=True, win_red=None):
    """Dix participants : 1 à 5 en bleue (100), 6 à 10 en rouge (200)."""
    if win_red is None:
        win_red = not win_blue
    participants = []
    for participant_id in range(1, 11):
        blue = participant_id <= 5
        participants.append(
            {
                "participantId": participant_id,
                "teamId": 100 if blue else 200,
                "championId": participant_id,
                "stats": {
                    "win": win_blue if blue else win_red,
                    "kills": participant_id,
                    "deaths": 2,
                    "assists": 3,
                },
            }
        )
    return {"participants": participants}


def rows(deltas):
    """Une ligne d'impact par joueur, `deltas` : {participant_id: delta_p}."""
    return [{"participant_id": pid, "delta_p": delta} for pid, delta in deltas.items()]


def players(result, team_index):
    return result["teams"][team_index]["players"]


def test_chaque_equipe_de_cinq_classee_par_delta_decroissant(champions):
    deltas = {
        1: 0.02,
        2: 0.10,
        3: -0.01,
        4: 0.05,
        5: 0.00,
        6: -0.04,
        7: -0.20,
        8: 0.01,
        9: -0.08,
        10: -0.02,
    }
    result = ranking(rows(deltas), game(), ROLES, 1, champions)
    for team in result["teams"]:
        assert len(team["players"]) == 5
        impacts = [player["impact"] for player in team["players"]]
        assert impacts == sorted(impacts, reverse=True)
        assert [player["rank"] for player in team["players"]] == [1, 2, 3, 4, 5]


def test_mvp_sur_le_numero_un_gagnant_et_ace_sur_le_numero_un_perdant(champions):
    deltas = {2: 0.10, 4: 0.05, 7: -0.02, 8: -0.20, 9: -0.05}
    result = ranking(rows(deltas), game(win_blue=True), ROLES, 1, champions)
    blue, red = result["teams"]
    assert blue["win"] is True and red["win"] is False
    assert players(result, 0)[0]["pid"] == 2 and players(result, 0)[0]["badge"] == "MVP"
    assert players(result, 1)[0]["pid"] == 6  # 6 et 10 à 0.0 sans ligne : 6 d'abord
    assert [p["badge"] for p in red["players"]].count("ACE") == 1


def test_ace_couronne_meme_a_impact_negatif(champions):
    deltas = {6: -0.03, 7: -0.10, 8: -0.20, 9: -0.05, 10: -0.07}
    result = ranking(rows(deltas), game(win_blue=True), ROLES, 1, champions)
    red_top = players(result, 1)[0]
    assert red_top["pid"] == 6 and red_top["impact"] == pytest.approx(-0.03)
    assert red_top["badge"] == "ACE"
    ace = [p for team in result["teams"] for p in team["players"] if p["badge"] == "ACE"]
    assert [p["pid"] for p in ace] == [6]
    assert sum(p["badge"] == "MVP" for team in result["teams"] for p in team["players"]) == 1


def test_ex_aequo_departages_par_participant_id(champions):
    deltas = {3: 0.05, 2: 0.05, 1: 0.05}
    result = ranking(rows(deltas), game(), ROLES, 1, champions)
    assert [p["pid"] for p in players(result, 0)[:3]] == [1, 2, 3]


def test_participant_sans_ligne_vaut_zero_et_reste_present(champions):
    result = ranking(rows({1: 0.04, 2: -0.01}), game(), ROLES, 1, champions)
    blue = {p["pid"]: p for p in players(result, 0)}
    assert blue[3]["impact"] == 0.0 and blue[3]["rank"] == 2
    assert len(players(result, 0)) == 5


def test_lignes_d_un_meme_joueur_sont_sommees(champions):
    result = ranking(rows({1: 0.03}) + rows({1: 0.02, 2: 0.01}), game(), ROLES, 1, champions)
    assert players(result, 0)[0]["pid"] == 1
    assert players(result, 0)[0]["impact"] == pytest.approx(0.05)


def test_remake_sans_badge(champions):
    deltas = {1: 0.05, 6: -0.05}
    result = ranking(rows(deltas), game(win_blue=False, win_red=False), ROLES, 1, champions)
    assert all(p["badge"] is None for team in result["teams"] for p in team["players"])


def test_rows_vides_donne_none(champions):
    assert ranking([], game(), ROLES, 1, champions) is None


def test_brut_sans_participants_donne_none(champions):
    assert ranking(rows({1: 0.05}), {}, ROLES, 1, champions) is None


def test_ligne_sans_delta_donne_none(champions):
    assert ranking([{"participant_id": 1}], game(), ROLES, 1, champions) is None


def test_equipe_du_joueur_en_premier_meme_perdante(champions):
    result = ranking(rows({1: 0.05, 6: 0.10}), game(win_blue=False), ROLES, 1, champions)
    assert result["teams"][0]["mine"] is True and result["teams"][0]["win"] is False
    assert result["teams"][1]["mine"] is False
    assert [p["me"] for p in players(result, 0)].count(True) == 1


def test_role_nom_portrait_et_kda(champions):
    result = ranking(rows({1: 0.05}), game(), ROLES, 1, champions)
    top = players(result, 0)[0]
    assert top["pid"] == 1 and top["me"] is True
    assert top["role"] == "Top"
    assert top["champion"] == "Champion 1"
    assert top["portrait"] == "/assets/champion/Champ1.png"
    assert top["kda"] == "1 / 2 / 3"


# ---------- pages (tâche 148 : clé `ranking` de `game_page`) ----------

GAME_ID = 7998195590
NOW = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
FR_POINTS = re.compile(r"[+−]\d+,\d|0,0")
PAGE_CHAMPIONS = {
    "data": {
        cid: {"key": str(key), "id": cid, "name": label, "tags": []}
        for key, cid, label in [
            (2, "Olaf", "Olaf"),
            (57, "Maokai", "Maokai"),
            (4, "TwistedFate", "Twisted Fate"),
            (236, "Lucian", "Lucian"),
            (412, "Thresh", "Thresh"),
            (240, "Kled", "Kled"),
            (141, "Kayn", "Kayn"),
            (45, "Veigar", "Veigar"),
            (804, "Yunara", "Yunara"),
            (117, "Lulu", "Lulu"),
        ]
    }
}


@pytest.fixture
def assets(tmp_path):
    base = client_config.DDRAGON_BASE
    files = {
        f"{base}/api/versions.json": json.dumps(["16.2.1"]).encode(),
        f"{base}/cdn/16.2.1/data/fr_FR/champion.json": json.dumps(PAGE_CHAMPIONS).encode(),
    }
    return Assets(tmp_path / "cache", fetch=files.get)


def _page(db, assets, model):
    return game_page(CoachingRepository(db), GAME_ID, Champions(assets), model, NOW)


def test_page_classe_dix_joueurs_en_deux_equipes_de_cinq(db, assets, modele):
    capture(db, pid=1)
    roles(db, GAME_ID)
    impact(db)
    ranking_view = _page(db, assets, modele)["ranking"]
    assert [len(team["players"]) for team in ranking_view["teams"]] == [5, 5]
    assert ranking_view["teams"][0]["mine"] is True
    for player in (p for team in ranking_view["teams"] for p in team["players"]):
        assert FR_POINTS.fullmatch(player["impact_text"]), player["impact_text"]
        assert player["tone"] == ("gain" if player["impact"] >= 0 else "cost")


def test_barres_sur_une_echelle_commune_le_plus_grand_ecart_remplit_la_moitie(db, assets, modele):
    capture(db, pid=1)
    roles(db, GAME_ID)
    impact(db)
    ranking_view = _page(db, assets, modele)["ranking"]
    players = [p for team in ranking_view["teams"] for p in team["players"]]
    biggest = max(players, key=lambda p: abs(p["impact"]))
    scale = abs(biggest["impact"])
    assert scale > 0 and biggest["width"] == 50
    for player in players:
        expected = min(50, abs(player["impact"]) / scale * 50)
        assert player["width"] == pytest.approx(expected, abs=0.06)
        if player["impact"] >= 0:
            assert player["left"] == 50
        else:
            assert player["left"] == pytest.approx(50 - player["width"], abs=0.06)


def test_sans_impact_pas_de_classement_et_notes_inchangees(db, assets, modele):
    capture(db, pid=1)
    page = _page(db, assets, modele)
    assert page["ranking"] is None
    assert page["curve"] and page["curve_note"] is None
    assert page["impact_note"] == "Impact non calculé pour cette partie."


def test_sans_timeline_pas_de_classement_meme_avec_impact_stocke(db, assets, modele):
    capture(db, pid=1, timeline=False)
    impact(db)
    page = _page(db, assets, modele)
    assert page["ranking"] is None
    assert page["curve_note"].startswith("Pas de timeline")
    assert page["impact_note"] is None


# ---------- rendu (tâche 149 : panneau « Classement de la partie ») ----------


@pytest.mark.parametrize("url", ["/postgame", f"/parties/{GAME_ID}"])
def test_panneau_dix_portraits_un_mvp_un_ace_une_ligne_toi(db, temp_db, assets, modele, url):
    capture(db, pid=1)
    roles(db, GAME_ID)
    impact(db)
    html = client(temp_db, assets).get(url).text
    assert "Classement de la partie" in html
    assert len(re.findall(r'<img class="rank-champ" src="/assets/champion/\w+\.png"', html)) == 10
    assert html.count('aria-label="MVP de la partie"') == 1
    assert html.count('aria-label="ACE de la partie"') == 1
    assert html.count("rank-row ") == 10 and html.count(" is-me") == 1
    assert html.count("<em>toi</em></b>") == 1


def test_panneau_defaite_equipe_du_joueur_a_gauche_avec_l_ace(db, temp_db, assets, modele):
    capture(db, pid=6)
    roles(db, GAME_ID)
    impact(db)
    html = client(temp_db, assets).get(f"/parties/{GAME_ID}").text
    first, second = html.split('<div class="rank-team ')[1:3]
    assert first.startswith("loss") and "Ton équipe · Défaite" in first
    assert 'aria-label="ACE de la partie"' in first and "MVP" not in first.split("<img")[0]
    assert second.startswith("win") and 'aria-label="MVP de la partie"' in second


@pytest.mark.parametrize("timeline", [True, False])
def test_sans_impact_ou_sans_timeline_le_panneau_est_absent(db, temp_db, assets, modele, timeline):
    capture(db, pid=1, timeline=timeline)
    if not timeline:
        impact(db)
    response = client(temp_db, assets).get(f"/parties/{GAME_ID}")
    assert response.status_code == 200
    assert "Classement de la partie" not in response.text
