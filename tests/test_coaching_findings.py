"""Références, moteur de constats et rapport (SPEC-19 tâches 33 à 35).

Hermétiques : fixtures du spike, base temporaire, objectif OneTricks simulé.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.coaching import findings, report
from src.coaching.capture import GameCapture
from src.coaching.findings import analyze_pending
from src.coaching.grid import Reference, norm_reference, objective_from_history, z_score
from src.config_constants import coaching_config
from src.repositories.coaching import CoachingRepository

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME_ID = 7998195590
RAW_GAME = (FIXTURES / f"{GAME_ID}_game.json").read_text(encoding="utf-8")
RAW_TIMELINE = (FIXTURES / f"{GAME_ID}_timeline.json").read_text(encoding="utf-8")
DEATHS_PER_10 = 5 / (1488 / 60) * 10  # Olaf, participant 1


def no_objective(*_):
    return {}


def _record(db, game_id=GAME_ID, created="2026-09-28 21:23:18", raw_game=RAW_GAME):
    db.insert_game_record(
        game_id=game_id,
        queue_id=420,
        game_creation_utc=created,
        duration_s=1488,
        player_participant_id=1,
        raw_game=raw_game,
        raw_timeline=RAW_TIMELINE,
        raw_eog=None,
    )


def _norm(db, values, metric="deaths_per_10", role="top"):
    """Parties antérieures dont l'adversaire du poste a les valeurs données."""
    rows = []
    for index, value in enumerate(values, 1):
        _record(db, game_id=index, created=f"2026-09-01 00:00:{index:02d}", raw_game="{}")
        rows.append((index, 6, metric, 0, role, 240, value) + (None,) * 9)
    CoachingRepository(db).insert_metrics(rows)


def _rows(db, sql):
    cursor = db.connection.cursor()
    cursor.execute(sql)
    return cursor.fetchall()


class TestReferences:
    def test_z_is_oriented_so_that_positive_is_good_news(self):
        ref = Reference(mean=2.0, sd=1.0, n=20)
        assert z_score(4.0, ref, sense=-1) == -2.0  # morts : plus est pire
        assert z_score(4.0, ref, sense=1) == 2.0
        assert z_score(4.0, Reference(2.0, None, 1), sense=1) is None

    def test_lane_gap_norm_is_zero_whatever_the_opponents_mirror(self):
        # Adversaires de lane d'un joueur qui gagne ses lanes : leur écart est
        # l'opposé du sien. Leur moyenne (-600) ne mesurerait que lui.
        ref = norm_reference("gold_diff_15", [-400.0, -800.0])
        assert (ref.mean, ref.n) == (0.0, 2)
        assert ref.sd == pytest.approx((400**2 / 2 + 800**2 / 2) ** 0.5)
        assert norm_reference("cs_10", [60.0, 80.0]).mean == 70.0

    def test_onetricks_objective_reads_the_played_role_only(self):
        game = {
            "details": {
                "playerData": {"stats": {"cs": 210, "deaths": 3, "kills": 5, "assists": 5}},
                "gameDuration": 1800,
                "teamKills": 20,
            },
            "gameRoles": {"playerRole": "top", "gd15": 500, "exp15": 300},
        }
        history = [game] * 25 + [{**game, "gameRoles": {"playerRole": "jungle"}}] * 30
        history[0] = {**game, "gameRoles": {**game["gameRoles"], "gd15": 1500}}

        refs = objective_from_history(history, "top", "OneTricks Olaf")

        assert refs["cs_per_min"].mean == pytest.approx(7.0)
        assert refs["deaths_per_10"].mean == pytest.approx(1.0)
        assert refs["kill_participation"].mean == pytest.approx(0.5)
        assert refs["gold_diff_15"].n == 25 and refs["gold_diff_15"].sd > 0
        assert refs["gold_diff_15"].source == "OneTricks Olaf n=25"

    def test_onetricks_objective_needs_enough_games(self):
        game = {"gameRoles": {"playerRole": "top", "gd15": 1, "exp15": 1}}
        assert objective_from_history([game] * 5, "top", "x") == {}


class TestAnalyzeGame:
    def test_negative_finding_against_the_norm_is_stored_and_ranked(self, db):
        _norm(db, [0.5, 1.5] * 10)  # moyenne 1, écart-type ~0,51
        _record(db)

        (analysis,) = analyze_pending(db, no_objective)

        assert analysis.role == "top" and analysis.opponent_champion_id == 240
        worst = analysis.negatives[0]
        assert worst.metric == "deaths_per_10" and worst.reference == "norm"
        assert worst.z == pytest.approx(-(DEATHS_PER_10 - 1.0) / 0.5130, abs=0.01)
        assert _rows(db, "SELECT metric, polarity, rank FROM game_findings") == [
            ("deaths_per_10", "negative", 1)
        ]
        stored = _rows(
            db,
            "SELECT norm_n, grid_version FROM game_metrics "
            f"WHERE game_id = {GAME_ID} AND is_player = 1 AND metric = 'deaths_per_10'",
        )
        assert stored == [(20, coaching_config.GRID_VERSION)]

    def test_small_norm_is_stored_but_never_ranked(self, db):
        _norm(db, [0.5, 1.5] * 3)
        _record(db)

        (analysis,) = analyze_pending(db, no_objective)

        assert analysis.negatives == [] and analysis.norm_n == 6
        z = _rows(
            db,
            "SELECT z_norm FROM game_metrics WHERE is_player = 1 AND metric = 'deaths_per_10'",
        )
        assert z[0][0] < 0  # stocké quand même (critère 6)

    def test_objective_ranks_when_the_norm_is_too_small(self, db):
        _record(db)
        objective = {"deaths_per_10": Reference(1.0, 0.5, 100, "OneTricks Olaf n=100")}

        (analysis,) = analyze_pending(db, lambda *_: objective)

        assert analysis.negatives[0].reference == "objective"
        source = _rows(db, "SELECT objective_source FROM game_metrics WHERE z_objective < 0")
        assert source == [("OneTricks Olaf n=100",)]

    def test_second_pass_analyzes_nothing(self, db):
        _record(db)
        analyze_pending(db, no_objective)
        assert analyze_pending(db, no_objective) == []

    def test_grid_version_change_recomputes_everything(self, db):
        _record(db)
        analyze_pending(db, no_objective)
        db.connection.execute("UPDATE game_metrics SET grid_version = 0 WHERE is_player = 1")

        assert len(analyze_pending(db, no_objective)) == 1

    def test_malformed_raw_game_does_not_block_the_next_ones(self, db):
        _record(db, game_id=1, created="2026-09-01 00:00:00", raw_game='{"gameDuration": 1}')
        _record(db)

        assert [a.game_id for a in analyze_pending(db, no_objective)] == [GAME_ID]


class TestReport:
    def test_report_shows_the_draft_context_and_the_findings(self, db):
        _norm(db, [0.5, 1.5] * 10)
        _record(db)
        (analysis,) = analyze_pending(db, no_objective)

        lines = report.game_report(analysis, lambda cid: f"C{cid}", predicted=0.54, duel=-2.1)

        assert lines[0].startswith("[DATA] Fin de partie : C2 top vs C240, victoire (24 min")
        assert "54% prédit, duel défavorable (-2.1 pts)" in lines[1]
        assert lines[2].startswith("[ALERTE] Morts / 10 min : 2.0")
        assert "(norme 1.0)" in lines[2]

    def test_report_says_when_the_norm_is_still_building(self, db):
        _record(db)
        (analysis,) = analyze_pending(db, no_objective)

        lines = report.game_report(analysis, str)

        assert any("Norme en construction (0/" in line for line in lines)


class TestLiveCapture:
    def test_post_game_pass_prints_the_report_of_the_new_game(self, db, capsys):
        lcu = Mock()
        lcu.get_recent_matches.return_value = [
            {
                "game_id": GAME_ID,
                "game_creation_ms": 1790630598170,
                "queue_id": 420,
                "participant_id": 1,
            }
        ]
        lcu.get_game_detail.return_value = json.loads(RAW_GAME)
        lcu.get_game_timeline.return_value = json.loads(RAW_TIMELINE)
        lcu.get_end_of_game_block.return_value = None
        lcu.get_lp_change_notification.return_value = {}
        monitor = SimpleNamespace(lcu=lcu, assistant=SimpleNamespace(db=db), verbose=True)

        with patch.object(findings, "onetricks_objective", return_value={}):
            GameCapture(monitor).on_post_game()

        out = capsys.readouterr().out
        assert "[DATA] Fin de partie : " in out
        assert "[WARNING]" not in out
