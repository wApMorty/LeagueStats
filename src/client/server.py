"""Serveur local du client en fil daemon (SPEC-21 §4.1, §4.2).

Best-effort : un échec de démarrage s'annonce en `[ALERTE]` et renvoie `None`, jamais d'exception
vers le menu.
"""

import threading
import time
from pathlib import Path
from typing import Any, Optional, Union

import uvicorn

from ..config_client import client_config
from .app import create_app

_lock = threading.Lock()
_server: Optional[uvicorn.Server] = None
_thread: Optional[threading.Thread] = None
_url: Optional[str] = None


def _run(server: uvicorn.Server) -> None:
    try:
        server.run()
    except (Exception, SystemExit):  # uvicorn quitte par sys.exit(1) si le port est pris
        pass


def start(db_path: Union[str, Path], bus: Any = None, lcu: Any = None) -> Optional[str]:
    """Démarre le serveur (une seule fois) et renvoie son URL, ou `None` en cas d'échec."""
    global _server, _thread, _url  # pylint: disable=global-statement
    with _lock:
        if _url is not None:
            return _url
        try:
            # log_config=None : sans console (exe fenêtré), sys.stdout vaut None et le
            # logging d'uvicorn plante (SPEC-21 §8).
            config = uvicorn.Config(
                create_app(db_path, bus, lcu),
                host=client_config.HOST,
                port=client_config.PORT,
                log_level="warning",
                log_config=None,
                timeout_graceful_shutdown=client_config.SERVER_GRACEFUL_SHUTDOWN_S,
            )
            server = uvicorn.Server(config)
            thread = threading.Thread(target=_run, args=(server,), daemon=True)
            thread.start()
            deadline = time.monotonic() + client_config.SERVER_START_TIMEOUT_S
            while not server.started and thread.is_alive() and time.monotonic() < deadline:
                time.sleep(0.01)
            if not server.started:
                server.should_exit = True
                print("[ALERTE] Le serveur du client n'a pas démarré (port indisponible ?)")
                return None
            port = server.servers[0].sockets[0].getsockname()[1]
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[ALERTE] Le serveur du client n'a pas démarré : {exc}")
            return None
        _server, _thread = server, thread
        _url = f"http://{client_config.HOST}:{port}"
        return _url


def stop() -> None:
    """Arrête le serveur (tests) ; sans effet s'il ne tourne pas."""
    global _server, _thread, _url  # pylint: disable=global-statement
    with _lock:
        if _server is not None:
            _server.should_exit = True
            _thread.join(client_config.SERVER_STOP_TIMEOUT_S)
        _server = _thread = _url = None
