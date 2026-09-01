"""Tests for the predictions table (SPEC-05 B7): Database.insert_prediction /
update_prediction_outcome / get_latest_prediction_id, and the best-effort
logging hook in DraftMonitor._calculate_final_scores.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor


class TestDatabaseInsertPrediction:
    def test_insert_prediction_writes_row_with_null_outcome(self, db):
        prediction_id = db.insert_prediction(
            ally_champions=[1, 2, 3, 4, 5],
            enemy_champions=[6, 7, 8, 9, 10],
            ally_lanes={1: "top", 2: "jungle"},
            predicted_probability=0.62,
            model_version="b7-v1",
        )

        assert prediction_id is not None

        cursor = db.connection.cursor()
        cursor.execute(
            "SELECT ally_champions, enemy_champions, ally_lanes, predicted_probability, "
            "model_version, outcome FROM predictions WHERE id = ?",
            (prediction_id,),
        )
        row = cursor.fetchone()
        assert row[0] == "1,2,3,4,5"
        assert row[1] == "6,7,8,9,10"
        assert row[2] == "top,jungle,,,"  # only champions 1 and 2 have a known lane
        assert row[3] == pytest.approx(0.62)
        assert row[4] == "b7-v1"
        assert row[5] is None  # outcome starts NULL

    def test_insert_prediction_without_lanes_stores_null(self, db):
        prediction_id = db.insert_prediction(
            ally_champions=[1, 2, 3, 4, 5],
            enemy_champions=[6, 7, 8, 9, 10],
            ally_lanes=None,
            predicted_probability=0.5,
            model_version="b7-v1",
        )

        cursor = db.connection.cursor()
        cursor.execute("SELECT ally_lanes FROM predictions WHERE id = ?", (prediction_id,))
        assert cursor.fetchone()[0] is None


class TestDatabaseUpdatePredictionOutcome:
    def test_update_prediction_outcome_sets_value(self, db):
        prediction_id = db.insert_prediction([1], [2], None, 0.5, "b7-v1")

        result = db.update_prediction_outcome(prediction_id, 1)

        assert result is True
        cursor = db.connection.cursor()
        cursor.execute("SELECT outcome FROM predictions WHERE id = ?", (prediction_id,))
        assert cursor.fetchone()[0] == 1

    def test_update_prediction_outcome_unknown_id_returns_false(self, db):
        assert db.update_prediction_outcome(999999, 0) is False


class TestDatabaseGetLatestPredictionId:
    def test_returns_most_recent_row_without_outcome(self, db):
        first_id = db.insert_prediction([1], [2], None, 0.5, "b7-v1")
        second_id = db.insert_prediction([3], [4], None, 0.6, "b7-v1")

        assert db.get_latest_prediction_id() == second_id

        db.update_prediction_outcome(second_id, 1)
        assert db.get_latest_prediction_id() == first_id

    def test_returns_none_when_no_pending_prediction(self, db):
        assert db.get_latest_prediction_id() is None


class TestDraftMonitorBestEffortLogging:
    """A broken insert_prediction (e.g. a dead connection) must never raise
    out of _calculate_final_scores, nor stop the draft analysis printout
    (SPEC-05 §4 B7 step 4: 'la journalisation ne doit jamais bloquer ni
    ralentir le draft')."""

    @pytest.fixture
    def monitor(self):
        with patch("src.draft_monitor.Assistant", return_value=Mock()):
            with patch("src.draft_monitor.LCUClient", return_value=Mock()):
                monitor = DraftMonitor(verbose=False, auto_hover=False)
        return monitor

    @staticmethod
    def _wire_common_mocks(monitor):
        ally_ids = [1, 2, 3, 4, 5]
        enemy_ids = [6, 7, 8, 9, 10]
        monitor.champion_id_to_name = {
            **{cid: f"Ally{cid}" for cid in ally_ids},
            **{cid: f"Enemy{cid}" for cid in enemy_ids},
        }

        matchup = Mock(games=1000)
        monitor.assistant.get_matchups_for_draft.return_value = [matchup]
        monitor.assistant.score_against_team.return_value = 2.0
        monitor.assistant.db.get_synergy_delta2.return_value = None
        monitor.assistant._calculate_team_winrate.return_value = {"team_winrate": 55.0}
        return ally_ids, enemy_ids

    def test_insert_prediction_failure_is_silent(self, monitor, capsys):
        ally_ids, enemy_ids = self._wire_common_mocks(monitor)
        monitor.assistant.db.insert_prediction.side_effect = Exception("db connection lost")

        # Must not raise, even though logging failed underneath.
        monitor._calculate_final_scores(ally_ids, enemy_ids, ally_lanes={1: "top"})

        assert monitor._last_prediction_id is None
        captured = capsys.readouterr()
        assert "Échec de l'enregistrement de la prédiction" in captured.out
        # The rest of the analysis still ran (didn't bail out early).
        assert "ANALYSE FINALE DU DRAFT" in captured.out

    def test_insert_prediction_success_stores_id(self, monitor):
        ally_ids, enemy_ids = self._wire_common_mocks(monitor)
        monitor.assistant.db.insert_prediction.return_value = 42

        monitor._calculate_final_scores(ally_ids, enemy_ids, ally_lanes={1: "top"})

        assert monitor._last_prediction_id == 42
