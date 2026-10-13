"""Forme récente et impact par fenêtre (SPEC-33 tâche 152, src/winprob/form.py). Hermétiques."""

import json
from pathlib import Path

import pytest

from src.coaching.metrics import participant_roles
from src.winprob.form import form, player_impact, ranked_games
from src.winprob.impact import impacts
from src.winprob.model import INPUTS, WinModel

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))
QUEUES = (420, 440)


def _model():
    """Modèle jouet (copie locale de tests/test_winprob_impact.py::_model)."""
    d = 2 * len(INPUTS)
    weights = [0.0] * (d + 1)
    weights[INPUTS.index("kills")] = 0.5
    weights[INPUTS.index("towers")] = 0.5
    return WinModel(INPUTS, [0.0] * d, [1.0] * d, weights)


def _entry(game_id, creation, queue=420, champion=103, win=True, kills=1, deaths=2, assists=3):
    return {
        "gameId": game_id,
        "gameCreation": creation,
        "gameDuration": 1800,
        "queueId": queue,
        "participants": [
            {
                "championId": champion,
                "stats": {
                    "win": win,
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "totalMinionsKilled": 90,
                    "neutralMinionsKilled": 12,
                },
            }
        ],
    }


def _game(game_id, win, kills, deaths, assists, cs, duration, champion=103):
    return {
        "game_id": game_id,
        "creation_ms": 0,
        "queue_id": 420,
        "champion_id": champion,
        "win": win,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "cs": cs,
        "duration_s": duration,
    }


def test_ranked_games_filters_queues_skips_malformed_and_sorts_newest_first():
    history = [
        _entry(1, 1000),
        _entry(2, 3000, queue=450),  # hors des files demandées
        _entry(3, 2000, queue=440),
        {"gameId": 4, "gameCreation": 5000, "queueId": 420},  # participants absent
        {"gameId": 5, "gameCreation": 5000, "queueId": 420, "participants": []},  # vide
        {"gameId": 6, "gameCreation": 5000, "queueId": 420, "participants": [{"championId": 1}]},
        "pas un dict",
        None,
        _entry(7, 1000),  # même instant que la 1 : l'ordre du LCU est conservé
    ]
    games = ranked_games(history, QUEUES)
    assert [g["game_id"] for g in games] == [3, 1, 7]
    assert games[0]["cs"] == 102  # sbires + monstres neutres
    assert games[0]["duration_s"] == 1800
    assert ranked_games("pas une liste", QUEUES) == []


def test_form_kda_cs_per_minute_and_champion_count():
    games = [
        _game(1, True, 5, 0, 2, 150, 1800, champion=103),
        _game(2, False, 1, 0, 0, 60, 1200, champion=64),
    ]
    f = form(games, {}, 103, 10)
    assert f["n"] == 2  # fenêtre plus grande que l'historique
    assert f["win_rate"] == 0.5
    assert f["kda"] == 8.0  # 7 / max(0, 1)
    assert f["cs_min"] == pytest.approx(210 / 50)
    assert f["on_champion"] == 1
    assert f["impact"] is None and f["impact_n"] == 0
    assert form([_game(3, True, 2, 4, 4, 0, 600)], {}, 103, 10)["kda"] == 1.5
    assert form(games, {}, 103, 1)["n"] == 1  # la fenêtre ne voit que la première partie
    assert form(games, {}, 103, 1)["on_champion"] == 1
    assert form([_game(9, True, 0, 0, 0, 0, 0)], {}, 103, 1)["cs_min"] is None
    empty = form([], {}, 103, 10)
    assert empty["n"] == 0 and empty["win_rate"] is None and empty["kda"] is None
    assert empty["cs_min"] is None and empty["on_champion"] == 0


def test_form_impact_averages_only_games_that_have_one():
    games = [
        _game(1, True, 0, 0, 0, 0, 600),
        _game(2, True, 0, 0, 0, 0, 600),
        _game(3, True, 0, 0, 0, 0, 600),
    ]
    f = form(games, {1: 2.0, 3: 4.0, 99: 9.0}, 103, 3)
    assert f["impact"] == 3.0 and f["impact_n"] == 2
    assert form(games, {1: 2.0, 3: 4.0}, 103, 1)["impact"] == 2.0
    none = form(games, {99: 1.0}, 103, 3)
    assert none["impact"] is None and none["impact_n"] == 0


def _puuid(pid):
    return next(
        i["player"]["puuid"] for i in GAME["participantIdentities"] if i["participantId"] == pid
    )


def test_player_impact_is_100_times_the_participant_rows_sum():
    rows = impacts(_model(), GAME, TIMELINE, participant_roles(GAME))["rows"]
    expected = 100 * sum(r["delta_p"] for r in rows if r["participant_id"] == 7)
    assert expected != 0
    assert player_impact(_model(), GAME, TIMELINE, _puuid(7)) == pytest.approx(expected)


def test_player_impact_is_none_for_unknown_puuid_or_without_frames():
    assert player_impact(_model(), GAME, TIMELINE, "absent") is None
    assert player_impact(_model(), GAME, {"frames": []}, _puuid(7)) is None
    assert player_impact(_model(), GAME, {}, _puuid(7)) is None
    assert player_impact(_model(), GAME, None, _puuid(7)) is None
