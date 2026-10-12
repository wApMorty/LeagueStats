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
