"""Impact par événement et attribution (SPEC-20 tâche 43, src/winprob/impact.py). Hermétiques."""

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
