"""Écran Données du client (SPEC-37 tâche 183) : `UpdateJob` avec un faux `run`, et la vue pure.

Aucun vrai pipeline : le faux `run` rejoue des événements et se synchronise par `threading.Event`
(jamais de `time.sleep`). Les fils sont attendus par `job.cancel(...)`, qui joint le fil.
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone

from src.client.donnees import UpdateJob, donnees_view, last_scrape_lanes
from src.data_freshness import FreshnessInfo
from src.pipeline import PipelineResult

WAIT_S = 5.0
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
