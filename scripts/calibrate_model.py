"""Calibration diagnostic for the log-odds scoring model (SPEC-05 B7).

Reads the `predictions` table (rows with a known `outcome`, logged via the
draft coach's manual "outcome win"/"outcome loss" command -- see
src/draft_monitor.py) and reports:

    1. A calibration curve by decile: among drafts predicted at ~60%, do we
       actually win ~60% of them?
    2. The Brier score (mean squared error between predicted probability and
       actual outcome).
    3. A simple suggested adjustment to k_m/k_s, from a hand-rolled
       1-parameter logistic recalibration (Platt scaling, no intercept) --
       no new dependency (scipy/sklearn/numpy are explicitly out of scope,
       see SPEC-05 section 8 "Hors périmètre").

This is a read-only diagnostic script: it never writes back to the database
or to config_constants.py. Applying a suggested k_m/k_s is a manual decision
(and must come with a MODEL_VERSION bump, see config_constants.py).

USAGE:
    python scripts/calibrate_model.py
    python scripts/calibrate_model.py --db-path data/db.db
    python scripts/calibrate_model.py --all-versions   # don't filter by MODEL_VERSION
"""

import argparse
import math
import sys
from pathlib import Path
from typing import List, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import config
from src.config_constants import analysis_config
from src.db import Database

# Below this many labeled predictions, a calibration curve or a suggested
# k_m/k_s is noise, not signal -- SPEC-05 §4 B7 step 5: "à n'écrire qu'une
# fois assez de données accumulées".
MIN_ROWS_FOR_CALIBRATION = 30

Row = Tuple[float, int]  # (predicted_probability, outcome)


def _fetch_labeled_predictions(db: Database, model_version: str = None) -> List[Row]:
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


def _calibration_curve(rows: List[Row]) -> str:
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


def _brier_score(rows: List[Row]) -> float:
    """Mean((predicted_probability - outcome)^2). 0 = perfect, 0.25 = always predicting 50%."""
    return sum((p - o) ** 2 for p, o in rows) / len(rows)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _suggest_scale(rows: List[Row], learning_rate: float = 0.1, iterations: int = 500) -> float:
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SPEC-05 B7: calibration diagnostic for the log-odds scoring model"
    )
    parser.add_argument(
        "--db-path",
        default=config.DATABASE_PATH,
        help=f"Path to the SQLite database (default: {config.DATABASE_PATH})",
    )
    parser.add_argument(
        "--all-versions",
        action="store_true",
        help="Don't filter by the current MODEL_VERSION (mixes predictions from "
        "different model iterations -- only useful to eyeball total row count)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    db = Database(args.db_path)
    db.connect()
    try:
        model_version = None if args.all_versions else analysis_config.MODEL_VERSION
        rows = _fetch_labeled_predictions(db, model_version)
    finally:
        db.close()

    version_note = "all model versions" if args.all_versions else f"model_version={model_version!r}"
    print(f"[CALIBRATE] {len(rows)} labeled predictions ({version_note}).")

    if len(rows) < MIN_ROWS_FOR_CALIBRATION:
        print(
            f"[CALIBRATE] Not enough data yet ({len(rows)} < {MIN_ROWS_FOR_CALIBRATION}). "
            "Play more games and log outcomes with 'outcome win'/'outcome loss' during "
            "the draft coach session before trusting anything below -- this is a "
            "diagnostic script, not a source of truth on a handful of games."
        )
        return

    print("\n[CALIBRATE] Calibration curve (predicted vs observed win rate, by decile):")
    print(_calibration_curve(rows))

    brier = _brier_score(rows)
    print(f"\n[CALIBRATE] Brier score: {brier:.4f} (0 = perfect, 0.25 = always predicting 50%)")

    scale = _suggest_scale(rows)
    print(f"\n[CALIBRATE] Suggested log-odds scale factor: {scale:.3f}")
    if abs(scale - 1.0) < 0.05:
        print("[CALIBRATE] Close to 1.0 -- current k_m/k_s look reasonably calibrated.")
    else:
        k_m_suggested = analysis_config.K_MATCHUP * scale
        k_s_suggested = analysis_config.K_SYNERGY * scale
        direction = (
            "more confident (further from 50%)" if scale > 1.0 else "more cautious (closer to 50%)"
        )
        print(
            f"[CALIBRATE] Predictions should be {direction}. As a starting point: "
            f"k_m {analysis_config.K_MATCHUP:.2f} -> {k_m_suggested:.2f}, "
            f"k_s {analysis_config.K_SYNERGY:.2f} -> {k_s_suggested:.2f} (uniform scaling -- "
            "this script can't separate the matchup and synergy contributions from a "
            "stored predicted_probability alone; treat this as a starting point for "
            "manual tuning, not a final answer)."
        )

    print(
        f"\n[CALIBRATE] If you apply any of this, bump analysis_config.MODEL_VERSION "
        f"(currently {analysis_config.MODEL_VERSION!r}) so future predictions aren't "
        "mixed with this calibration's."
    )


if __name__ == "__main__":
    main()
