"""Source unique de la phase gameflow du client LoL (SPEC-25).

La phase arrive par l'événement WebSocket `/lol-gameflow/v1/gameflow-phase` à l'instant du changement
(relevé du 2026-10-07 : `data` est la phase en chaîne, `"None"` hors lobby). Un sondage lent rattrape
un événement manqué, une reconnexion et le mode console, où le WebSocket n'existe pas.

`phase` vaut None tant que la phase n'est pas confirmée depuis `PHASE_STALE_S` (client fermé, tracker
pas démarré) : l'appelant la lit alors lui-même. Rien ici ne lève vers l'appelant ni n'ouvre de base.
"""

import threading
import time
from typing import Callable, List, Optional

from ..client.lcu_events import TOPIC as LCU_TOPIC
from ..config_constants import draft_config
from ..lcu_client import LCUClient

TOPIC = "phase"
PHASE_URI = "/lol-gameflow/v1/gameflow-phase"

# (ancienne phase, nouvelle phase, famille de la nouvelle)
Callback = Callable[[Optional[str], Optional[str], str], None]


def kind_of(phase: Optional[str]) -> str:
    """Famille d'une phase du LCU : closed, idle, queue, draft, game, post, error ou unknown."""
    if phase is None:
        return "closed"
    if phase in draft_config.OUTCOME_TRIGGER_PHASES:
        return "post"
    return draft_config.PHASE_KINDS.get(phase, "unknown")


def lcu_phase_reader() -> Callable[[], Optional[str]]:
    """Lecteur de phase sur un `LCUClient` propre au tracker (ni celui du coach, ni celui du serveur)."""
    lcu = LCUClient()
    searched_at = float("-inf")

    def read() -> Optional[str]:
        nonlocal searched_at
        if lcu.credentials is None:
            now = time.monotonic()
            if now - searched_at < draft_config.PHASE_CREDENTIALS_RETRY_S:
                return None  # la recherche scrute les processus : pas à chaque sondage
            searched_at = now
            lcu.credentials = lcu.find_lcu_credentials()
        phase = lcu._make_request(PHASE_URI)  # pylint: disable=protected-access
        if not isinstance(phase, str):
            lcu.credentials = None  # port ou mot de passe périmés : le client a redémarré
            return None
        return phase

    return read


class PhaseTracker:
    """La phase gameflow courante, de l'événement WebSocket ou du sondage de rattrapage."""

    def __init__(
        self,
        read: Callable[[], Optional[str]],
        bus=None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read = read
        self._bus = bus
        self._clock = clock
        self._lock = threading.Lock()
        self._phase: Optional[str] = None
        self._entered = clock()
        self._entered_epoch = time.time()
        self._confirmed = float("-inf")  # dernier instant où la phase a été confirmée
        self._callbacks: List[Callback] = []
        self._event_handlers: List[Callable[[dict], None]] = []
        self._unknown_seen: set = set()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def phase(self) -> Optional[str]:
        """Chaîne brute du LCU ; None : client fermé, phase non confirmée ou tracker muet."""
        with self._lock:
            return self._phase

    @property
    def kind(self) -> str:
        """Famille de la phase courante (`kind_of`)."""
        return kind_of(self.phase)

    def since(self) -> float:
        """Secondes passées dans la phase courante."""
        with self._lock:
            return self._clock() - self._entered

    def subscribe(self, callback: Callback) -> None:
        """`callback(ancienne, nouvelle, famille)` à chaque changement, dans le fil du tracker."""
        self._callbacks.append(callback)

    def subscribe_events(self, handler: Callable[[dict], None]) -> None:
        """`handler(événement)` pour chaque événement LCU du bus autre que la phase, dans le fil du
        tracker : il doit rester bref et ne pas toucher à une base. Sans bus, jamais appelé."""
        self._event_handlers.append(handler)

    def observe(self, phase: Optional[str]) -> None:
        """Une lecture : événement, sondage réussi (chaîne) ou sondage sans réponse (None)."""
        now = self._clock()
        with self._lock:
            if phase is None:
                # Un sondage raté n'efface pas une phase connue avant PHASE_STALE_S.
                if self._phase is None or now - self._confirmed < draft_config.PHASE_STALE_S:
                    return
            else:
                self._confirmed = now
            if phase == self._phase:
                return
            old, self._phase = self._phase, phase
            self._entered, self._entered_epoch = now, time.time()
            since_epoch = self._entered_epoch
        self._announce(old, phase, since_epoch)

    def _announce(self, old: Optional[str], new: Optional[str], since_epoch: float) -> None:
        kind = kind_of(new)
        if kind == "unknown" and new not in self._unknown_seen:
            self._unknown_seen.add(new)
            print(f"[INFO] Phase gameflow inconnue : {new}")
        if self._bus is not None:
            self._bus.publish(TOPIC, {"phase": new, "kind": kind, "since": since_epoch})
        for callback in list(self._callbacks):
            try:
                callback(old, new, kind)
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # un rappel cassé n'arrête ni le tracker ni les autres rappels

    def poll_once(self) -> None:
        """Un sondage de rattrapage."""
        try:
            phase = self._read()
        except Exception:  # pylint: disable=broad-exception-caught
            phase = None
        self.observe(phase)

    def _on_event(self, event) -> None:
        """Un message du bus : l'événement de phase, ou un autre pour les abonnés d'événements."""
        payload = event[1]
        if not isinstance(payload, dict):
            return
        if payload.get("uri") == PHASE_URI:
            data = payload.get("data")
            if isinstance(data, str):
                self.observe(data)
            return
        for handler in list(self._event_handlers):
            try:
                handler(payload)
            except Exception:  # pylint: disable=broad-exception-caught
                pass  # un abonné cassé n'arrête ni le tracker ni les autres

    def start(self) -> None:
        """Lance le fil daemon ; sans bus, le sondage seul. Sans effet s'il tourne déjà."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="phase-tracker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Demande l'arrêt ; le fil, daemon, s'éteint au plus tard au prochain sondage."""
        self._stop.set()

    def _run(self) -> None:
        subscription = self._bus.subscribe([LCU_TOPIC]) if self._bus is not None else None
        next_poll = float("-inf")
        try:
            while not self._stop.is_set():
                try:
                    if self._clock() >= next_poll:
                        self.poll_once()
                        post = self.kind == "post"
                        interval = (
                            draft_config.PHASE_POST_POLL_S if post else draft_config.PHASE_POLL_S
                        )
                        next_poll = self._clock() + interval
                    wait = max(0.0, next_poll - self._clock())
                    if subscription is None:
                        self._stop.wait(wait)
                    elif (event := subscription.get(wait)) is not None:
                        self._on_event(event)
                except Exception:  # pylint: disable=broad-exception-caught
                    self._stop.wait(draft_config.PHASE_POLL_S)
        finally:
            if subscription is not None:
                subscription.close()
