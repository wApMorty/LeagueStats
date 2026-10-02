"""Overlay de win chance (SPEC-20 tâche 47, src/winprob/overlay.py). Hermétiques : instantané
du spike, Live Client API simulée ; la fenêtre est créée hors écran et détruite aussitôt."""

import json
import queue
import threading
import tkinter
from pathlib import Path

import pytest

from src.winprob import live, overlay
from src.winprob.overlay import Overlay, Tracker, poll, text
from tests.test_winprob_impact import _model

FIXTURES = Path(__file__).parent / "fixtures" / "spike_live"
SNAPSHOT = json.loads((FIXTURES / "snapshot.json").read_text(encoding="utf-8"))


def _as(snapshot, name):
    """Instantané où le joueur actif est `name` (summonerName d'un joueur de la partie)."""
    return {**snapshot, "activePlayer": {"summonerName": name}}


def _blue_and_red_names():
    players = SNAPSHOT["allPlayers"]
    blue = next(p["summonerName"] for p in players if p["team"] == "ORDER")
    red = next(p["summonerName"] for p in players if p["team"] == "CHAOS")
    return blue, red


def test_tracker_shows_the_win_chance_of_the_players_team():
    blue, red = _blue_and_red_names()
    as_blue = Tracker(_model()).update(_as(SNAPSHOT, blue))["p"]
    as_red = Tracker(_model()).update(_as(SNAPSHOT, red))["p"]
    assert as_blue == pytest.approx(1 - as_red)
    assert as_blue == pytest.approx(_model().predict(live.state_from_live(SNAPSHOT)))


def test_unknown_active_player_defaults_to_blue_point_of_view():
    blue, _ = _blue_and_red_names()
    assert Tracker(_model()).update({**SNAPSHOT})["p"] == pytest.approx(
        Tracker(_model()).update(_as(SNAPSHOT, blue))["p"]
    )


def test_delta_compares_with_the_oldest_point_of_the_last_minute():
    tracker, blue = Tracker(_model()), _blue_and_red_names()[0]
    first = tracker.update(_as(SNAPSHOT, blue))
    assert first["delta"] == 0
    later = json.loads(json.dumps(SNAPSHOT))
    later["gameData"]["gameTime"] += 30
    later["events"]["Events"].append(
        {"EventName": "ChampionKill", "EventTime": later["gameData"]["gameTime"] - 1,
         "KillerName": blue, "VictimName": _blue_and_red_names()[1], "Assisters": []}
    )  # fmt: skip
    second = tracker.update(_as(later, blue))
    assert second["delta"] == pytest.approx(second["p"] - first["p"]) and second["delta"] != 0
    far = json.loads(json.dumps(later))
    far["gameData"][
        "gameTime"
    ] += 600  # bien plus d'une minute plus tard : les points anciens sortent
    assert len(tracker.history) == 2
    tracker.update(_as(far, blue))
    assert len(tracker.history) == 1


def test_text_formats_percentage_and_signed_points():
    assert text({"p": 0.634, "delta": -0.041}) == "Win chance 63%  (-4 pts / min)"


def test_poll_signals_the_end_after_the_grace_period(monkeypatch):
    answers = iter([SNAPSHOT] + [None] * 20)
    monkeypatch.setattr(live, "fetch", lambda: next(answers))
    monkeypatch.setattr(overlay.cfg, "OVERLAY_POLL_S", 0.0)
    out = queue.Queue()
    poll(Tracker(_model()), out, threading.Event())
    items = []
    while not out.empty():
        items.append(out.get())
    assert items[0]["p"] and items[-1] is None


def test_poll_waits_quietly_without_a_game(monkeypatch):
    stop = threading.Event()
    calls = []

    def fetch():
        calls.append(1)
        if len(calls) >= 3:
            stop.set()

    monkeypatch.setattr(live, "fetch", fetch)
    monkeypatch.setattr(overlay.cfg, "OVERLAY_POLL_S", 0.0)
    out = queue.Queue()
    poll(Tracker(_model()), out, stop)
    assert out.empty() and len(calls) == 3


def test_window_shows_the_latest_message_and_closes_at_the_end():
    try:
        window = Overlay(queue.Queue(), x=10_000, y=10_000)
    except Exception as e:  # pas d'affichage (CI sans écran)
        pytest.skip(f"tkinter indisponible : {e}")
    try:
        window.source.put({"p": 0.5, "delta": 0.0})
        window.source.put({"p": 0.7, "delta": 0.02})
        window.refresh()
        assert window.label.cget("text") == "Win chance 70%  (+2 pts / min)"
        window.source.put(None)
        window.refresh()
        with pytest.raises(tkinter.TclError):  # détruite : la fenêtre n'existe plus
            window.root.winfo_exists()
    finally:
        try:
            window.root.destroy()
        except Exception:
            pass
