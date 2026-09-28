"""Régression (2026-09-29) : scripts/calibrate_model.py ne voyait aucune partie
dès qu'il y en avait assez.

Remonté par @pj35 : 34 prédictions labellisées sous spec13-v1, mais le script
cherchait « spec13-v1+lane-restante » et n'en trouvait aucune. Il filtrait sur
effective_model_version(), qui ajoute ce suffixe dès que le garde-fou SPEC-11
s'ouvre (MIN_ROWS_FOR_CALIBRATION parties), alors que depuis SPEC-12 les
prédictions sont journalisées sous MODEL_VERSION seul
(src/draft/final_analysis.py). Le script fonctionnait donc sous le seuil, et
cessait de fonctionner exactement au moment où il devenait utile.
"""

import importlib.util
import sys
from pathlib import Path

from src.config_constants import analysis_config

SCRIPT = Path(__file__).parents[2] / "scripts" / "calibrate_model.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("calibrate_model", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_calibration_finds_the_games_logged_under_the_current_model(
    db, temp_db, monkeypatch, capsys
):
    count = analysis_config.MIN_ROWS_FOR_CALIBRATION + 4
    for index in range(count):
        prediction_id = db.insert_prediction(
            [1, 2], [3, 4], None, 0.55, analysis_config.MODEL_VERSION
        )
        db.update_prediction_outcome(prediction_id, index % 2)

    monkeypatch.setattr(sys, "argv", ["calibrate_model.py", "--db-path", str(temp_db)])
    _load_script().main()

    out = capsys.readouterr().out
    assert f"{count} labeled predictions" in out
    assert f"model_version={analysis_config.MODEL_VERSION!r}" in out
