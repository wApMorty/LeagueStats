"""SPEC-25 tâche 112 : `dump_lcu_endgame.py` relève événements et sondages, identités retirées.

Faux LCU, horloge et répertoire temporaires : rien ne touche le vrai client ni `outputs/`.
"""

import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

SCRIPT = Path(__file__).parent.parent / "scripts" / "dump_lcu_endgame.py"
spec = importlib.util.spec_from_file_location("dump_lcu_endgame", SCRIPT)
dump = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dump)


def fake_lcu(responses):
    """``responses`` : endpoint -> liste de réponses successives (la dernière se répète)."""
    lcu = Mock()
    counters = {}

    def request(endpoint):
        queue = responses.get(endpoint) or [None]
        index = counters.get(endpoint, 0)
        counters[endpoint] = index + 1
        return queue[min(index, len(queue) - 1)]

    lcu._make_request.side_effect = request
    return lcu


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        self.now += 0.25
        return self.now


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_sondage_note_phases_et_premiere_reponse_anonymisee(tmp_path):
    lcu = fake_lcu(
        {
            dump.PHASE_ENDPOINT: ["InProgress", "EndOfGame", "EndOfGame", "Lobby"],
            dump.TRANSIENTS["eog_stats_block"]: [{}, {"gameId": 7, "summonerName": "Moi"}, {}],
            dump.TRANSIENTS["lp_change_notification"]: [{}, {"lpDelta": 19}, {}],
        }
    )
    recorder = dump.Recorder(tmp_path, clock=Clock())
    dump.watch(lcu, recorder, ticks=4, sleep=lambda _: None)
    polls = rows(tmp_path / "polls.jsonl")
    assert [p["phase"] for p in polls] == ["InProgress", "EndOfGame", "EndOfGame", "Lobby"]
    assert [p["eog_stats_block"]["filled"] for p in polls] == [False, True, False, False]
    first = (tmp_path / "first_eog_stats_block.json").read_text(encoding="utf-8")
    assert '"gameId": 7' in first and "Moi" not in first
    assert [phase for _, phase in recorder.phases] == ["InProgress", "EndOfGame", "Lobby"]
    assert "1 lectures non vides" in recorder.summary()


def test_evenements_filtres_par_prefixe_et_anonymises(tmp_path):
    recorder = dump.Recorder(tmp_path, clock=Clock())
    recorder.publish(
        "lcu", {"uri": dump.PHASE_ENDPOINT, "eventType": "Update", "data": "PreEndOfGame"}
    )
    recorder.publish("lcu", {"uri": "/lol-chat/v1/me", "eventType": "Update", "data": {}})
    recorder.publish(
        "lcu", {"uri": "/lol-ranked/v1/x", "data": {"puuid": "secret", "tier": "GOLD"}}
    )
    events = rows(tmp_path / "events.jsonl")
    assert [e["uri"] for e in events] == [dump.PHASE_ENDPOINT, "/lol-ranked/v1/x"]
    assert events[1]["data"] == {"puuid": "anon", "tier": "GOLD"}
    assert recorder.phases[0][1] == "PreEndOfGame"


FIXTURES = Path(__file__).parent / "fixtures" / "lcu_endgame"


def test_fixtures_du_spike_sans_identite_ni_jeton():
    """Le relevé réel du 2026-10-07 : ni nom, ni puuid, ni jeton du salon de fin de partie."""
    block = json.loads((FIXTURES / "eog_stats_block.json").read_text(encoding="utf-8"))
    for player in (p for team in block["teams"] for p in team["players"]):
        assert {player["puuid"], player["summonerName"], player["riotIdGameName"]} == {"anon"}
    assert block["mucJwtDto"]["jwt"] == block["multiUserChatPassword"] == "anon"
    notification = json.loads((FIXTURES / "lp_change_notification.json").read_text("utf-8"))
    assert notification["gameId"] == block["gameId"]
    phases = [
        e["phase"] for e in json.loads((FIXTURES / "gameflow_events.json").read_text("utf-8"))
    ]
    assert phases[-5:] == ["Reconnect", "WaitingForStats", "PreEndOfGame", "EndOfGame", "None"]
