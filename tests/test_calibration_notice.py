"""Tests for src/draft/calibration_notice.py (SPEC-12).

should_trigger() is pure and tested in isolation against every crossing
shape (single game, batch jump, staying flat). format_summary() is tested
against the real `db` fixture -- it's a thin composition of already-tested
src/analysis/calibration.py functions, so this only checks the plumbing
(threshold gate, model_version filter reaching the query) rather than
re-deriving the math.
"""

from src.config_constants import analysis_config
from src.draft.calibration_notice import format_summary, should_trigger

THRESHOLD = analysis_config.MIN_ROWS_FOR_CALIBRATION  # 30
INTERVAL = analysis_config.AUTO_CALIBRATION_CHECK_INTERVAL  # 20


class TestShouldTrigger:
    def test_below_threshold_never_triggers(self):
        assert should_trigger(before_count=10, after_count=THRESHOLD - 1) is False

    def test_crossing_the_threshold_for_the_first_time_triggers(self):
        assert should_trigger(before_count=THRESHOLD - 1, after_count=THRESHOLD) is True

    def test_reaching_exactly_the_threshold_from_below_triggers(self):
        assert should_trigger(before_count=THRESHOLD - 5, after_count=THRESHOLD) is True

    def test_a_single_game_between_two_multiples_does_not_retrigger(self):
        assert should_trigger(before_count=THRESHOLD + 1, after_count=THRESHOLD + 2) is False

    def test_crossing_the_next_interval_multiple_triggers_again(self):
        assert (
            should_trigger(before_count=THRESHOLD + INTERVAL - 1, after_count=THRESHOLD + INTERVAL)
            is True
        )

    def test_large_backfill_batch_jumping_straight_past_threshold_triggers_once(self):
        """A startup backfill can resolve several predictions in one call --
        going from well below to well above the threshold must still report
        True (the call site fires the notice once, not once per prediction)."""
        assert should_trigger(before_count=5, after_count=THRESHOLD + 40) is True

    def test_batch_skipping_multiple_intervals_still_triggers(self):
        assert (
            should_trigger(before_count=THRESHOLD + 5, after_count=THRESHOLD + INTERVAL * 3) is True
        )

    def test_staying_within_the_same_interval_bucket_does_not_trigger(self):
        assert (
            should_trigger(before_count=THRESHOLD + 2, after_count=THRESHOLD + INTERVAL - 1)
            is False
        )


class TestFormatSummary:
    def test_returns_none_below_threshold(self, db):
        prediction_id = db.insert_prediction([1], [2], None, 0.5, "v1")
        db.update_prediction_outcome(prediction_id, 1)

        assert format_summary(db, "v1") is None

    def test_returns_a_calibrate_tagged_summary_once_enough_rows_exist(self, db):
        for _ in range(THRESHOLD):
            prediction_id = db.insert_prediction([1], [2], None, 0.5, "v1")
            db.update_prediction_outcome(prediction_id, 1)

        summary = format_summary(db, "v1")

        assert summary is not None
        assert summary.startswith(f"[CALIBRATE] {THRESHOLD} prédictions labellisées")
        assert "Score de Brier" in summary
        assert "lecture seule" in summary

    def test_ignores_rows_from_a_different_model_version(self, db):
        for _ in range(THRESHOLD):
            prediction_id = db.insert_prediction([1], [2], None, 0.5, "v1")
            db.update_prediction_outcome(prediction_id, 1)

        assert format_summary(db, "v2-not-yet-played") is None
