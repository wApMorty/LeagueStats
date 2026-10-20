"""Écran Données du client (SPEC-37) : une mise à jour à la fois dans un fil daemon, son état et sa vue.

`UpdateJob` tient l'état du dernier run (progression reçue par `progress`, arrêt par `stop`) sous verrou.
`donnees_view` et `last_scrape_lanes` sont des fonctions pures ou quasi pures : la vue se teste avec des
dictionnaires et un `FreshnessInfo` construit à la main. Les valeurs de réglage sont dans `config_client.py`.
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime
from typing import Any, Callable, Optional

from ..config_client import client_config
from ..data_freshness import FreshnessInfo
from .data import ago, date_fr, plural, thousands
from .draft_view import ROLE_LABELS

STEP_LABELS = {
    "idle": "En attente",
    "preparation": "Préparation",
    "plan": "Scrape",
    "start": "Scrape",
    "done": "Scrape",
    "recalcul": "Recalcul des scores et des bans",
    "reparation": "Réparation ciblée",
}

_STATUS_LABELS = {"ok": "OK", "partial": "Partiel", "failed": "Échec"}
_OUTCOME_TEXTS = {
    "ok": "Mise à jour terminée",
    "partial": "Terminée avec des manques (voir le rapport)",
}
_STEP_EVENTS = ("preparation", "plan", "start", "done", "recalcul", "reparation")


def _lane_label(label: str) -> str:
    """« Mid » pour `middle` ; `default` (découverte des lanes en échec) devient « Lane par défaut »."""
    return ROLE_LABELS.get(label, "Lane par défaut" if label == "default" else label)


class UpdateJob:
    """Une mise à jour à la fois, dans un fil daemon ; état lu par l'écran Données."""

    def __init__(
        self,
        run: Optional[Callable[..., Any]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Prépare un job inactif.

        Args:
            run: Fonction qui lance le pipeline (`run_pipeline` par défaut, importé ici pour ne pas
                charger Selenium à l'import du client). Reçoit `progress=` et `stop=`.
            clock: Horloge monotone en secondes (injectable pour les tests).
        """
        if run is None:
            from ..pipeline import run_pipeline

            run = run_pipeline
        self._run = run
        self._clock = clock
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._state = "idle"
        self._step = "idle"
        self._detail = ""
        self._lanes: dict = {}
        self._started_at: Optional[float] = None
        self._plan_at: Optional[float] = None
        self._finished_at: Optional[float] = None
        self._error: Optional[str] = None
        self._report = ""

    def start(self) -> Optional[str]:
        """Lance une mise à jour dans un fil daemon.

        Returns:
            None si le run est lancé, sinon la raison du refus (« Mise à jour déjà en cours »).
        """
        with self._lock:
            if self._state == "running":
                return "Mise à jour déjà en cours"
            self._state = "running"
            self._step = "idle"
            self._detail = ""
            self._lanes = {}
            self._started_at = self._clock()
            self._plan_at = None
            self._finished_at = None
            self._error = None
            self._report = ""
            self._stop = threading.Event()
            self._thread = threading.Thread(target=self._work, name="donnees-update", daemon=True)
            self._thread.start()
        return None

    @property
    def running(self) -> bool:
        """True tant que le run lancé n'a pas rendu son résultat."""
        with self._lock:
            return self._state == "running"

    def snapshot(self) -> dict:
        """Copie de l'état sous verrou (listes et dictionnaires neufs, sûrs à lire hors verrou).

        `elapsed_s` s'arrête à la fin du run ; `eta_s` vaut None tant que `DONNEES_ETA_MIN_PAGES` pages
        ne sont pas faites (approximation sans le recalcul final, ~2 min).
        """
        with self._lock:
            now = self._clock()
            lanes = [
                {
                    "lane": label,
                    "done": lane["done"],
                    "total": lane["total"],
                    "failed": lane["failed"],
                    "current": sorted(lane["current"]),
                }
                for label, lane in self._lanes.items()
            ]
            elapsed = 0.0
            if self._started_at is not None:
                end = self._finished_at if self._finished_at is not None else now
                elapsed = end - self._started_at
            eta = None
            pages = sum(lane["done"] for lane in self._lanes.values())
            if (
                self._state == "running"
                and self._plan_at is not None
                and pages
                and pages >= client_config.DONNEES_ETA_MIN_PAGES
            ):
                total = sum(lane["total"] for lane in self._lanes.values())
                eta = (total - pages) * (now - self._plan_at) / pages
            return {
                "state": self._state,
                "step": self._step,
                "detail": self._detail,
                "lanes": lanes,
                "started_at": self._started_at or 0.0,
                "elapsed_s": elapsed,
                "eta_s": eta,
                "error": self._error,
                "report": self._report,
            }

    def cancel(self, timeout: float) -> bool:
        """Demande l'arrêt du run (signal `stop`) et attend la fin du fil au plus `timeout` secondes.

        Returns:
            True si le fil est fini (ou n'a jamais été lancé), False s'il tourne encore.
        """
        with self._lock:
            stop, thread = self._stop, self._thread
        stop.set()
        if thread is None:
            return True
        thread.join(timeout)
        return not thread.is_alive()

    def _work(self) -> None:
        """Corps du fil : exécute le run, range son résultat, rend le logging du client intact."""
        root = logging.getLogger()
        handlers = list(root.handlers)
        level = root.level
        try:
            result = self._run(progress=self._on_progress, stop=self._stop)
            with self._lock:
                self._state = result.status
                self._error = result.error
                self._report = result.report
        except Exception as e:
            with self._lock:
                self._state = "failed"
                self._error = f"{type(e).__name__}: {e}"
        finally:
            root.handlers[:] = handlers
            root.setLevel(level)
            with self._lock:
                self._finished_at = self._clock()

    def _on_progress(self, event: dict) -> None:
        """Reçoit un événement de `run_pipeline` ; ne lève jamais (un événement inconnu est ignoré)."""
        step = event.get("step")
        if step not in _STEP_EVENTS:
            return
        with self._lock:
            self._step = step
            if step == "preparation":
                self._detail = event.get("detail", "")
            elif step == "plan":
                self._lanes = {
                    label: {"done": 0, "total": int(count), "failed": 0, "current": set()}
                    for label, count in event.get("lanes", {}).items()
                }
                self._plan_at = self._clock()
            elif step == "start":
                self._lane(event)["current"].add(event.get("champion"))
            elif step == "done":
                lane = self._lane(event)
                lane["current"].discard(event.get("champion"))
                lane["done"] += 1
                if not event.get("ok", True):
                    lane["failed"] += 1

    def _lane(self, event: dict) -> dict:
        """Compteur de la lane de l'événement, créé à la volée si le plan ne la listait pas."""
        label = event.get("lane") or "default"
        if label not in self._lanes:
            self._lanes[label] = {"done": 0, "total": 0, "failed": 0, "current": set()}
        return self._lanes[label]


def last_scrape_lanes(connection: sqlite3.Connection) -> dict:
    """Lanes du dernier scrape (`db_meta.last_scrape_lanes`, JSON) ; `{}` si absent, illisible ou non tabulé."""
    try:
        row = connection.execute(
            "SELECT value FROM db_meta WHERE key = ?", ("last_scrape_lanes",)
        ).fetchone()
    except sqlite3.Error:
        return {}
    if not row:
        return {}
    try:
        lanes = json.loads(row[0])
    except (TypeError, ValueError):
        return {}
    return lanes if isinstance(lanes, dict) else {}


def _minutes(seconds: float) -> int:
    """Durée en minutes arrondies, au moins 1 (« 12 min »)."""
    return max(1, round(seconds / 60))


def _reason(running: bool, phase_kind: str) -> Optional[str]:
    """Raison qui grise le bouton de lancement, None si on peut lancer."""
    if running:
        return "Mise à jour en cours"
    if phase_kind == "draft":
        return "Sélection des champions en cours"
    if phase_kind == "game":
        return "Partie en cours"
    return None


def _outcome(snapshot: dict) -> Optional[dict]:
    """Issue du dernier run de la session ; None tant qu'aucun run ne s'est terminé."""
    state = snapshot["state"]
    if state in _OUTCOME_TEXTS:
        return {"kind": state, "text": _OUTCOME_TEXTS[state]}
    if state == "failed":
        return {"kind": "failed", "text": f"Échec : {snapshot['error'] or 'raison inconnue'}"}
    return None


def _last(freshness: FreshnessInfo, last_lanes: dict, now: datetime) -> dict:
    """Bloc « dernière mise à jour » : date, statut, volumes et lanes du dernier scrape."""
    if freshness.last_update is None:
        when = "Jamais"
    else:
        when = f"{date_fr(freshness.last_update)} ({ago(freshness.last_update, now)})"
    return {
        "when": when,
        "status": _STATUS_LABELS.get(freshness.scrape_status, "Inconnu"),
        "matchups": thousands(freshness.matchups_count),
        "synergies": thousands(freshness.synergies_count),
        "lanes": [
            {
                "label": _lane_label(label),
                "text": (
                    f"{row.get('success', 0)}/{row.get('total', 0)} "
                    f"en {_minutes(row.get('duration_s', 0))} min, "
                    f"{plural(row.get('failed', 0), 'échec')}"
                ),
            }
            for label, row in last_lanes.items()
        ],
    }


def donnees_view(
    snapshot: dict,
    freshness: FreshnessInfo,
    last_lanes: dict,
    phase_kind: str,
    now: datetime,
) -> dict:
    """Ce que l'écran Données affiche : état du run, bouton de lancement, dernier scrape.

    Args:
        snapshot: Sortie de `UpdateJob.snapshot()`.
        freshness: Fraîcheur de la base (`get_freshness_info`).
        last_lanes: Sortie de `last_scrape_lanes`.
        phase_kind: Famille de phase du client (`draft`, `game`, ...).
        now: Instant de référence (timezone UTC) pour l'âge du dernier scrape.

    Returns:
        Dictionnaire prêt pour le gabarit, libellés en français.
    """
    running = snapshot["state"] == "running"
    reason = _reason(running, phase_kind)
    eta = snapshot["eta_s"]
    step = STEP_LABELS.get(snapshot["step"], snapshot["step"])
    if snapshot["step"] == "preparation" and snapshot.get("detail"):
        step = f"{step} : {snapshot['detail']}"
    return {
        "running": running,
        "can_start": reason is None,
        "reason": reason,
        "step": step,
        "lanes": [
            {
                "label": _lane_label(lane["lane"]),
                "done": lane["done"],
                "total": lane["total"],
                "failed": lane["failed"],
                "current": ", ".join(lane["current"]),
            }
            for lane in snapshot["lanes"]
        ],
        "elapsed": (
            None if snapshot["state"] == "idle" else f"{_minutes(snapshot['elapsed_s'])} min"
        ),
        "eta": None if eta is None else f"≈ {_minutes(eta)} min restantes",
        "outcome": _outcome(snapshot),
        "last": _last(freshness, last_lanes, now),
    }
