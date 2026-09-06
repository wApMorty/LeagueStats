"""Calibration diagnostic for the log-odds scoring model (SPEC-05 B7).

Reads the `predictions` table (rows with a known `outcome`, logged
automatically since SPEC-08 via the LCU match history, or manually via the
draft coach's "outcome win"/"outcome loss" command -- see
src/draft/outcome_tracker.py and src/draft_monitor.py) and reports:

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

The core math lives in src/analysis/calibration.py (SPEC-12), shared with
the live Draft Coach's own auto-triggered summary
(src/draft/calibration_notice.py) -- this script is a thin CLI wrapper.

USAGE:
    python scripts/calibrate_model.py
    python scripts/calibrate_model.py --db-path data/db.db
    python scripts/calibrate_model.py --all-versions   # don't filter by MODEL_VERSION
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.calibration import (
    brier_score,
    calibration_curve,
    fetch_labeled_predictions,
    suggest_scale,
)
from src.config import config
from src.config_constants import analysis_config
from src.db import Database


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
        rows = fetch_labeled_predictions(db, model_version)
    finally:
        db.close()

    version_note = "all model versions" if args.all_versions else f"model_version={model_version!r}"
    print(f"[CALIBRATE] {len(rows)} labeled predictions ({version_note}).")

    if len(rows) < analysis_config.MIN_ROWS_FOR_CALIBRATION:
        print(
            f"[CALIBRATE] Not enough data yet "
            f"({len(rows)} < {analysis_config.MIN_ROWS_FOR_CALIBRATION}). "
            "Play more games before trusting anything below -- outcomes are now logged "
            "automatically (SPEC-08), or manually with 'outcome win'/'outcome loss' during "
            "the draft coach session; this is a diagnostic script, not a source of truth "
            "on a handful of games."
        )
        return

    print("\n[CALIBRATE] Calibration curve (predicted vs observed win rate, by decile):")
    print(calibration_curve(rows))

    brier = brier_score(rows)
    print(f"\n[CALIBRATE] Brier score: {brier:.4f} (0 = perfect, 0.25 = always predicting 50%)")

    scale = suggest_scale(rows)
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
