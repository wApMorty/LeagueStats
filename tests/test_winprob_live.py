"""État de partie depuis la Live Client API (SPEC-20 tâche 47, src/winprob/live.py).

Hermétiques : un instantané réel du spike du 2026-10-02 (partie de 27 min, pseudos remplacés,
champs réduits à ceux que lit `live.py`) et la timeline LCU de la même partie.
"""

import json
from pathlib import Path

import pytest

from src.winprob import live
from src.winprob.state import BLUE, FEATURES, RED, walk
from tests.test_winprob_impact import _model

FIXTURES = Path(__file__).parent / "fixtures" / "spike_live"
SNAPSHOT = json.loads((FIXTURES / "snapshot.json").read_text(encoding="utf-8"))
GAME = json.loads((FIXTURES / "game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "timeline.json").read_text(encoding="utf-8"))
COUNTERS = ("kills", "towers", "inhibitors", "dragons", "soul", "herald", "grubs", "baron", "elder")


def _timeline_state_at(t_ms):
    """Dernier état après un événement suivi, à t_ms au plus."""
    return [s for t, e, s in walk(GAME, TIMELINE) if e is not None and t <= t_ms][-1]


def test_live_counters_match_the_timeline_of_the_same_game():
    state = live.state_from_live(SNAPSHOT)
    expected = _timeline_state_at(SNAPSHOT["gameData"]["gameTime"] * 1000)
    assert {k: state[k] for k in COUNTERS} == {k: expected[k] for k in COUNTERS}
    assert state["kills"] != 0 and state["towers"] != 0  # le test compare bien quelque chose


def test_live_state_has_every_model_feature_and_a_valid_win_chance():
    state = live.state_from_live(SNAPSHOT)
    assert set(FEATURES) <= set(state) and "gold" not in state  # l'API ne sert pas l'or
    assert 0 < _model().predict(state) < 1


def test_dead_players_come_from_the_live_fields_not_a_guess():
    players = SNAPSHOT["allPlayers"]
    dead = {team: sum(p["isDead"] for p in players if p["team"] == team) for team in live.TEAMS}
    remaining = {
        team: sum(p["respawnTimer"] for p in players if p["team"] == team and p["isDead"])
        for team in live.TEAMS
    }
    state = live.state_from_live(SNAPSHOT)
    assert state["dead"] == dead["ORDER"] - dead["CHAOS"]
    assert state["dead_s"] == pytest.approx(remaining["ORDER"] - remaining["CHAOS"])


def test_events_naming_a_player_by_any_form_are_attributed():
    snapshot = json.loads(json.dumps(SNAPSHOT))
    for p in snapshot["allPlayers"]:  # un joueur dont seul riotIdGameName correspond aux événements
        p["summonerName"] = p["riotId"] = "autre-forme-" + p["summonerName"]
    state = live.state_from_live(snapshot)
    assert state["kills"] == live.state_from_live(SNAPSHOT)["kills"]


def test_untracked_and_unknown_events_are_ignored():
    snapshot = json.loads(json.dumps(SNAPSHOT))
    snapshot["events"]["Events"] += [
        {"EventName": "Ace", "EventTime": 1.0, "Acer": "x", "AcingTeam": "ORDER"},
        {
            "EventName": "ChampionKill",
            "EventTime": 2.0,
            "KillerName": "Minion_T100",
            "VictimName": "inconnu",
        },
    ]
    assert live.state_from_live(snapshot) == live.state_from_live(SNAPSHOT)


def test_fetch_returns_none_without_a_game(monkeypatch):
    def refuse(*args, **kwargs):
        raise ConnectionRefusedError

    monkeypatch.setattr(live.urllib.request, "urlopen", refuse)
    assert live.fetch() is None
