"""Tests for src/analysis/calibration.py (SPEC-12).

Extracted from scripts/calibrate_model.py -- no prior test coverage existed
for this math (SPEC-10 §3.5 style gap: correct-looking code nobody had
pinned). Covers the pure functions and the one DB read (fetch_labeled_
predictions), via the real `db` fixture (temp_db, never data/db.db).
"""

import pytest

from src.analysis.calibration import (
    auc,
    brier_score,
    calibration_buckets,
    calibration_curve,
    fetch_labeled_predictions,
    intrinsic_points,
    suggest_scale,
)


class TestBrierScore:
    def test_perfect_predictions_score_zero(self):
        assert brier_score([(1.0, 1), (0.0, 0)]) == pytest.approx(0.0)

    def test_always_50_percent_scores_quarter(self):
        assert brier_score([(0.5, 1), (0.5, 0)]) == pytest.approx(0.25)

    def test_worst_case_predictions_score_one(self):
        assert brier_score([(0.0, 1), (1.0, 0)]) == pytest.approx(1.0)


class TestCalibrationCurve:
    def test_buckets_by_decile(self):
        # 0.05 -> bucket 0 ([0-10%[), 0.95 -> bucket 9 ([90-100%[)
        output = calibration_curve([(0.05, 0), (0.95, 1)])
        lines = output.splitlines()
        assert len(lines) == 10
        assert "n=   1" in lines[0]
        assert "n=   1" in lines[9]

    def test_probability_of_exactly_one_lands_in_the_top_bucket(self):
        """int(1.0 * 10) == 10 would overflow a 0-9 bucket list -- the
        min(..., 9) clamp in the implementation must catch this."""
        output = calibration_curve([(1.0, 1)])
        lines = output.splitlines()
        assert "n=   1" in lines[9]
        assert all("n=   1" not in line for line in lines[:9])

    def test_empty_bucket_reports_n_zero(self):
        output = calibration_curve([(0.05, 0)])
        assert "[ 10- 20%[  n=0" in output


class TestSuggestScale:
    def test_well_calibrated_predictions_converge_near_one(self):
        """Predictions whose observed win rate exactly matches the predicted
        probability (70% predicted -> 7/10 observed wins, 30% -> 3/10)
        shouldn't suggest much of a correction."""
        rows = ([(0.7, 1)] * 7 + [(0.7, 0)] * 3 + [(0.3, 1)] * 3 + [(0.3, 0)] * 7) * 5
        scale = suggest_scale(rows)
        assert scale == pytest.approx(1.0, abs=0.15)

    def test_overconfident_predictions_suggest_scaling_down(self):
        """Predictions clustered near the extremes but with observed
        outcomes close to 50/50 mean the model is too confident (scale < 1)."""
        rows = [(0.9, 1), (0.9, 0)] * 20
        scale = suggest_scale(rows)
        assert scale < 1.0


class TestFetchLabeledPredictions:
    def test_only_rows_with_outcome_are_returned(self, db):
        resolved_id = db.insert_prediction([1, 2, 3, 4, 5], [6, 7, 8, 9, 10], None, 0.6, "v1")
        db.insert_prediction([1, 2, 3, 4, 5], [6, 7, 8, 9, 10], None, 0.4, "v1")  # left pending
        db.update_prediction_outcome(resolved_id, 1)

        rows = fetch_labeled_predictions(db)

        assert rows == [(0.6, 1)]

    def test_filters_by_model_version_when_given(self, db):
        old_id = db.insert_prediction([1], [2], None, 0.5, "v1")
        new_id = db.insert_prediction([1], [2], None, 0.6, "v2")
        db.update_prediction_outcome(old_id, 0)
        db.update_prediction_outcome(new_id, 1)

        assert fetch_labeled_predictions(db, "v2") == [(0.6, 1)]
        assert fetch_labeled_predictions(db, "v1") == [(0.5, 0)]
        assert set(fetch_labeled_predictions(db, None)) == {(0.5, 0), (0.6, 1)}

    def test_no_labeled_rows_returns_empty_list(self, db):
        db.insert_prediction([1], [2], None, 0.5, "v1")  # never resolved
        assert fetch_labeled_predictions(db) == []


# ---------- SPEC-18 : AUC et force intrinsèque ----------


def test_auc_perfect_random_and_inverted():
    assert auc([(0.9, 1), (0.8, 1), (0.2, 0), (0.1, 0)]) == 1.0
    assert auc([(0.1, 1), (0.9, 0)]) == 0.0
    assert auc([(0.5, 1), (0.5, 0)]) == 0.5


def test_auc_without_both_outcomes_is_uninformative():
    assert auc([(0.9, 1), (0.8, 1)]) == 0.5
    assert auc([]) == 0.5


def test_intrinsic_points_is_ally_minus_enemy_and_missing_counts_as_mean():
    strength = {"top": {"Garen": 2.0, "Teemo": -1.0}, "middle": {"Ahri": 0.5}}
    allies = [("Garen", "top"), ("Ahri", "middle"), ("Unknown", "jungle")]
    enemies = [("Teemo", "top"), ("Zed", "middle"), ("Ahri", None)]

    assert intrinsic_points(allies, enemies, strength) == 2.0 + 0.5 - (-1.0)


def _lcg_rows(count=80):
    """Prédictions et issues pseudo-aléatoires mais fixes (générateur congruentiel)."""
    seed, rows = 7, []
    for _ in range(count):
        seed = (seed * 9301 + 49297) % 233280
        predicted = seed / 233280
        seed = (seed * 9301 + 49297) % 233280
        rows.append((round(predicted, 4), 1 if seed / 233280 < 0.25 + 0.5 * predicted else 0))
    return rows


class TestCalibrationBuckets:
    """SPEC-21 tâche 54 : `calibration_curve()` devient une mise en forme de `calibration_buckets()`,
    sa sortie texte est inchangée (relevée avant l'extraction)."""

    GOLDEN = "\n".join(
        [
            "  [  0- 10%[  n=  12  predicted=  5.6%  observed= 25.0%",
            "  [ 10- 20%[  n=  10  predicted= 15.2%  observed= 60.0%",
            "  [ 20- 30%[  n=  10  predicted= 25.5%  observed= 30.0%",
            "  [ 30- 40%[  n=   3  predicted= 33.8%  observed= 66.7%",
            "  [ 40- 50%[  n=  16  predicted= 45.4%  observed= 56.2%",
            "  [ 50- 60%[  n=   8  predicted= 56.3%  observed= 75.0%",
            "  [ 60- 70%[  n=   8  predicted= 65.7%  observed= 62.5%",
            "  [ 70- 80%[  n=   6  predicted= 74.4%  observed= 33.3%",
            "  [ 80- 90%[  n=   3  predicted= 86.6%  observed= 66.7%",
            "  [ 90-100%[  n=   4  predicted= 94.4%  observed= 50.0%",
        ]
    )

    def test_text_output_is_identical_to_the_one_before_the_extraction(self):
        assert calibration_curve(_lcg_rows()) == self.GOLDEN

    def test_text_output_with_an_empty_bucket_is_identical(self):
        output = calibration_curve([row for row in _lcg_rows() if row[0] < 0.9])
        assert output.splitlines()[:9] == self.GOLDEN.splitlines()[:9]
        assert output.splitlines()[9] == "  [ 90-100%[  n=0"

    def test_buckets_carry_counts_means_and_rates(self):
        buckets = calibration_buckets([(0.05, 0), (0.07, 1), (1.0, 1)])
        assert [b["n"] for b in buckets] == [2, 0, 0, 0, 0, 0, 0, 0, 0, 1]
        assert buckets[0]["predicted"] == pytest.approx(0.06) and buckets[0]["observed"] == 0.5
        assert buckets[1]["predicted"] is None and buckets[1]["observed"] is None
        assert (buckets[9]["lo"], buckets[9]["hi"]) == (90, 100)
