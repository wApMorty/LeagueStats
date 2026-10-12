"""Impact par événement et attribution (SPEC-20 tâche 43, src/winprob/impact.py). Hermétiques."""

import copy
import json
from pathlib import Path

import pytest

from src.winprob.impact import event_kind, impacts
from src.winprob.model import INPUTS, WinModel
from src.winprob.state import BLUE, RED, transitions

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))


def _model():
    """Modèle jouet : chaque kill d'avance vaut +0,5 de logit, chaque tour +0,5, le reste nul."""
    d = 2 * len(INPUTS)
    weights = [0.0] * (d + 1)
    weights[INPUTS.index("kills")] = 0.5
    weights[INPUTS.index("towers")] = 0.5
    return WinModel(INPUTS, [0.0] * d, [1.0] * d, weights)


def _model_baron():
    """Comme `_model()`, avec +0,5 de logit par Nashor d'avance (le baron ne bouge pas `_model()`)."""
    d = 2 * len(INPUTS)
    weights = [0.0] * (d + 1)
    weights[INPUTS.index("baron")] = 0.5
    return WinModel(INPUTS, [0.0] * d, [1.0] * d, weights)


def _at(rows, ts: int, label: str) -> list:
    return [r for r in rows if r["event_time_ms"] == ts and r["event_type"] == label]


def test_lost_objectives_mirror_the_scorer_row_for_row():
    # Tour rouge détruite par le bleu à 905 206 ms (delta > 0) ; Nashor à 1 325 162 ms.
    rows = impacts(_model(), GAME, TIMELINE)["rows"]
    tower_for, tower_lost = _at(rows, 905206, "tower"), _at(rows, 905206, "lost_tower")
    assert tower_lost and all(r["delta_p"] < 0 for r in tower_lost)
    assert all(r["participant_id"] >= 6 for r in tower_lost)  # côté rouge
    assert sum(r["delta_p"] for r in tower_lost) == pytest.approx(
        -sum(r["delta_p"] for r in tower_for)
    )
    rows = impacts(_model_baron(), GAME, TIMELINE)["rows"]
    baron_for, baron_lost = _at(rows, 1325162, "baron"), _at(rows, 1325162, "lost_baron")
    assert baron_lost and all(r["delta_p"] < 0 for r in baron_lost)
    assert sum(r["delta_p"] for r in baron_lost) == pytest.approx(
        -sum(r["delta_p"] for r in baron_for)
    )


def test_lost_objectives_fall_back_to_five_when_none_is_absent():
    event = next(e for e, _, _ in transitions(GAME, TIMELINE) if e["timestamp"] == 905206)
    timeline = copy.deepcopy(TIMELINE)
    frame = min(timeline["frames"], key=lambda f: abs(f["timestamp"] - 905206))
    for pid in range(6, 11):  # les cinq rouges sur la tour : aucun absent
        frame["participantFrames"][str(pid)]["position"] = dict(event["position"])
    rows = impacts(_model(), GAME, timeline)["rows"]
    lost = _at(rows, 905206, "lost_tower")
    assert sorted(r["participant_id"] for r in lost) == [6, 7, 8, 9, 10]
    for r in lost:
        assert r["delta_p"] == pytest.approx(lost[0]["delta_p"])
    assert sum(r["delta_p"] for r in lost) == pytest.approx(
        -sum(r["delta_p"] for r in _at(rows, 905206, "tower"))
    )


def test_only_absent_foes_are_charged_when_some_are_present():
    # Nashor à 1 325 162 ms : rouges 7 et 10 présents, 6, 8 et 9 absents.
    rows = impacts(_model_baron(), GAME, TIMELINE)["rows"]
    lost = _at(rows, 1325162, "lost_baron")
    assert sorted(r["participant_id"] for r in lost) == [6, 8, 9]


def test_kill_carries_no_lost_row():
    kill_ts = {e["timestamp"] for e, _, _ in transitions(GAME, TIMELINE) if event_kind(e) == "kill"}
    rows = impacts(_model(), GAME, TIMELINE)["rows"]
    lost = [r for r in rows if r["event_type"].startswith("lost_")]
    assert lost and not {r["event_time_ms"] for r in lost} & kill_ts


def test_transitions_share_the_same_instant():
    for e, before, after in transitions(GAME, TIMELINE):
        assert before["time_min"] == after["time_min"] == e["timestamp"] / 60000


def test_kill_hurts_the_victim_and_rewards_killer_and_assists_equally():
    rows = impacts(_model(), GAME, TIMELINE)["rows"]
    # 1er kill : le participant 10 (rouge) tue le participant 5 (bleu) à 94 829 ms, assisté par le 7.
    first = [r for r in rows if r["event_time_ms"] == 94829]
    by_pid = {r["participant_id"]: r["delta_p"] for r in first}
    assert by_pid[5] < 0 and by_pid[10] > 0
    assert by_pid[10] == pytest.approx(by_pid[7])
    assert by_pid[10] + by_pid[7] == pytest.approx(-by_pid[5])


def test_objective_goes_to_scoring_team_only():
    rows = impacts(_model(), GAME, TIMELINE)["rows"]
    tower = [r for r in rows if r["event_type"] == "tower" and r["event_time_ms"] == 905206]
    assert tower and all(r["participant_id"] <= 5 for r in tower)  # tour rouge détruite par le bleu
    assert all(r["delta_p"] > 0 for r in tower)
    assert {4, 1, 3, 5} <= {r["participant_id"] for r in tower}  # tueur 4, assistants 1, 3, 5


def test_team_summary_reconciles_attributed_and_residual():
    teams = impacts(_model(), GAME, TIMELINE)["teams"]
    for summary in teams.values():
        assert summary["attributed"] + summary["unattributed"] == pytest.approx(summary["total"])
    assert teams[BLUE]["total"] == pytest.approx(-teams[RED]["total"])


def test_event_kind_names():
    assert event_kind({"type": "CHAMPION_KILL"}) == "kill"
    base = {"type": "ELITE_MONSTER_KILL", "monsterSubType": ""}
    assert event_kind({**base, "monsterType": "BARON_NASHOR"}) == "baron"
    assert (
        event_kind({**base, "monsterType": "DRAGON", "monsterSubType": "ELDER_DRAGON"}) == "elder"
    )
    assert (
        event_kind({"type": "BUILDING_KILL", "buildingType": "INHIBITOR_BUILDING"}) == "inhibitor"
    )


def _only(**weights):
    """Modèle jouet qui ne pèse que les variables nommées (logit par unité d'avance)."""
    d = 2 * len(INPUTS)
    w = [0.0] * (d + 1)
    for name, value in weights.items():
        w[INPUTS.index(name)] = value
    return WinModel(INPUTS, [0.0] * d, [1.0] * d, w)


def _kill(ts, victim, killer, assists=()):
    return {
        "type": "CHAMPION_KILL",
        "timestamp": ts,
        "victimId": victim,
        "killerId": killer,
        "assistingParticipantIds": list(assists),
    }


def _mini(levels, kills):
    """Dix joueurs, cinq images d'une minute ; les niveaux `levels` arrivent à la 3e image, entre
    deux kills (`kills` : `(image, événement)`) : un intervalle sans événement les porte."""
    game = {
        "participants": [
            {"participantId": i, "teamId": BLUE if i <= 5 else RED} for i in range(1, 11)
        ]
    }
    frames = []
    for n in range(5):
        pf = {
            str(i): {
                "level": (levels.get(i, 1) if n >= 2 else 1),
                "minionsKilled": 0,
                "jungleMinionsKilled": 0,
                "totalGold": 0,
            }
            for i in range(1, 11)
        }
        frames.append(
            {
                "timestamp": 60000 * n,
                "events": [e for at, e in kills if at == n],
                "participantFrames": pf,
            }
        )
    return game, {"frames": frames}


LANES = {i: ["top", "jungle", "middle", "bottom", "utility"][(i - 1) % 5] for i in range(1, 11)}


def test_level_and_respawn_leave_no_residual_with_a_model_that_only_weighs_them():
    model = _only(level=0.4, dead=-0.3, dead_s=-0.05)
    result = impacts(model, GAME, TIMELINE)
    for summary in result["teams"].values():
        assert summary["unattributed"] == pytest.approx(0.0, abs=1e-9)
    assert {"levels", "respawn"} <= {r["event_type"] for r in result["rows"]}


def test_levels_of_two_lane_opponents_cancel_and_teams_do_not_depend_on_roles():
    game, timeline = _mini({1: 4, 6: 2}, [(1, _kill(70000, 3, 8)), (3, _kill(200000, 9, 4))])
    model = _only(level=0.5)
    paired = impacts(model, game, timeline, LANES)["rows"]
    blind = impacts(model, game, timeline)["rows"]
    by = lambda rows: {
        r["participant_id"]: r["delta_p"] for r in rows if r["event_type"] == "levels"
    }
    top, anywhere = by(paired), by(blind)
    assert top[1] > 0 and top[1] == pytest.approx(-top[6])  # même poste : lignes opposées
    assert len(top) == 10 and sum(top.values()) == pytest.approx(0.0)
    assert sum(top[i] for i in range(1, 6)) == pytest.approx(sum(anywhere[i] for i in range(1, 6)))
    assert anywhere[1] != pytest.approx(top[1])  # sans poste : moyenne des cinq adverses


def test_respawn_goes_to_the_victim_and_is_charged_to_killer_and_assistant():
    game, timeline = _mini({}, [(1, _kill(65000, 1, 6, [7])), (3, _kill(200000, 8, 2))])
    rows = impacts(_only(dead=-0.3, dead_s=-0.05), game, timeline)["rows"]
    got = {r["participant_id"]: r["delta_p"] for r in rows if r["event_type"] == "respawn"}
    assert got[1] > 0 and got[6] == pytest.approx(-got[1] / 2) == pytest.approx(got[7])
    assert all(got[i] == 0 for i in (2, 3, 4, 5, 8, 9, 10))


def test_respawn_without_a_killer_charges_nobody():
    game, timeline = _mini({}, [(1, _kill(65000, 1, 0)), (3, _kill(200000, 8, 2))])
    result = impacts(_only(dead=-0.3, dead_s=-0.05), game, timeline)
    got = {
        r["participant_id"]: r["delta_p"] for r in result["rows"] if r["event_type"] == "respawn"
    }
    assert got[1] > 0 and all(got[i] == 0 for i in range(2, 11))
