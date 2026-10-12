"""État de partie de la win chance (SPEC-20 tâche 41, src/winprob/state.py).

Hermétiques : fixtures anonymisées du spike du 2026-09-28 (24 min 48, bleu gagne).
"""

import json
from pathlib import Path

import pytest

from src.winprob.state import FEATURES, _respawn_s, blue_win, frame_states, to_vector, walk

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))


def _mini(events, frames=2):
    """Partie minimale : 10 joueurs, `frames` images vides, événements dans la dernière."""
    game = {
        "participants": [
            {"participantId": i, "teamId": 100 if i <= 5 else 200} for i in range(1, 11)
        ]
    }
    pf = {
        str(i): {"level": 6, "minionsKilled": 10, "jungleMinionsKilled": 0, "totalGold": 0}
        for i in range(1, 11)
    }
    timeline = {
        "frames": [
            {"timestamp": 60000 * n, "events": [], "participantFrames": pf} for n in range(frames)
        ]
    }
    timeline["frames"][-1]["events"] = events
    return game, timeline


def _event(kind, timestamp, killer=0, victim=0, **extra):
    base = {"buildingType": "", "monsterType": "", "monsterSubType": "", "teamId": 0}
    return {
        "type": kind,
        "timestamp": timestamp,
        "killerId": killer,
        "victimId": victim,
        **base,
        **extra,
    }


def test_final_state_matches_team_totals():
    final = frame_states(GAME, TIMELINE)[-1]
    # Totaux d'équipe du détail de la partie : bleu 11 tours, 2 inhibiteurs, 3 dragons, rouge 2 tours.
    assert (final["towers"], final["inhibitors"], final["dragons"]) == (9, 2, 3)
    assert (final["herald"], final["grubs"]) == (1, 3)
    kills = sum(1 for f in TIMELINE["frames"] for e in f["events"] if e["type"] == "CHAMPION_KILL")
    assert abs(final["kills"]) <= kills and final["kills"] > 0


def test_frames_have_every_feature_and_label():
    states = frame_states(GAME, TIMELINE)
    assert len(states) == len(TIMELINE["frames"])
    assert all(set(FEATURES) <= set(s) for s in states)
    assert len(to_vector(states[0])) == len(FEATURES)
    assert states[0]["kills"] == 0 and blue_win(GAME) is True


def test_events_come_in_time_order_with_state_after_each():
    walked = list(walk(GAME, TIMELINE))
    events = [(t, s) for t, e, s in walked if e is not None]
    assert [t for t, _ in events] == sorted(t for t, _ in events)
    first_kill = next(s for t, e, s in walked if e is not None and e["type"] == "CHAMPION_KILL")
    assert abs(first_kill["kills"]) == 1


def test_building_kill_credits_the_other_team():
    # Tour rouge (teamId 200) détruite : avantage bleu.
    game, tl = _mini([_event("BUILDING_KILL", 70000, 1, buildingType="TOWER_BUILDING", teamId=200)])
    assert frame_states(game, tl)[-1]["towers"] == 1


def test_kill_without_killer_credits_the_opposite_team():
    # Victime bleue exécutée (killerId 0) : un kill pour le rouge.
    game, tl = _mini([_event("CHAMPION_KILL", 70000, killer=0, victim=2)])
    assert frame_states(game, tl)[-1]["kills"] == -1


def test_dead_players_and_respawn_window():
    game, tl = _mini([_event("CHAMPION_KILL", 100000, killer=6, victim=1)], frames=3)
    at_kill = next(s for t, e, s in walk(game, tl) if e is not None)
    assert at_kill["dead"] == 1 and 0 < at_kill["dead_s"] <= _respawn_s(6, 100)
    assert frame_states(game, tl)[-1]["dead"] == 0  # réapparu (16 s) avant 2 min


def test_soul_and_baron_buff_expiry():
    drakes = [
        _event("ELITE_MONSTER_KILL", 61000 + i, killer=1, monsterType="DRAGON") for i in range(4)
    ]
    baron = _event("ELITE_MONSTER_KILL", 62000, killer=1, monsterType="BARON_NASHOR")
    game, tl = _mini(drakes + [baron], frames=6)
    after_events = [s for t, e, s in walk(game, tl) if e is not None]
    assert after_events[3]["soul"] == 1 and after_events[3]["dragons"] == 4
    assert after_events[4]["baron"] == 1
    assert frame_states(game, tl)[-1]["baron"] == 0  # 300 s : les 180 s de buff sont écoulées


def test_respawn_grows_with_level_and_late_game():
    assert _respawn_s(1, 60) < _respawn_s(18, 60) < _respawn_s(18, 40 * 60)


def test_players_sum_to_the_team_difference_of_state_and_segments_chain_the_events():
    from src.winprob.state import _Replay, segments, transitions

    teams = {p["participantId"]: p["teamId"] for p in GAME["participants"]}
    replay = _Replay(teams)
    for frame in TIMELINE["frames"]:
        replay.frame(frame)
        t = frame["timestamp"] + 30000
        state, per = replay.state(t), replay.players(t)
        for name in ("level", "dead", "dead_s"):
            by_team = {100: 0.0, 200: 0.0}
            for pid, value in per[name].items():
                by_team[teams[pid]] += value
            assert by_team[100] - by_team[200] == pytest.approx(state[name])
    follows = list(segments(GAME, TIMELINE))
    events = list(transitions(GAME, TIMELINE))
    assert len(follows) == len(events) - 1
    for k, (a, b, _, _, _) in enumerate(follows):
        assert a == events[k][2] and b == events[k + 1][1]
