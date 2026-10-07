"""Lecture de l'écran de fin et de la notification de LP, hors de la boucle du monitor (SPEC-25).

Les deux endpoints ne répondent que pendant l'écran de fin (relevé du 2026-10-07 : de `PreEndOfGame`
à la sortie d'`EndOfGame`, puis `null`). La boucle du monitor met 2 à 5 s par tour : une lecture par
tour rate un écran quitté par « Rejouer ». Ce fil naît de la transition de phase du `PhaseTracker`,
lit chaque `PHASE_POST_POLL_S` avec son propre client LCU tant que la phase est `post`, et met les
lectures de côté en mémoire. Il n'ouvre aucune base : l'écriture reste dans le fil du coach.
"""

import threading
import time
from typing import Callable, Optional

from ..config_constants import draft_config
from ..lcu_client import LCUClient


class PostGameWatcher:
    """Fil de lecture de la fin de partie, lancé par le rappel du tracker de phase."""

    def __init__(self, tracker, capture, make_lcu: Callable[[], LCUClient] = LCUClient) -> None:
        self._tracker = tracker
        self._capture = capture
        self._make_lcu = make_lcu
        self._armed = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        tracker.subscribe(self.on_phase)

    def start(self) -> None:
        """Arme le suivi : sans lui, une transition de phase ne lance rien (tests, mode hors ligne)."""
        self._armed = True
        self._stop.clear()

    def stop(self) -> None:
        """Désarme et demande l'arrêt du fil en cours."""
        self._armed = False
        self._stop.set()

    def on_phase(self, _old, _new, kind: str) -> None:
        """Rappel du tracker : l'entrée dans la fin de partie lance la lecture, une seule à la fois."""
        if kind != "post" or not self._armed:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="post-game-watcher", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            lcu = self._make_lcu()
            lcu.credentials = lcu.find_lcu_credentials()
            deadline = time.monotonic() + draft_config.POST_GAME_RETRY_WINDOW
            while not self._stop.is_set():
                self._capture.read_transients(lcu)
                # La lecture qui suit la sortie de `post` est la dernière ; le délai borne un
                # tracker resté bloqué sur `post`.
                if self._tracker.kind != "post" or time.monotonic() >= deadline:
                    return
                self._stop.wait(draft_config.PHASE_POST_POLL_S)
        except Exception:  # pylint: disable=broad-exception-caught
            pass  # best-effort : rien ici ne doit atteindre le monitoring en pleine partie
