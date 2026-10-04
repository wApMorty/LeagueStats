"""Bus d'événements interne du client (SPEC-21 §4.2, §4.5).

La boucle de draft du Live Coach y publie son état : `publish` ne bloque jamais et ne lève jamais,
quoi que fasse un abonné lent ou cassé (`CLAUDE.md` : aucune exception ne doit interrompre le
monitoring). Les éditeurs sont des fils, le consommateur est le flux SSE du serveur.
"""

import queue
import threading
from typing import Any, Iterable, List, Optional, Tuple

from ..config_client import client_config

Event = Tuple[str, Any]  # (sujet, charge utile)


class Subscription:
    """Une file d'événements bornée, reçue par un abonné."""

    def __init__(self, bus: "EventBus", topics: Optional[frozenset]) -> None:
        self._bus = bus
        self._topics = topics
        self._queue: queue.Queue = queue.Queue(maxsize=client_config.BUS_QUEUE_SIZE)
        self._lock = threading.Lock()

    def accepts(self, topic: str) -> bool:
        return self._topics is None or topic in self._topics

    def put(self, event: Event) -> None:
        """File pleine : le plus ancien événement est abandonné, jamais l'éditeur retardé."""
        with self._lock:
            try:
                self._queue.put_nowait(event)
            except queue.Full:
                self._queue.get_nowait()
                self._queue.put_nowait(event)

    def get(self, timeout: float) -> Optional[Event]:
        """Prochain événement, ou None au bout de `timeout` secondes."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self._bus._unsubscribe(self)  # pylint: disable=protected-access

    def __enter__(self) -> "Subscription":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


class EventBus:
    """Diffusion de `(sujet, charge utile)` à tous les abonnés concernés."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscriptions: List[Subscription] = []

    def publish(self, topic: str, payload: Any) -> None:
        """Dépose l'événement chez chaque abonné du sujet ; ne bloque ni ne lève jamais."""
        try:
            with self._lock:
                targets = [s for s in self._subscriptions if s.accepts(topic)]
            for subscription in targets:
                subscription.put((topic, payload))
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    def subscribe(self, topics: Optional[Iterable[str]] = None) -> Subscription:
        """Abonnement aux `topics` (tous si None) ; à fermer, ou à utiliser dans un `with`."""
        subscription = Subscription(self, None if topics is None else frozenset(topics))
        with self._lock:
            self._subscriptions.append(subscription)
        return subscription

    def _unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            if subscription in self._subscriptions:
                self._subscriptions.remove(subscription)
