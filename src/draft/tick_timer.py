"""Chronomètre des tours du monitor (SPEC-28) : durée de chaque étape, journal des tours lents.

Le monitor est monofil : une étape lente (requête LCU au timeout, disque) retarde la lecture de la
draft. Sans trace on ne sait pas laquelle ; ici chaque étape est mesurée, un tour de plus de
`TICK_SLOW_S` est écrit au journal avec ses étapes lentes, et le délai de lecture de chaque draft
l'est toujours. Best-effort : rien ici ne lève vers la boucle.
"""

import logging
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Callable, List, Optional, Set, Tuple, TypeVar

from ..config_constants import draft_config

T = TypeVar("T")

_LOG_PATH = Path(__file__).resolve().parent.parent.parent / "logs" / "draft_monitor_ticks.log"


def open_journal() -> Callable[[str], None]:
    """Journal rotatif `logs/draft_monitor_ticks.log` ; à n'appeler qu'au démarrage du monitor.

    Renvoie un sink `ligne -> None` qui ne lève jamais (disque plein, dossier illisible : rien)."""
    logger = logging.getLogger("leaguestats.draft_monitor.ticks")
    try:
        if not logger.handlers:
            _LOG_PATH.parent.mkdir(exist_ok=True)
            handler = RotatingFileHandler(
                _LOG_PATH,
                maxBytes=draft_config.TICK_LOG_MAX_BYTES,
                backupCount=draft_config.TICK_LOG_BACKUPS,
                encoding="utf-8",
            )
            handler.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
            logger.propagate = False
    except Exception:  # pylint: disable=broad-exception-caught
        return lambda _line: None

    def sink(line: str) -> None:
        try:
            logger.info(line)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    return sink


class TickTimer:
    """Durée de chaque étape d'un tour du monitor ; journal des tours lents et du délai de la draft."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sink: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._clock = clock
        self.sink = sink  # None : rien n'est écrit (tests, avant start_monitoring)
        self._started: Optional[float] = None
        self._steps: List[Tuple[str, float, bool]] = []  # (nom, durée, feuille)
        self._open: List[bool] = []  # pile : l'étape en cours a-t-elle des sous-étapes ?
        self._alerted: Set[str] = set()

    def run(self, name: str, work: Callable[[], T]) -> T:
        """Chronomètre `work()`, renvoie son résultat ; une exception est comptée puis propagée."""
        start = self._clock()
        if self._started is None:
            self._started = start
        if self._open:
            self._open[-1] = True
        self._open.append(False)
        try:
            return work()
        finally:
            has_children = self._open.pop()
            self._steps.append((name, self._clock() - start, not has_children))

    def end_tick(self, phase: Optional[str]) -> None:
        """Clôt le tour : écrit s'il est lent, alerte la console s'il est très lent."""
        steps, started = self._steps, self._started
        self._steps, self._started, self._open = [], None, []
        if started is None:
            return
        total = self._clock() - started
        if total <= draft_config.TICK_SLOW_S:
            return
        try:
            shown = [f"{n} {d:.1f}" for n, d, _ in steps if d >= draft_config.TICK_STEP_MIN_S]
            line = " | ".join([f"tour {total:.1f} s phase={phase}"] + shown)
            if self.sink is not None:
                self.sink(line)
            leaves = [(d, n) for n, d, leaf in steps if leaf]
            if total > draft_config.TICK_ALERT_S and leaves:
                slowest = max(leaves)[1]
                if slowest not in self._alerted:
                    self._alerted.add(slowest)
                    print(f"[ALERTE] Boucle du Live Coach : {total:.0f} s dans {slowest}")
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def draft_seen(self, waited_s: float) -> None:
        """Une ligne par épisode : délai entre l'entrée en champ select et la lecture de la draft."""
        if self.sink is not None:
            try:
                self.sink(f"draft vue {waited_s:.1f} s après l'entrée en champ select")
            except Exception:  # pylint: disable=broad-exception-caught
                pass
