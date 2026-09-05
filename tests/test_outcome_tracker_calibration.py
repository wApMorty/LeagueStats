"""Integration tests: OutcomeTracker triggers the SPEC-12 calibration notice
at the right moments, and never lets a failure there corrupt resolved_count.

Reuses the fixtures/helpers of tests/test_outcome_tracker.py (SPEC-08)
rather than duplicating them.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.config_constants import analysis_config
from src.draft import calibration_notice
from src.draft.outcome_tracker import OutcomeTracker
from tests.test_outcome_tracker import (
    FULL_MATCH_PARTICIPANTS,
    _fake_monitor,
    _insert_prediction,
    _match,
)

THRESHOLD = analysis_config.MIN_ROWS_FOR_CALIBRATION  # 30
INTERVAL = analysis_config.AUTO_CALIBRATION_CHECK_INTERVAL  # 20


def _seed_already_labelled(db, count: int) -> None:
    """Insert and resolve `count` predictions directly via Database, bypassing
    OutcomeTracker -- these represent games labelled before the scenario
    under test, establishing the "before" count."""
    for _ in range(count):
        prediction_id = db.insert_prediction([1], [2], None, 0.5, analysis_config.MODEL_VERSION)
        db.update_prediction_outcome(prediction_id, 1)


class TestCalibrationNoticeTrigger:
    def test_crossing_the_threshold_prints_the_calibrate_block(self, db, capsys):
        _seed_already_labelled(db, THRESHOLD - 1)
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 1
        out = capsys.readouterr().out
        assert "[CALIBRATE]" in out
        assert f"{THRESHOLD} prédictions labellisées" in out

    def test_staying_well_below_threshold_does_not_print_the_block(self, db, capsys):
        _seed_already_labelled(db, 5)
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        OutcomeTracker(monitor).resolve_pending()

        assert "[CALIBRATE]" not in capsys.readouterr().out

    def test_one_more_game_within_the_same_interval_does_not_reprint(self, db, capsys):
        _seed_already_labelled(db, THRESHOLD + 2)
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        OutcomeTracker(monitor).resolve_pending()

        assert "[CALIBRATE]" not in capsys.readouterr().out

    def test_crossing_the_next_interval_reprints(self, db, capsys):
        _seed_already_labelled(db, THRESHOLD + INTERVAL - 1)
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        OutcomeTracker(monitor).resolve_pending()

        assert "[CALIBRATE]" in capsys.readouterr().out

    def test_a_backfill_batch_crossing_the_threshold_prints_it_exactly_once(self, db, capsys):
        """Several predictions resolved in one resolve_pending() call (the
        startup backfill scenario) that together cross the threshold must
        print the block once, not once per resolved prediction."""
        _seed_already_labelled(db, THRESHOLD - 2)
        ids = [_insert_prediction(db) for _ in range(3)]
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [
            _match(100 + i, minutes_after=30 + i) for i in range(len(ids))
        ]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 3
        # The summary block itself repeats the [CALIBRATE] tag per line (same
        # convention as [OUTCOME] elsewhere) -- count the header line, which
        # format_summary() emits exactly once per invocation, to check the
        # whole block was printed once rather than once per resolved game.
        assert capsys.readouterr().out.count("prédictions labellisées (model_version=") == 1

    def test_no_new_resolution_never_checks_calibration(self, db, capsys):
        """No prediction resolved this call -> no reason to touch the
        calibration path at all (also protects the DB from a pointless
        extra query on every empty poll)."""
        _seed_already_labelled(db, THRESHOLD)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = []  # nothing to resolve

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        assert "[CALIBRATE]" not in capsys.readouterr().out


class TestCalibrationNoticeIsBestEffort:
    def test_a_failing_calibration_check_does_not_affect_resolved_count(self, db, monkeypatch):
        _seed_already_labelled(db, THRESHOLD - 1)
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS
        monkeypatch.setattr(
            calibration_notice, "should_trigger", Mock(side_effect=RuntimeError("boom"))
        )

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 1  # the actual outcome resolution is unaffected

    def test_a_failing_calibration_check_does_not_raise(self, db, monkeypatch, capsys):
        _seed_already_labelled(db, THRESHOLD - 1)
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.verbose = True
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS
        monkeypatch.setattr(
            calibration_notice, "format_summary", Mock(side_effect=RuntimeError("boom"))
        )

        OutcomeTracker(monitor).resolve_pending()  # must not raise

        assert "[WARNING]" in capsys.readouterr().out
