"""Client WebSocket du LCU : les événements du client LoL arrivent sur le bus (SPEC-21 §4.2).

Relevé au spike du 2026-10-04 : connexion `wss://127.0.0.1:{port}` avec l'en-tête `Authorization`
des identifiants LCU, abonnement `[5, "OnJsonApiEvent"]`, messages `[8, "OnJsonApiEvent",
{"uri", "eventType", "data"}]`. Sur le bus : sujet `lcu`, charge `{"uri", "eventType", "data"}`,
limitée aux préfixes suivis (le client en émet 937 sortes).

Best-effort : un client fermé ou une connexion perdue s'annonce une fois en `[ALERTE]`, puis la
reconnexion est exponentielle et bornée ; rien ne remonte vers l'appelant.
"""

import asyncio
import json
import ssl
import threading
from typing import Any, Callable, Optional

from websockets.asyncio.client import connect

from ..config_client import client_config
from ..lcu_client import LCUCredentials
from .bus import EventBus

TOPIC = "lcu"

# Le client LoL sert un certificat auto-signé sur localhost.
_SSL_CONTEXT = ssl.create_default_context()
_SSL_CONTEXT.check_hostname = False
_SSL_CONTEXT.verify_mode = ssl.CERT_NONE


def tracked(uri: str) -> bool:
    """Cet événement est-il de ceux que le client suit ?"""
    return uri.startswith(client_config.LCU_EVENT_PREFIXES)


class LcuEvents:
    """Fil daemon qui republie les événements du LCU sur le bus."""

    def __init__(
        self,
        bus: EventBus,
        credentials: Callable[[], Optional[LCUCredentials]],
        scheme: str = "wss",
    ) -> None:
        """`credentials` est rappelé à chaque connexion : le client LoL change de port à chaque
        lancement. `scheme` ne change que dans les tests (faux serveur sans TLS)."""
        self._bus = bus
        self._credentials = credentials
        self._scheme = scheme
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop: Optional[asyncio.Event] = None
        self._ready = threading.Event()

    def start(self) -> None:
        """Lance le fil (une seule fois) ; revient quand sa boucle est prête à être arrêtée."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="lcu-events", daemon=True)
        self._thread.start()
        self._ready.wait(client_config.LCU_WS_STOP_TIMEOUT_S)

    def stop(self) -> None:
        """Arrête le fil ; sans effet s'il ne tourne pas."""
        thread, loop, stop = self._thread, self._loop, self._stop
        if thread is None:
            return
        if loop is not None and stop is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(stop.set)
            except RuntimeError:  # boucle déjà fermée
                pass
        thread.join(client_config.LCU_WS_STOP_TIMEOUT_S)
        self._thread = self._loop = self._stop = None
        self._ready.clear()

    def _run(self) -> None:
        try:
            asyncio.run(self._main())
        except Exception:  # pylint: disable=broad-exception-caught
            pass  # un échec ici ne doit jamais atteindre le reste de l'application
        finally:
            self._ready.set()

    async def _main(self) -> None:
        self._loop, self._stop = asyncio.get_running_loop(), asyncio.Event()
        self._ready.set()
        delay = client_config.LCU_WS_BACKOFF_MIN_S
        announced = False
        while not self._stop.is_set():
            try:
                credentials = await asyncio.to_thread(self._credentials)
                if credentials is None:
                    raise ConnectionError("client LoL fermé")
                async with connect(
                    f"{self._scheme}://127.0.0.1:{credentials.port}",
                    additional_headers={"Authorization": credentials.auth_header},
                    ssl=_SSL_CONTEXT if self._scheme == "wss" else None,
                    max_size=None,
                ) as websocket:
                    await websocket.send(json.dumps([5, client_config.LCU_WS_SUBSCRIBE_EVENT]))
                    if announced:
                        print("[INFO] WebSocket LCU rétabli")
                    announced, delay = False, client_config.LCU_WS_BACKOFF_MIN_S
                    await self._pump(websocket)
                raise ConnectionError("connexion fermée par le client LoL")
            except Exception as exc:  # pylint: disable=broad-exception-caught
                if not announced and not self._stop.is_set():
                    print(f"[ALERTE] WebSocket LCU indisponible ({exc}), nouvel essai en continu")
                    announced = True
            try:
                await asyncio.wait_for(self._stop.wait(), delay)
            except asyncio.TimeoutError:
                pass
            delay = min(delay * 2, client_config.LCU_WS_BACKOFF_MAX_S)

    async def _pump(self, websocket: Any) -> None:
        """Lit la connexion jusqu'à sa fermeture ou jusqu'à `stop()`."""

        async def read() -> None:
            async for message in websocket:
                self._publish(message)

        reader = asyncio.create_task(read())
        stopper = asyncio.create_task(self._stop.wait())
        try:
            await asyncio.wait({reader, stopper}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in (reader, stopper):
                task.cancel()
        if reader.done() and not reader.cancelled():
            reader.result()  # relève l'erreur de lecture, pour la reconnexion

    def _publish(self, message: Any) -> None:
        """`[8, "OnJsonApiEvent", {...}]` → bus ; tout autre message est ignoré."""
        try:
            kind, _name, event = json.loads(message)
            if kind == 8 and tracked(event["uri"]):
                self._bus.publish(
                    TOPIC,
                    {
                        "uri": event["uri"],
                        "eventType": event.get("eventType"),
                        "data": event.get("data"),
                    },
                )
        except (ValueError, TypeError, KeyError):
            pass
