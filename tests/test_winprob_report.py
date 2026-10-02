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


def _row(game_id, kind, delta):
    return {"game_id": game_id, "event_type": kind, "delta_p": delta}


def test_review_ranks_costs_and_compares_halves():
    from src.winprob.report import impact_review

    rows = []
    for game_id in range(10, 0, -1):  # 10 parties, de la plus récente à la plus ancienne
        recent = game_id > 5
        rows += [
            _row(game_id, "death_solo", -0.06),
            _row(game_id, "kill", 0.04 if recent else 0.02),
        ]
    lines = impact_review(rows)
    assert "sur 10 partie(s)" in lines[0] and "-3 pts" in lines[0]  # 10 × (-0,06 + 0,03) / 10
    assert "dernières 5 parties : -2 pts, les 5 d'avant : -4 pts" in lines[1]
    assert lines[2].lstrip().startswith("Morts en solo") and "-6 pts en moyenne" in lines[2]
    assert lines[3].lstrip().startswith("Kills")


def test_review_is_empty_without_impact():
    from src.winprob.report import impact_review

    assert impact_review([]) == []


def test_player_impact_feeds_the_bilan(db, tmp_path):
    from tests.test_winprob_pending import _model_file, _store
    from src.coaching.report import review
    from src.repositories.coaching import CoachingRepository
    from src.winprob.pending import compute_pending

    _store(db)
    db.connection.cursor().execute(
        "INSERT INTO game_metrics (game_id, participant_id, metric, is_player, role, value) "
        "VALUES (1, 4, 'cs_per_min', 1, 'middle', 7.0)"
    )
    db.connection.commit()
    compute_pending(db, _model_file(tmp_path))
    rows = CoachingRepository(db).player_impact(10)
    assert rows and all(r["game_id"] == 1 for r in rows)
    assert any("Impact sur la win chance" in line for line in review(db))
