"""Écran Calibration du client (SPEC-21 tâche 54) : versions du modèle jamais mélangées, refus sous le
minimum, mêmes Brier et n que `scripts/calibrate_model.py`."""

import importlib.util
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.analysis.calibration import brier_score, fetch_labeled_predictions
from src.client.app import create_app
from src.client.data import calibration_empty, calibration_view
from src.config_constants import analysis_config
from src.repositories.coaching import CoachingRepository
from tests.test_analysis_calibration import _lcg_rows

LOCAL = "http://127.0.0.1"
CURRENT = analysis_config.MODEL_VERSION
MINIMUM = analysis_config.MIN_ROWS_FOR_CALIBRATION


def client(temp_db):
    return TestClient(create_app(temp_db), base_url=LOCAL, raise_server_exceptions=False)


def predictions(db, version, rows):
    """Prédictions dont l'issue est connue (saisie manuelle : pas de partie rattachée)."""
    for probability, outcome in rows:
        prediction_id = db.insert_prediction([1], [2], None, probability, version)
        db.update_prediction_outcome(prediction_id, outcome)


# ---------- données ----------


def test_base_vide():
    view = calibration_empty()
    assert view["empty"] and view["versions"] == [] and view["chart"] is None


def test_sous_le_minimum_le_meme_refus_que_la_console(db):
    predictions(db, CURRENT, _lcg_rows(MINIMUM - 1))
    view = calibration_view(CoachingRepository(db), None)
    assert not view["empty"] and not view["enough"]
    assert (view["n"], view["minimum"]) == (MINIMUM - 1, MINIMUM)
    assert view["chart"] is None and view["table"] == []


def test_meme_brier_et_meme_n_que_la_console(db):
    rows = _lcg_rows(80)
    predictions(db, CURRENT, rows)
    view = calibration_view(CoachingRepository(db), None)
    assert view["enough"] and view["n"] == 80
    assert view["brier_value"] == pytest.approx(brier_score(rows))
    assert view["brier"] == f"{brier_score(rows):.4f}".replace(".", ",")
    assert str(view["chart"]).count("<circle") == 10  # une classe non vide = un point
    assert [r["n"] for r in view["table"]][:3] == [12, 10, 10]
    assert view["table"][0] == {
        "range": "0 à 10 %",
        "n": 12,
        "predicted": "5,6 %",
        "observed": "25,0 %",
    }


def test_les_versions_ne_se_melangent_jamais(db):
    predictions(db, CURRENT, _lcg_rows(40))
    predictions(db, "b7-v1", _lcg_rows(35)[::-1])
    repo = CoachingRepository(db)
    default = calibration_view(repo, None)
    assert default["version"] == CURRENT and default["n"] == 40
    assert [(v["name"], v["count"], v["on"]) for v in default["versions"]] == [
        (CURRENT, 40, True),
        ("b7-v1", 35, False),
    ]
    other = calibration_view(repo, "b7-v1")
    assert other["version"] == "b7-v1" and other["n"] == 35
    assert other["brier_value"] == pytest.approx(
        brier_score(fetch_labeled_predictions(db, "b7-v1"))
    )
    assert other["brier_value"] != default["brier_value"]


def test_version_inconnue_retombe_sur_la_courante_puis_la_plus_fournie(db):
    predictions(db, "ancienne", _lcg_rows(50))
    repo = CoachingRepository(db)
    assert calibration_view(repo, "n'existe pas")["version"] == "ancienne"  # la courante n'a rien
    predictions(db, CURRENT, _lcg_rows(31))
    assert calibration_view(repo, "n'existe pas")["version"] == CURRENT


def test_les_predictions_sans_issue_ne_comptent_pas(db):
    predictions(db, CURRENT, _lcg_rows(MINIMUM))
    for _ in range(5):
        db.insert_prediction([1], [2], None, 0.5, CURRENT)  # issue inconnue
    assert calibration_view(CoachingRepository(db), None)["n"] == MINIMUM


# ---------- route ----------


def test_route_sur_base_vide_repond_200(temp_db):
    response = client(temp_db).get("/calibration")
    assert (
        response.status_code == 200 and "Aucune prédiction avec une issue connue" in response.text
    )


def test_route_sur_base_non_migree_repond_200(tmp_path):
    path = tmp_path / "vide.db"
    sqlite3.connect(path).close()
    assert client(path).get("/calibration").status_code == 200


def test_route_sous_le_minimum(db, temp_db):
    predictions(db, CURRENT, _lcg_rows(10))
    page = client(temp_db).get("/calibration").text
    assert f"10 prédictions sur {MINIMUM} nécessaires" in page and '<svg class="chart"' not in page


def test_route_diagramme_et_choix_de_version(db, temp_db):
    predictions(db, CURRENT, _lcg_rows(60))
    predictions(db, "b7-v1+lane-restante", _lcg_rows(40))
    web = client(temp_db)
    page = web.get("/calibration").text
    assert page.count('class="ch-dot ch-dot-solid"') >= 5 and "Score de Brier" in page
    assert page.count('class="role-chip"') == 2
    assert "version=b7-v1%2Blane-restante" in page  # le « + » est encodé
    other = web.get("/calibration", params={"version": "b7-v1+lane-restante"}).text
    assert "40 prédictions" in other and "b7-v1+lane-restante" in other


def test_route_meme_brier_et_n_que_calibrate_model(db, temp_db, capsys):
    rows = _lcg_rows(80)
    predictions(db, CURRENT, rows)
    path = Path(__file__).parent.parent / "scripts" / "calibrate_model.py"
    spec = importlib.util.spec_from_file_location("calibrate_model_script", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    import sys

    old, sys.argv = sys.argv, ["calibrate_model.py", "--db-path", str(temp_db)]
    try:
        script.main()
    finally:
        sys.argv = old
    printed = capsys.readouterr().out
    console_n = int(re.search(r"(\d+) labeled predictions", printed).group(1))
    console_brier = re.search(r"Brier score: (\d\.\d{4})", printed).group(1)
    page = client(temp_db).get("/calibration").text
    assert console_n == 80
    assert console_brier.replace(".", ",") in page and f"{console_n} prédictions" in page


def test_la_consultation_n_ecrit_pas_dans_la_base(db, temp_db):
    predictions(db, CURRENT, _lcg_rows(60))
    before = (temp_db.stat().st_mtime_ns, temp_db.read_bytes())
    assert client(temp_db).get("/calibration").status_code == 200
    assert (temp_db.stat().st_mtime_ns, temp_db.read_bytes()) == before
