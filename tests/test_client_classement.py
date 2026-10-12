"""Classement des dix joueurs par impact ΔP (SPEC-32 tâche 147) : fonctions pures, brut construit à la main."""

import json

import pytest

from src.client.assets import Assets
from src.client.classement import ranking
from src.client.draft_view import Champions
from src.config_client import client_config

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
