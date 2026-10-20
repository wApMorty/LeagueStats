"""Écran Calibration du client (SPEC-21 tâche 54) : versions du modèle jamais mélangées, refus sous le
minimum, mêmes Brier et n que `scripts/calibrate_model.py`."""

import importlib.util
import json
import re
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import escape

from src.analysis.calibration import (
    brier_score,
    fetch_labeled_predictions,
    scale_interval,
    suggest_scale,
)
from src.calibration_overrides import next_version
from src.client.app import create_app
from src.client.bus import EventBus
from src.client.data import calibration_empty, calibration_view, phase_reason
from src.client.donnees import _reason
from src.config_client import client_config
from src.config_constants import analysis_config
from src.draft import calibration_notice
from src.repositories.coaching import CoachingRepository
from tests.test_analysis_calibration import _lcg_rows
from tests.test_calibration_apply import _rows

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


# ---------- diagnostic et « Appliquer » ----------


def _signed_fr(value, digits=2):
    return ("−" if value < 0 else "") + f"{abs(value):.{digits}f}".replace(".", ",")


def test_facteur_et_intervalle_egaux_au_diagnostic(db):
    rows = _lcg_rows(MINIMUM + 50)
    predictions(db, CURRENT, rows)
    view = calibration_view(CoachingRepository(db), None)
    low, high = scale_interval(
        rows, analysis_config.CALIBRATION_CI_CONFIDENCE, analysis_config.CALIBRATION_CI_RESAMPLES
    )
    assert view["scale"] == f"{suggest_scale(rows):.3f}".replace(".", ",")
    assert view["interval"] == f"[{_signed_fr(low)} ; {_signed_fr(high)}]"
    assert view["confidence"] == "90 %"


def test_version_ancienne_sans_suggestion_et_sans_appliquer(db):
    predictions(db, "b7-v1", _lcg_rows(MINIMUM + 10))
    view = calibration_view(CoachingRepository(db), "b7-v1", "closed")
    assert view["scale"] is not None and view["interval"] is not None
    assert view["suggested"] is None
    assert view["can_apply"] is False
    assert view["apply_reason"].startswith("Seule la version courante")


@pytest.mark.parametrize("phase_kind", ["draft", "game"])
def test_phase_de_jeu_grise_appliquer_meme_si_le_diagnostic_propose(db, phase_kind):
    predictions(db, CURRENT, _rows(400, 0.4))
    view = calibration_view(CoachingRepository(db), None, phase_kind)
    assert view["apply_reason"] == phase_reason(phase_kind)
    assert view["can_apply"] is False and view["proposal"] is None


def test_diagnostic_qui_propose_permet_appliquer_hors_partie(db):
    predictions(db, CURRENT, _rows(400, 0.4))
    view = calibration_view(CoachingRepository(db), None, "closed")
    assert view["can_apply"] is True and view["apply_reason"] is None
    assert view["proposal"] is not None
    assert view["suggested"]["version"] == f"{CURRENT} → {next_version(CURRENT)}"


def test_diagnostic_qui_refuse_donne_sa_raison(db):
    predictions(db, CURRENT, _lcg_rows(MINIMUM + 50))
    view = calibration_view(CoachingRepository(db), None, "closed")
    assert view["can_apply"] is False
    assert view["apply_reason"] is not None and view["proposal"] is None


def test_phase_reason_textes_et_rien_hors_draft_ou_partie():
    assert phase_reason("draft") == "Sélection des champions en cours"
    assert phase_reason("game") == "Partie en cours"
    assert phase_reason("closed") is None


def test_reason_de_donnees_inchangee():
    assert _reason(True, "closed") == "Mise à jour en cours"
    assert _reason(False, "draft") == "Sélection des champions en cours"
    assert _reason(False, "closed") is None


# ---------- route « Appliquer » (SPEC-39 tâche 192) ----------


@pytest.fixture
def reglage(monkeypatch, tmp_path):
    """Fichier de calibration redirigé vers tmp_path ; K et version restaurés après le test."""
    from src import calibration_overrides as overrides

    monkeypatch.setattr(
        overrides, "get_calibration_path", lambda: str(tmp_path / "calibration.json")
    )
    for name in ("K_MATCHUP", "K_SYNERGY", "MODEL_VERSION"):
        monkeypatch.setattr(analysis_config, name, getattr(analysis_config, name))
    return tmp_path / "calibration.json"


def web_en_phase(temp_db, kind):
    bus = EventBus()
    bus.publish("phase", {"kind": kind})
    return TestClient(create_app(temp_db, bus=bus), base_url=LOCAL, raise_server_exceptions=False)


def _jeton(web):
    return {client_config.TOKEN_HEADER: web.app.state.session_token}


def test_page_diagnostic_facteur_et_bouton_grise(db, temp_db):
    rows = _rows(400, 1.0)
    predictions(db, CURRENT, rows)
    page = client(temp_db).get("/calibration").text
    view = calibration_view(CoachingRepository(db), None, "closed")
    assert "Facteur d'échelle" in page and view["scale"] in page
    tag = re.search(r'<button[^>]*class="btn-primary calib-apply"[^>]*>', page).group(0)
    assert "disabled" in tag and not view["can_apply"]
    assert str(escape(view["apply_reason"])) in page


def test_la_cible_porte_le_garde_htmx_des_409_et_500(db, temp_db):
    """htmx:beforeSwap est émis sur la cible (#calib), pas sur le bouton : le garde y vit."""
    predictions(db, CURRENT, _rows(400, 0.4))
    page = client(temp_db).get("/calibration").text
    target = re.search(r'<div id="calib"[^>]*>', page).group(0)
    assert 'hx-on:htmx:before-swap="if([409,500].includes(event.detail.xhr.status))' in target


@pytest.mark.parametrize("phase_kind", ["draft", "game"])
def test_la_page_grise_appliquer_en_phase_de_jeu(db, temp_db, phase_kind):
    """GET /calibration lit la phase du bus : en draft ou en partie le bouton est grisé d'emblée."""
    predictions(db, CURRENT, _rows(400, 0.4))
    page = web_en_phase(temp_db, phase_kind).get("/calibration").text
    tag = re.search(r'<button[^>]*class="btn-primary calib-apply"[^>]*>', page).group(0)
    assert "disabled" in tag and phase_reason(phase_kind) in page


@pytest.mark.parametrize("phase_kind", ["draft", "game"])
def test_appliquer_refuse_en_phase_de_jeu(db, temp_db, reglage, phase_kind):
    predictions(db, CURRENT, _rows(400, 0.4))
    web = web_en_phase(temp_db, phase_kind)
    response = web.post("/calibration/appliquer", headers=_jeton(web))
    assert response.status_code == 409
    assert phase_reason(phase_kind) in response.text and not reglage.exists()


@pytest.mark.parametrize("rows", [lambda: _rows(400, 1.0), lambda: _lcg_rows(MINIMUM + 50)])
def test_appliquer_refuse_quand_le_diagnostic_refuse(db, temp_db, reglage, rows):
    data = rows()
    predictions(db, CURRENT, data)
    web = client(temp_db)
    response = web.post("/calibration/appliquer", headers=_jeton(web))
    reason = calibration_view(CoachingRepository(db), None, "closed")["apply_reason"]
    assert response.status_code == 409 and not reglage.exists()
    assert str(escape(reason)) in response.text


def test_appliquer_sans_jeton_403(db, temp_db, reglage):
    predictions(db, CURRENT, _rows(400, 0.4))
    response = client(temp_db).post("/calibration/appliquer")
    assert response.status_code == 403 and not reglage.exists()


def test_appliquer_ecrit_le_reglage_et_le_retient(db, temp_db, reglage):
    rows = _rows(400, 0.4)
    predictions(db, CURRENT, rows)
    old_matchup, old_synergy = analysis_config.K_MATCHUP, analysis_config.K_SYNERGY
    scale = suggest_scale(rows)
    web = client(temp_db)
    response = web.post("/calibration/appliquer", headers=_jeton(web))
    assert response.status_code == 200
    saved = json.loads(reglage.read_text(encoding="utf-8"))
    assert saved["K_MATCHUP"] == pytest.approx(old_matchup * scale)
    assert saved["K_SYNERGY"] == pytest.approx(old_synergy * scale)
    assert saved["MODEL_VERSION"] == f"{CURRENT}+cal1"
    assert analysis_config.MODEL_VERSION == f"{CURRENT}+cal1"
    assert "Réglage appliqué" in response.text


def test_ecriture_impossible_500_sans_changement(db, temp_db, reglage, monkeypatch):
    predictions(db, CURRENT, _rows(400, 0.4))
    monkeypatch.setattr(calibration_notice, "save_overrides", lambda *args, **kwargs: False)
    before = (analysis_config.K_MATCHUP, analysis_config.K_SYNERGY, analysis_config.MODEL_VERSION)
    web = client(temp_db)
    response = web.post("/calibration/appliquer", headers=_jeton(web))
    assert response.status_code == 500
    assert "Écriture de calibration.json impossible" in response.text
    assert (
        analysis_config.K_MATCHUP,
        analysis_config.K_SYNERGY,
        analysis_config.MODEL_VERSION,
    ) == before
    assert not reglage.exists()
