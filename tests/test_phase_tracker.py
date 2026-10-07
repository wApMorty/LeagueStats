"""SPEC-25 tâche 113 : `PhaseTracker`, la phase gameflow par événement avec sondage de rattrapage.

Fausse horloge, faux bus ou `EventBus` réel, faux lecteur : rien ne touche le client LoL. Les
fixtures sont le relevé réel du 2026-10-07 (`tests/fixtures/lcu_endgame/`).
"""

import json
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.client.bus import EventBus
from src.config_constants import draft_config
from src.draft import phase_tracker
from src.draft.phase_tracker import PHASE_URI, TOPIC, PhaseTracker, kind_of

FIXTURES = Path(__file__).parent / "fixtures" / "lcu_endgame"


class Clock:
    def __init__(self, now: float = 100.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def event(phase, uri=PHASE_URI):
    return ("lcu", {"uri": uri, "eventType": "Update", "data": phase})


def make(read=lambda: None, bus=None):
    clock = Clock()
    return PhaseTracker(read, bus=bus, clock=clock), clock


def wait_for(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


@pytest.mark.parametrize(
    "phase, kind",
    [
        (None, "closed"),
        ("None", "idle"),
        ("Lobby", "idle"),
        ("Matchmaking", "queue"),
        ("ReadyCheck", "queue"),
        ("ChampSelect", "draft"),
        ("GameStart", "game"),
        ("InProgress", "game"),
        ("Reconnect", "game"),
        ("WaitingForStats", "post"),
        ("PreEndOfGame", "post"),
        ("EndOfGame", "post"),
        ("FailedToLaunch", "error"),
        ("TerminatedInError", "error"),
        ("PhaseDeDemain", "unknown"),
    ],
)
def test_chaque_phase_du_lcu_a_une_famille(phase, kind):
    assert kind_of(phase) == kind


def test_la_famille_post_vient_de_outcome_trigger_phases():
    assert all(kind_of(p) == "post" for p in draft_config.OUTCOME_TRIGGER_PHASES)
    assert not set(draft_config.PHASE_KINDS.values()) & {"post", "closed", "unknown"}


def test_un_evenement_notifie_et_publie_sans_attendre_un_sondage():
    bus = Mock()
    read = Mock(return_value=None)
    tracker, clock = make(read, bus)
    changes = []
    tracker.subscribe(lambda old, new, kind: changes.append((old, new, kind)))
    tracker._on_event(event("ChampSelect"))
    assert (tracker.phase, tracker.kind) == ("ChampSelect", "draft")
    assert changes == [(None, "ChampSelect", "draft")]
    topic, payload = bus.publish.call_args.args
    assert topic == TOPIC
    assert (payload["phase"], payload["kind"]) == ("ChampSelect", "draft")
    assert payload["since"] == pytest.approx(time.time(), abs=5)
    read.assert_not_called()


def test_seul_l_evenement_de_phase_compte():
    tracker, _ = make()
    tracker._on_event(event("ChampSelect", uri="/lol-gameflow/v1/session"))
    tracker._on_event(event({"phase": "ChampSelect"}))  # pas une chaîne
    tracker._on_event(("lcu", None))
    assert tracker.phase is None


def test_le_sondage_rattrape_un_evenement_manque():
    tracker, _ = make(lambda: "InProgress")
    tracker.poll_once()
    assert (tracker.phase, tracker.kind) == ("InProgress", "game")


def test_une_meme_phase_lue_deux_fois_ne_notifie_pas():
    tracker, _ = make(lambda: "Lobby")
    changes = []
    tracker.subscribe(lambda *args: changes.append(args))
    tracker._on_event(event("Lobby"))
    tracker.poll_once()
    tracker._on_event(event("Lobby"))
    assert len(changes) == 1


def test_un_rappel_qui_leve_n_arrete_ni_le_tracker_ni_les_autres():
    bus = Mock()
    tracker, _ = make(bus=bus)
    seen = []
    tracker.subscribe(Mock(side_effect=RuntimeError("boum")))
    tracker.subscribe(lambda old, new, kind: seen.append(new))
    tracker._on_event(event("Lobby"))
    tracker._on_event(event("Matchmaking"))
    assert seen == ["Lobby", "Matchmaking"]
    assert tracker.phase == "Matchmaking"


def test_un_lecteur_qui_leve_vaut_un_sondage_sans_reponse():
    tracker, _ = make(Mock(side_effect=OSError("client fermé")))
    tracker._on_event(event("ChampSelect"))
    tracker.poll_once()
    assert tracker.phase == "ChampSelect"


def test_un_sondage_rate_n_efface_la_phase_qu_apres_phase_stale_s():
    tracker, clock = make()
    changes = []
    tracker._on_event(event("ChampSelect"))
    tracker.subscribe(lambda old, new, kind: changes.append((new, kind)))
    clock.now += draft_config.PHASE_STALE_S - 1
    tracker.poll_once()
    assert tracker.phase == "ChampSelect"
    clock.now += 2
    tracker.poll_once()
    assert tracker.phase is None
    assert changes == [(None, "closed")]


def test_un_evenement_apres_un_silence_reprend_le_suivi():
    tracker, clock = make()
    tracker._on_event(event("ChampSelect"))
    clock.now += draft_config.PHASE_STALE_S + 1
    tracker.poll_once()
    assert tracker.phase is None
    tracker._on_event(event("ChampSelect"))  # le WebSocket reprend
    assert (tracker.phase, tracker.kind) == ("ChampSelect", "draft")


def test_phase_inconnue_journalisee_une_fois(capsys):
    tracker, _ = make()
    tracker._on_event(event("Nouvelle"))
    tracker._on_event(event("Autre"))
    tracker._on_event(event("Nouvelle"))
    out = capsys.readouterr().out
    assert out.count("[INFO] Phase gameflow inconnue : Nouvelle") == 1
    assert tracker.kind == "unknown"


def test_since_compte_les_secondes_dans_la_phase():
    tracker, clock = make()
    tracker._on_event(event("EndOfGame"))
    clock.now += 12.5
    assert tracker.since() == pytest.approx(12.5)
    tracker._on_event(event("None"))
    assert tracker.since() == pytest.approx(0.0)


def test_rejeu_de_la_fin_de_partie_reelle():
    """La suite d'événements du relevé du 2026-10-07 : une partie, de la file à la sortie."""
    tracker, clock = make()
    changes = []
    tracker.subscribe(lambda old, new, kind: changes.append((new, kind)))
    for row in json.loads((FIXTURES / "gameflow_events.json").read_text(encoding="utf-8")):
        clock.now = 100.0 + row["t"]
        tracker._on_event(event(row["phase"]))
    kinds = [kind for _, kind in changes]
    assert kinds == ["queue"] * 3 + ["draft"] + ["game"] * 3 + ["post"] * 3 + ["idle"]
    assert [phase for phase, _ in changes[-4:]] == [
        "WaitingForStats",
        "PreEndOfGame",
        "EndOfGame",
        "None",
    ]


def test_le_fil_suit_les_evenements_du_bus_sans_attendre_le_sondage(monkeypatch):
    monkeypatch.setattr(draft_config, "PHASE_POLL_S", 30.0)  # le rattrapage ne passe plus
    bus = EventBus()
    tracker = PhaseTracker(lambda: None, bus=bus)
    topic_seen = bus.subscribe([TOPIC])
    tracker.start()
    try:
        assert wait_for(lambda: tracker._thread.is_alive())
        time.sleep(0.1)  # le fil a fait son premier sondage et attend sur le bus
        bus.publish("lcu", event("ReadyCheck")[1])
        assert wait_for(lambda: tracker.phase == "ReadyCheck")
        assert topic_seen.get(1.0)[1]["kind"] == "queue"
    finally:
        tracker.stop()


def test_sans_bus_le_sondage_seul_suit_la_phase_et_cadence_la_fin_de_partie(monkeypatch):
    monkeypatch.setattr(draft_config, "PHASE_POLL_S", 0.02)
    monkeypatch.setattr(draft_config, "PHASE_POST_POLL_S", 0.01)
    phases = iter(["ChampSelect", "InProgress", "EndOfGame"])
    last = ["EndOfGame"]

    def read():
        last[0] = next(phases, last[0])
        return last[0]

    tracker = PhaseTracker(read)
    tracker.start()
    try:
        assert wait_for(lambda: tracker.phase == "EndOfGame")
        assert tracker.kind == "post"
    finally:
        tracker.stop()


def test_le_lecteur_ne_cherche_pas_les_identifiants_a_chaque_sondage(monkeypatch):
    lcu = Mock(credentials=None)
    lcu.find_lcu_credentials.return_value = None
    with patch.object(phase_tracker, "LCUClient", return_value=lcu):
        read = phase_tracker.lcu_phase_reader()
    assert [read(), read(), read()] == [None, None, None]
    assert lcu.find_lcu_credentials.call_count == 1  # scrute les processus : au plus 1 par délai


def test_le_lecteur_oublie_des_identifiants_perimes():
    lcu = Mock(credentials=object())
    lcu._make_request.side_effect = ["Lobby", None]
    with patch.object(phase_tracker, "LCUClient", return_value=lcu):
        read = phase_tracker.lcu_phase_reader()
    assert read() == "Lobby"
    assert read() is None
    assert lcu.credentials is None  # le client LoL a redémarré : nouveau port


def test_les_abonnes_d_evenements_recoivent_les_autres_uri_et_un_abonne_casse_ne_gene_pas():
    tracker, _ = make()
    seen = []
    tracker.subscribe_events(Mock(side_effect=RuntimeError("boum")))
    tracker.subscribe_events(seen.append)
    ranked = {"uri": "/lol-ranked/v1/current-lp-change-notification", "data": {"gameId": 1}}
    tracker._on_event(("lcu", ranked))
    tracker._on_event(event("Lobby"))  # la phase n'est pas un événement « autre »
    tracker._on_event(("lcu", None))
    assert seen == [ranked]
    assert tracker.phase == "Lobby"
