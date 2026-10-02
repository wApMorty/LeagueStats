"""Rapport d'impact de fin de partie (SPEC-20 tâche 44, src/winprob/report.py). Hermétiques."""

import json
from pathlib import Path

from src.winprob.impact import impacts
from src.winprob.report import SPARK, curve, impact_report
from tests.test_winprob_impact import _model

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))
MODEL = _model()


def _report(pid):
    return impact_report(MODEL, GAME, TIMELINE, pid, impacts(MODEL, GAME, TIMELINE))


def test_curve_has_one_block_per_frame_and_flips_with_the_team():
    blue, red = curve(MODEL, GAME, TIMELINE, 100), curve(MODEL, GAME, TIMELINE, 200)
    assert len(blue) == len(red) == len(TIMELINE["frames"])
    assert set(blue + red) <= set(SPARK)
    assert SPARK.index(blue[-1]) > SPARK.index(red[-1])  # bleu gagne cette partie


def test_report_for_a_blue_player_lists_costs_and_gains():
    lines = _report(
        5
    )  # participant 5 : tué à 1:34 (assisté par 7), puis à 16:07 par 8 assisté par 10
    assert lines[0].startswith("[DATA] Impact sur la win chance")
    assert any(line.startswith("  Courbe") for line in lines)
    costly = [line for line in lines if line.startswith("  Plus coûteux")]
    assert costly and "mort à 1:34" in " ".join(costly)  # tué avec assistance : pas « solo »
    assert any("Non attribué" in line for line in lines)


def test_solo_death_is_flagged_with_the_objective_lost_right_after():
    # Participant 4 (bleu) : 1re mort tuée seul ? On cherche une mort solo du joueur 10 (rouge).
    solo = [
        e
        for f in TIMELINE["frames"]
        for e in f["events"]
        if e["type"] == "CHAMPION_KILL" and e["victimId"] == 10 and not e["assistingParticipantIds"]
    ]
    assert solo
    text = " ".join(_report(10))
    assert "mort solo" in text
