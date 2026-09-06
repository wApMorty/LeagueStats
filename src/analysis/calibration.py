"""Pure calibration math for the log-odds scoring model (SPEC-05 B7).

Extracted from scripts/calibrate_model.py (SPEC-12) so both the standalone
CLI diagnostic and the live Draft Coach's auto-triggered summary
(src/draft/calibration_notice.py) share one implementation instead of two.
No I/O beyond the DB read in fetch_labeled_predictions(); everything else is
plain math, hand-rolled per SPEC-05 section 8 ("hors périmètre" for
numpy/scipy/sklearn on a 2-parameter logistic regression).
"""

import math
from typing import List, Optional, Tuple

Row = Tuple[float, int]  # (predicted_probability, outcome)


def fetch_labeled_predictions(db, model_version: Optional[str] = None) -> List[Row]:
    """Rows with a known outcome, optionally restricted to one model_version
    (SPEC-05 §7: mixing model versions makes calibration meaningless)."""
    cursor = db.connection.cursor()
    if model_version:
        cursor.execute(
            "SELECT predicted_probability, outcome FROM predictions "
            "WHERE outcome IS NOT NULL AND model_version = ?",
            (model_version,),
        )
    else:
        cursor.execute(
            "SELECT predicted_probability, outcome FROM predictions WHERE outcome IS NOT NULL"
        )
    return cursor.fetchall()


def calibration_curve(rows: List[Row]) -> str:
    """Bucket predictions into 10 decile buckets, predicted vs observed win rate."""
    buckets: List[List[Row]] = [[] for _ in range(10)]
    for predicted, outcome in rows:
        idx = min(int(predicted * 10), 9)
        buckets[idx].append((predicted, outcome))

    lines = []
    for i, bucket in enumerate(buckets):
        lo, hi = i * 10, (i + 1) * 10
        if not bucket:
            lines.append(f"  [{lo:3d}-{hi:3d}%[  n=0")
            continue
        mean_predicted = sum(p for p, _ in bucket) / len(bucket)
        observed = sum(o for _, o in bucket) / len(bucket)
        lines.append(
            f"  [{lo:3d}-{hi:3d}%[  n={len(bucket):4d}  "
            f"predicted={mean_predicted * 100:5.1f}%  observed={observed * 100:5.1f}%"
        )
    return "\n".join(lines)


def brier_score(rows: List[Row]) -> float:
    """Mean((predicted_probability - outcome)^2). 0 = perfect, 0.25 = always predicting 50%."""
    return sum((p - o) ** 2 for p, o in rows) / len(rows)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def suggest_scale(rows: List[Row], learning_rate: float = 0.1, iterations: int = 500) -> float:
    """Hand-rolled 1-parameter logistic recalibration (Platt scaling, no
    intercept -- our model is already centered at logit=0 for an even draft):
    finds the scale `s` maximizing the log-likelihood of the observed
    outcomes under `P = sigmoid(s * logit(predicted_probability))`.

    Plain gradient ascent in pure Python -- no numpy/scipy/sklearn, per
    SPEC-05 section 8 ("la régression logistique de calibration se fait sur
    2 paramètres, à la main ... aucune dépendance nouvelle"). `s < 1` means
    the model is currently too confident (predictions too far from 50%);
    `s > 1` means it's too timid.
    """
    logits = [_logit(p) for p, _ in rows]
    outcomes = [o for _, o in rows]
    n = len(rows)

    scale = 1.0
    for _ in range(iterations):
        gradient = sum((y - _sigmoid(scale * x)) * x for x, y in zip(logits, outcomes)) / n
        scale += learning_rate * gradient
    return scale
