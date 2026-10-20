"""Écran Données du client (SPEC-37 tâche 183) : `UpdateJob` avec un faux `run`, et la vue pure.

Aucun vrai pipeline : le faux `run` rejoue des événements et se synchronise par `threading.Event`
(jamais de `time.sleep`). Les fils sont attendus par `job.cancel(...)`, qui joint le fil.
"""

import logging
import re
import sqlite3
import threading
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.assets import Assets
from src.client.bus import EventBus
from src.client.donnees import UpdateJob, donnees_view, last_scrape_lanes
from src.config_client import client_config
from src.data_freshness import FreshnessInfo
from src.pipeline import PipelineResult

WAIT_S = 5.0
LOCAL = "http://127.0.0.1"
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class _Clock:
    """Horloge factice : `now` se règle à la main."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _end(job: UpdateJob) -> None:
    """Attend la fin du fil du job (le signal d'arrêt n'a ici aucun effet sur le faux run)."""
    assert job.cancel(WAIT_S)


def test_snapshot_lanes_et_current():
    replayed, release = threading.Event(), threading.Event()

    def run(progress, stop):
        progress({"step": "plan", "lanes": {"top": 3, "jungle": 2}})
        progress({"step": "start", "lane": "top", "champion": "Ahri"})
        progress({"step": "start", "lane": "top", "champion": "Zed"})
        progress({"step": "done", "lane": "top", "champion": "Ahri", "ok": True})
        replayed.set()
        release.wait(WAIT_S)
        return PipelineResult(status="ok")

    job = UpdateJob(run=run, clock=_Clock())
    assert job.start() is None
    assert replayed.wait(WAIT_S)
    snap = job.snapshot()
    assert snap["lanes"][0] == {
        "lane": "top",
        "done": 1,
        "total": 3,
        "failed": 0,
        "current": ["Zed"],
    }
    assert snap["state"] == "running"
    release.set()
    _end(job)


def test_done_en_echec_compte_failed():
    replayed, release = threading.Event(), threading.Event()

    def run(progress, stop):
        progress({"step": "plan", "lanes": {"top": 2}})
        progress({"step": "start", "lane": "top", "champion": "Ahri"})
        progress({"step": "done", "lane": "top", "champion": "Ahri", "ok": False})
        replayed.set()
        release.wait(WAIT_S)
        return PipelineResult(status="partial")

    job = UpdateJob(run=run, clock=_Clock())
    job.start()
    assert replayed.wait(WAIT_S)
    lane = job.snapshot()["lanes"][0]
    assert lane["failed"] == 1
    assert lane["done"] == 1
    release.set()
    _end(job)


def test_eta_seuil_puis_extrapolation():
    clock = _Clock()
    at_four, go, replayed, release = (threading.Event() for _ in range(4))

    def run(progress, stop):
        progress({"step": "plan", "lanes": {"top": 6, "jungle": 4}})
        for champion in ("Ahri", "Zed", "Lux", "Vi"):
            progress({"step": "done", "lane": "top", "champion": champion, "ok": True})
        clock.now = 40.0
        at_four.set()
        go.wait(WAIT_S)
        clock.now = 50.0
        progress({"step": "done", "lane": "jungle", "champion": "Lee Sin", "ok": True})
        replayed.set()
        release.wait(WAIT_S)
        return PipelineResult(status="ok")

    job = UpdateJob(run=run, clock=clock)
    job.start()
    assert at_four.wait(WAIT_S)
    assert job.snapshot()["eta_s"] is None
    go.set()
    assert replayed.wait(WAIT_S)
    assert job.snapshot()["eta_s"] == 50
    release.set()
    _end(job)


def test_second_start_refuse_puis_relance():
    release = threading.Event()

    def run(progress, stop):
        release.wait(WAIT_S)
        return PipelineResult(status="ok")

    job = UpdateJob(run=run, clock=_Clock())
    assert job.start() is None
    assert job.running
    assert job.start() == "Mise à jour déjà en cours"
    release.set()
    _end(job)
    assert not job.running
    assert job.start() is None
    _end(job)


def test_logging_restaure_apres_run():
    root = logging.getLogger()

    def run(progress, stop):
        root.handlers[:] = [logging.NullHandler()]
        root.setLevel(logging.DEBUG)
        return PipelineResult(status="ok")

    handlers_before, level_before = list(root.handlers), root.level
    job = UpdateJob(run=run, clock=_Clock())
    job.start()
    _end(job)
    assert root.handlers == handlers_before
    assert root.level == level_before


def test_run_qui_leve_passe_en_failed():
    def run(progress, stop):
        raise RuntimeError("boom")

    job = UpdateJob(run=run, clock=_Clock())
    job.start()
    _end(job)
    snap = job.snapshot()
    assert snap["state"] == "failed"
    assert snap["error"] == "RuntimeError: boom"
    assert not job.running


def test_cancel_arrete_le_run():
    seen = []

    def run(progress, stop):
        seen.append(stop.wait(WAIT_S))
        return PipelineResult(status="failed", error="Interrompu")

    job = UpdateJob(run=run, clock=_Clock())
    job.start()
    assert job.cancel(1.0)
    assert seen == [True]
    snap = job.snapshot()
    assert snap["state"] == "failed"
    assert snap["error"] == "Interrompu"


def test_last_scrape_lanes_tolerant():
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE db_meta (key TEXT PRIMARY KEY, value TEXT)")
        connection.execute(
            "INSERT INTO db_meta VALUES (?, ?)",
            (
                "last_scrape_lanes",
                '{"top": {"success": 90, "failed": 0, "total": 90, "duration_s": 1080}}',
            ),
        )
        assert last_scrape_lanes(connection)["top"]["success"] == 90
        connection.execute(
            "UPDATE db_meta SET value = ? WHERE key = ?", ("{pas du json", "last_scrape_lanes")
        )
        assert last_scrape_lanes(connection) == {}
    finally:
        connection.close()

    connection = sqlite3.connect(":memory:")
    try:
        assert last_scrape_lanes(connection) == {}
    finally:
        connection.close()


def test_donnees_view_etats_et_libelles():
    idle = {
        "state": "idle",
        "step": "idle",
        "detail": "",
        "lanes": [],
        "started_at": 0.0,
        "elapsed_s": 0.0,
        "eta_s": None,
        "error": None,
        "report": "",
    }
    fresh = FreshnessInfo(
        last_update=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
        matchups_count=57612,
        synergies_count=50495,
        scrape_status="ok",
    )
    lanes = {"top": {"success": 90, "failed": 0, "total": 90, "duration_s": 1080}}

    view = donnees_view(idle, fresh, lanes, "draft", NOW)
    assert view["can_start"] is False
    assert view["reason"] == "Sélection des champions en cours"
    assert view["elapsed"] is None
    assert view["last"]["when"] == "6 oct. (il y a 14 j)"
    assert view["last"]["status"] == "OK"
    assert view["last"]["matchups"] == "57 612"
    assert view["last"]["lanes"] == [{"label": "Top", "text": "90/90 en 18 min, 0 échec"}]

    view = donnees_view(idle, fresh, lanes, "game", NOW)
    assert view["can_start"] is False
    assert view["reason"] == "Partie en cours"

    view = donnees_view(idle, fresh, lanes, "closed", NOW)
    assert view["can_start"] is True
    assert view["reason"] is None
    assert view["outcome"] is None

    running = dict(idle, state="running", step="plan", elapsed_s=720.0, eta_s=2040.0)
    view = donnees_view(running, fresh, lanes, "closed", NOW)
    assert view["running"] is True
    assert view["can_start"] is False
    assert view["reason"] == "Mise à jour en cours"
    assert view["elapsed"] == "12 min"
    assert view["eta"] == "≈ 34 min restantes"
    assert view["step"] == "Scrape"

    lanes_running = dict(
        running,
        lanes=[{"lane": "middle", "done": 1, "total": 2, "failed": 0, "current": ["Ahri", "Zed"]}],
    )
    view = donnees_view(lanes_running, fresh, {}, "closed", NOW)
    assert view["lanes"] == [
        {"label": "Mid", "done": 1, "total": 2, "failed": 0, "current": "Ahri, Zed"}
    ]
    preparing = dict(running, step="preparation", detail="Découverte des lanes")
    assert donnees_view(preparing, fresh, {}, "closed", NOW)["step"] == (
        "Préparation : Découverte des lanes"
    )

    never = FreshnessInfo()
    view = donnees_view(idle, never, {}, "closed", NOW)
    assert view["last"]["when"] == "Jamais"
    assert view["last"]["status"] == "Inconnu"


# ---------- écran Données et bandeau du draft (tâche 184) ----------


def _token(web):
    return {client_config.TOKEN_HEADER: web.app.state.session_token}


def _web(temp_db, tmp_path, job, bus=None):
    assets = Assets(tmp_path / "cache", fetch=lambda url: None)
    app = create_app(temp_db, bus=bus, assets=assets, update_job=job)
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def _quick_job(calls=None):
    """Faux run qui rend « ok » aussitôt ; `calls` note ses appels."""

    def run(progress, stop):
        if calls is not None:
            calls.append(1)
        return PipelineResult(status="ok")

    return UpdateJob(run=run, clock=_Clock())


def test_page_donnees_et_lien_actif(temp_db, tmp_path):
    web = _web(temp_db, tmp_path, _quick_job())
    response = web.get("/donnees")
    page = response.text
    assert response.status_code == 200
    assert "Actualiser" in page and "Dernier passage" in page
    assert re.search(r'href="/donnees"[^>]*aria-current="page"', page)


def test_etat_sans_run_pas_de_sondage_puis_pendant_un_run(temp_db, tmp_path):
    replayed, release = threading.Event(), threading.Event()

    def run(progress, stop):
        progress({"step": "plan", "lanes": {"top": 3}})
        replayed.set()
        release.wait(WAIT_S)
        return PipelineResult(status="ok")

    job = UpdateJob(run=run, clock=_Clock())
    web = _web(temp_db, tmp_path, job)
    assert 'hx-trigger="every' not in web.get("/donnees/etat").text

    job.start()
    assert replayed.wait(WAIT_S)
    during = web.get("/donnees/etat").text
    assert 'hx-trigger="every' in during
    assert "0/3" in during
    release.set()
    _end(job)


@pytest.mark.parametrize(
    "phase, status, started",
    [("draft", 409, False), ("game", 409, False), ("closed", 200, True)],
)
def test_lancement_selon_la_phase(temp_db, tmp_path, phase, status, started):
    calls = []
    bus = EventBus()
    bus.publish("phase", {"kind": phase})
    job = _quick_job(calls)
    web = _web(temp_db, tmp_path, job, bus)
    response = web.post("/donnees/actualiser", headers=_token(web))
    assert response.status_code == status
    _end(job)
    assert calls == ([1] if started else [])


def test_post_sans_jeton_refuse(temp_db, tmp_path):
    calls = []
    job = _quick_job(calls)
    web = _web(temp_db, tmp_path, job)
    assert web.post("/donnees/actualiser").status_code == 403
    _end(job)
    assert calls == []


def test_bandeau_du_draft_pendant_un_run_seulement(temp_db, tmp_path):
    release = threading.Event()

    def run(progress, stop):
        release.wait(WAIT_S)
        return PipelineResult(status="ok")

    job = UpdateJob(run=run, clock=_Clock())
    web = _web(temp_db, tmp_path, job)
    assert 'class="draft-updating"' not in web.get("/draft/stage").text

    job.start()
    during = web.get("/draft/stage").text
    assert 'class="draft-updating"' in during
    assert 'data-key="updating"' in during and 'data-sig="updating"' in during
    release.set()
    _end(job)
    assert 'class="draft-updating"' not in web.get("/draft/stage").text
