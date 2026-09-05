"""Auto-triggered calibration summary surfaced in the live Draft Coach
console (SPEC-12).

Fires from OutcomeTracker.resolve_pending() whenever the count of predictions
labelled under the current MODEL_VERSION crosses
analysis_config.MIN_ROWS_FOR_CALIBRATION for the first time, or a further
multiple of analysis_config.AUTO_CALIBRATION_CHECK_INTERVAL past it -- so the
diagnostic self-paces on actual play instead of a wall-clock schedule (a
scheduled task would run mute for weeks before the first 30 games, then nag
identically after every single game once past it).

The standalone `python scripts/calibrate_model.py` CLI stays available
separately (English output, --all-versions) for an on-demand full read; this
module owns only the live-console French summary and the crossing detection,
reusing the same math from src/analysis/calibration.py.
"""

from typing import Optional

from ..analysis.calibration import (
    brier_score,
    calibration_curve,
    fetch_labeled_predictions,
    suggest_scale,
)
from ..config_constants import analysis_config


def should_trigger(before_count: int, after_count: int) -> bool:
    """True if going from before_count to after_count labelled predictions
    (under the current model version) crosses MIN_ROWS_FOR_CALIBRATION, or a
    later multiple of AUTO_CALIBRATION_CHECK_INTERVAL past it.

    A batch that resolves several predictions at once (e.g. the startup
    backfill) can jump over more than one multiple in a single call -- this
    still fires exactly once, showing the up-to-date total, rather than once
    per skipped multiple.
    """
    threshold = analysis_config.MIN_ROWS_FOR_CALIBRATION
    interval = analysis_config.AUTO_CALIBRATION_CHECK_INTERVAL
    if after_count < threshold:
        return False
    if before_count < threshold:
        return True
    return (before_count - threshold) // interval != (after_count - threshold) // interval


def format_summary(db, model_version: str) -> Optional[str]:
    """French summary for the live console, or None if there isn't actually
    enough data (defensive: should_trigger() already gates the call site)."""
    rows = fetch_labeled_predictions(db, model_version)
    if len(rows) < analysis_config.MIN_ROWS_FOR_CALIBRATION:
        return None

    brier = brier_score(rows)
    scale = suggest_scale(rows)

    lines = [
        f"[CALIBRATE] {len(rows)} prédictions labellisées (model_version={model_version!r}) "
        "-- diagnostic automatique :",
        calibration_curve(rows),
        f"[CALIBRATE] Score de Brier : {brier:.4f} (0 = parfait, 0.25 = toujours 50 %)",
    ]

    if abs(scale - 1.0) < 0.05:
        lines.append(
            "[CALIBRATE] Facteur d'échelle suggéré proche de 1.0 -- K_MATCHUP/K_SYNERGY "
            "semblent raisonnablement calibrés."
        )
    else:
        direction = "plus confiant" if scale > 1.0 else "plus prudent"
        k_m_suggested = analysis_config.K_MATCHUP * scale
        k_s_suggested = analysis_config.K_SYNERGY * scale
        lines.append(
            f"[CALIBRATE] Facteur d'échelle suggéré : {scale:.3f} -- le modèle devrait être "
            f"{direction}. Piste de départ : K_MATCHUP {analysis_config.K_MATCHUP:.2f} -> "
            f"{k_m_suggested:.2f}, K_SYNERGY {analysis_config.K_SYNERGY:.2f} -> "
            f"{k_s_suggested:.2f} (mise à l'échelle uniforme -- décision manuelle)."
        )

    lines.append(
        "[CALIBRATE] Diagnostic en lecture seule -- rien n'est modifié automatiquement. "
        "Pour l'analyse complète : python scripts/calibrate_model.py "
        "(bump MODEL_VERSION si vous appliquez un ajustement)."
    )
    return "\n".join(lines)
