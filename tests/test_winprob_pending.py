"""Impacts calculés après coup (SPEC-20 tâche 44, src/winprob/pending.py et son branchement
sur la capture du coach de gameplay). Hermétiques : fixtures du spike, base temporaire."""

import json
from types import SimpleNamespace

import pytest

from src.coaching.capture import GameCapture
from src.repositories.coaching import CoachingRepository
from src.winprob.model import INPUTS, WinModel
from src.winprob.pending import compute_pending
from tests.test_winprob_impact import GAME, TIMELINE, _model


def _store(db, game_id=1, game=None, timeline=None):
    db.insert_game_record(
        game_id=game_id,
        queue_id=420,
        game_creation_utc=f"2026-10-01 00:00:{game_id:02d}",
        duration_s=1488,
        player_participant_id=4,
        raw_game=json.dumps(GAME if game is None else game),
        raw_timeline=json.dumps(TIMELINE if timeline is None else timeline),
        raw_eog=None,
    )


def _model_file(tmp_path):
    path = tmp_path / "winprob_model.json"
    path.write_text(_model().to_json(), encoding="utf-8")
    return path


def test_without_a_trained_model_nothing_happens(db, tmp_path):
    _store(db)
    assert compute_pending(db, tmp_path / "absent.json") == []
    assert CoachingRepository(db).impact_rows(1) == []


def test_pending_game_is_stored_once_with_its_report(db, tmp_path):
    _store(db)
    path = _model_file(tmp_path)
    [(game_id, lines)] = compute_pending(db, path)
    repo = CoachingRepository(db)
    assert game_id == 1 and lines[0].startswith("[DATA] Impact sur la win chance")
    assert {r["model_version"] for r in repo.impact_rows(1)} == {f"{_model().version}+c2"}
    assert repo.impact_rows(1, participant_id=4)
    assert compute_pending(db, path) == []  # figé : jamais recalculé


def test_unreadable_game_does_not_block_the_next_ones(db, tmp_path):
    _store(db, game_id=1, game={"participants": []}, timeline={"frames": [{"events": []}]})
    _store(db, game_id=2)
    assert [g for g, _ in compute_pending(db, _model_file(tmp_path))] == [2]


def test_capture_prints_the_latest_report_only_when_live(db, tmp_path, monkeypatch, capsys):
    _store(db)
    monkeypatch.setattr("src.winprob.pending.model_path", lambda: _model_file(tmp_path))
    capture = GameCapture(
        SimpleNamespace(lcu=None, assistant=SimpleNamespace(db=db), verbose=False)
    )
    capture.impact(live=True)
    assert "Impact sur la win chance" in capsys.readouterr().out
    _store(db, game_id=2)
    capture.impact(live=False)  # rattrapage : calcule sans rapport
    assert capsys.readouterr().out == ""
    assert CoachingRepository(db).impact_rows(2)


def _store_old_convention(db, game_id):
    """Une partie dont l'impact a été rangé avant SPEC-22 (version sans suffixe de convention)."""
    db.connection.execute(
        "INSERT INTO game_impact VALUES (?, 4, 1000, 'kill', 0.01, ?)",
        (game_id, f"{_model().version}+c1"),
    )
    db.connection.commit()


def test_a_game_stored_under_an_older_convention_is_recomputed_once(db, tmp_path):
    _store(db)
    _store_old_convention(db, 1)
    path = _model_file(tmp_path)
    assert [g for g, _ in compute_pending(db, path)] == [1]
    versions = {r["model_version"] for r in CoachingRepository(db).impact_rows(1)}
    assert versions == {f"{_model().version}+c2"}
    assert any(r["event_type"] == "levels" for r in CoachingRepository(db).impact_rows(1))
    assert compute_pending(db, path) == []


@pytest.mark.parametrize("eog", [None, "", "{", "[]", '{"teams": [{"players": [{}]}]}', '"x"'])
def test_absent_or_corrupt_end_of_game_screen_never_raises(db, tmp_path, eog):
    _store(db)
    db.connection.execute("UPDATE game_records SET raw_eog = ? WHERE game_id = 1", (eog,))
    db.connection.commit()
    assert [g for g, _ in compute_pending(db, _model_file(tmp_path))] == [1]
    assert CoachingRepository(db).impact_rows(1)


def test_the_end_of_game_screen_pairs_the_lane_opponents(db, tmp_path):
    _store(db)
    eog = {
        "teams": [
            {
                "players": [
                    {
                        "teamId": p["teamId"],
                        "championId": p["championId"],
                        "detectedTeamPosition": lane,
                    }
                    for p, lane in zip(
                        [q for q in GAME["participants"] if q["teamId"] == team],
                        ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"),
                    )
                ]
            }
            for team in (100, 200)
        ]
    }
    db.connection.execute(
        "UPDATE game_records SET raw_eog = ? WHERE game_id = 1", (json.dumps(eog),)
    )
    db.connection.commit()
    model_path = tmp_path / "winprob_model.json"
    model_path.write_text(
        WinModel(
            INPUTS, [0.0] * 2 * len(INPUTS), [1.0] * 2 * len(INPUTS), _level_weights()
        ).to_json(),
        encoding="utf-8",
    )
    compute_pending(db, model_path)
    levels = {
        r["participant_id"]: r["delta_p"]
        for r in CoachingRepository(db).impact_rows(1)
        if r["event_type"] == "levels"
    }
    blue, red = GAME["participants"][0], GAME["participants"][5]
    assert (blue["teamId"], red["teamId"]) == (100, 200)
    assert levels[blue["participantId"]] != 0
    assert levels[blue["participantId"]] == pytest.approx(-levels[red["participantId"]])


def _level_weights():
    weights = [0.0] * (2 * len(INPUTS) + 1)
    weights[INPUTS.index("level")] = 0.5
    return weights
