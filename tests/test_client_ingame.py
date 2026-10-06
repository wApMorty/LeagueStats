"""SPEC-24 tâche 107 : `LiveGame` lit la Live Client API et publie l'état de la partie.

Hermétique : `fetch` factice servant les fixtures de `tests/fixtures/spike_live/`, phase du client
simulée, pas de fil réel (`tick()` appelé à la main), aucun accès à data/db.db ni au client LoL.
"""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.client.bus import EventBus
from src.client.ingame import TOPIC, LiveGame, me_of, objectives_of
from src.config_client import client_config
from src.winprob import live
from src.winprob.model import fit
from src.winprob.overlay import Tracker

FIXTURES = Path(__file__).parent / "fixtures" / "spike_live"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def make_model():
    """Un modèle de la forme que `train` écrit, ajusté sur quatre images de la partie du spike."""
    return fit([live.state_from_live(load("snapshot.json"))] * 4, [1, 0, 1, 0])


class Feed:
    """`fetch` factice : sert les lectures prévues dans l'ordre, puis None."""

    def __init__(self, *reads):
        self.reads = list(reads)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.reads.pop(0) if self.reads else None


def game(feed, phase="InProgress"):
    bus = EventBus()
    phases = {"value": phase}
    live_game = LiveGame(bus, lambda: phases["value"], fetch=feed, model=make_model())
    live_game.phases = phases
    return live_game, bus


def at(snapshot, seconds):
    data = json.loads(json.dumps(snapshot))
    data["gameData"]["gameTime"] = seconds
    return data


def test_meme_probabilite_que_l_overlay():
    snapshot = load("snapshot.json")
    live_game, bus = game(Feed(snapshot))
    live_game.tick()
    payload = bus.latest(TOPIC)
    expected = Tracker(live_game._model).update(snapshot)
    assert payload["state"] == "live"
    assert payload["p"] == pytest.approx(expected["p"])
    assert payload["game_time"] == snapshot["gameData"]["gameTime"]


def test_hors_inprogress_aucune_lecture_de_l_api():
    feed = Feed(load("snapshot.json"))
    live_game, bus = game(feed, phase="ChampSelect")
    assert live_game.tick() == client_config.INGAME_IDLE_POLL_S
    live_game.tick()
    assert feed.calls == 0
    assert bus.latest(TOPIC) == {"state": "idle"}


def test_idle_n_est_publie_qu_une_fois():
    live_game, _ = game(Feed(), phase=None)
    live_game._bus = Mock()
    live_game.tick()
    live_game.tick()
    live_game._bus.publish.assert_called_once_with(TOPIC, {"state": "idle"})


def test_une_exception_du_fetch_ne_sort_pas_du_fil(capsys):
    def broken():
        raise RuntimeError("API cassée")

    live_game = LiveGame(EventBus(), lambda: "InProgress", fetch=broken, model=make_model())
    assert live_game.tick() == client_config.INGAME_POLL_S
    live_game.tick()
    assert capsys.readouterr().out.count("[INFO] Écran « En partie »") == 1  # annoncée une fois


def test_une_exception_de_la_phase_ne_sort_pas_du_fil():
    live_game = LiveGame(EventBus(), Mock(side_effect=OSError("LCU")), fetch=Feed())
    assert live_game.tick() > 0


def test_instantane_incomplet_ignore():
    live_game, bus = game(Feed({"gameData": {"gameTime": 3.0}, "allPlayers": [], "events": {}}))
    live_game.tick()  # KeyError : au suivant
    assert bus.latest(TOPIC) is None


def test_la_serie_prend_un_point_toutes_les_5_s_et_reste_bornee(monkeypatch):
    monkeypatch.setattr(client_config, "INGAME_MAX_POINTS", 4)
    snapshot = load("snapshot.json")
    times = [100, 102, 105, 110, 115, 120, 125, 130]
    live_game, bus = game(Feed(*[at(snapshot, t) for t in times]))
    for _ in times:
        live_game.tick()
    assert [t for t, _ in live_game.series] == [115, 120, 125, 130]
    assert len(bus.latest(TOPIC)["series"]) == 4


def test_un_temps_de_jeu_qui_recule_reinitialise_la_serie():
    snapshot = load("snapshot.json")
    live_game, _ = game(Feed(at(snapshot, 600), at(snapshot, 610), at(snapshot, 30)))
    for _ in range(3):
        live_game.tick()
    assert [t for t, _ in live_game.series] == [30]


def test_fin_de_partie_apres_les_lectures_vides_la_serie_est_gardee(monkeypatch):
    monkeypatch.setattr(client_config, "INGAME_GRACE_POLLS", 3)
    live_game, bus = game(Feed(at(load("snapshot.json"), 600)))
    live_game.tick()
    for _ in range(2):
        live_game.tick()
    assert bus.latest(TOPIC)["state"] == "live"
    live_game.tick()
    ended = bus.latest(TOPIC)
    assert ended["state"] == "ended" and len(ended["series"]) == 1


def test_la_phase_qui_quitte_inprogress_termine_la_partie():
    live_game, bus = game(Feed(load("snapshot.json")))
    live_game.tick()
    live_game.phases["value"] = "EndOfGame"
    live_game.tick()
    assert bus.latest(TOPIC)["state"] == "ended"
    live_game._bus = Mock()
    live_game.tick()  # pas de republication
    live_game._bus.publish.assert_not_called()


def test_sans_modele_p_est_none_et_le_reste_est_publie(monkeypatch):
    monkeypatch.setattr("src.client.ingame._load_model", lambda: None)
    bus = EventBus()
    live_game = LiveGame(bus, lambda: "InProgress", fetch=Feed(load("snapshot.json")))
    live_game.tick()
    payload = bus.latest(TOPIC)
    assert payload["state"] == "live" and payload["p"] is None and payload["series"] == []


# ---------- ce qu'on lit de la partie réelle (spike du 2026-10-07) ----------


def test_moi_objets_or_et_competences_de_la_partie_reelle():
    me = me_of(load("allgamedata_items.json"))
    assert (me["champion"], me["team"], me["position"], me["level"]) == (
        "Yorick",
        "ORDER",
        "TOP",
        13,
    )
    assert me["gold"] == pytest.approx(858.0, abs=0.1)
    assert [item["id"] for item in me["items"]][:3] == [1120, 1036, 3071]
    assert me["abilities"] == {"Q": 5, "W": 1, "E": 5, "R": 2}


def test_objectifs_avec_leur_camp():
    found = objectives_of(load("allgamedata_items.json"))
    kinds = [o["kind"] for o in found]
    assert kinds.count("dragon") == 2 and kinds.count("herald") == 1 and kinds.count("turret") == 5
    first_turret = next(o for o in found if o["kind"] == "turret")
    assert first_turret["team"] == "ORDER"  # tour Chaos tombée, prise par Joueur3 (Ordre)
    assert all(o["team"] in ("ORDER", "CHAOS") for o in found)


def test_la_partie_reelle_donne_une_probabilite_serialisable():
    live_game, bus = game(Feed(load("allgamedata_items.json")))
    live_game.tick()
    payload = bus.latest(TOPIC)
    assert 0.0 <= payload["p"] <= 1.0 and payload["me"]["champion"] == "Yorick"
    json.dumps(payload)
