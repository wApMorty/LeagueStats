"""Lancement du client LeagueStats (SPEC-21 §4.1, tâche 55).

Fil principal : la fenêtre. Fils daemon : le serveur local, le WebSocket LCU et le Live Coach, qui
tourne comme en console mais sans lire l'entrée standard. Tout ce qui précède la fenêtre est
best-effort : un échec s'annonce en `[ALERTE]` et ne bloque ni le menu ni les autres fils.
"""

import threading
from typing import Optional

from ..config import config
from ..config_client import client_config
from ..draft_monitor import DraftMonitor
from ..lcu_client import LCUClient
from ..pool_manager import PoolManager
from ..ui.checks import check_database, check_dependencies
from ..user_prefs import UserPrefs, load_user_prefs
from . import server, window
from .bus import EventBus
from .lcu_events import LcuEvents


def _saved_pool(name: Optional[str]) -> Optional[str]:
    """La pool mémorisée si elle existe encore ; sinon None (la pool par défaut du Live Coach)."""
    try:
        return name if name and PoolManager().get_pool(name) is not None else None
    except Exception:  # pylint: disable=broad-exception-caught
        return None


class LiveCoachThread:
    """Le Live Coach en fil daemon : préférences de `user_prefs.json`, aucune question à la console."""

    def __init__(self, bus: EventBus, verbose: bool = False) -> None:
        self._bus = bus
        self._verbose = verbose
        self._stopping = threading.Event()
        self._monitor: Optional[DraftMonitor] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="live-coach", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping.set()
        if self._monitor is not None:
            self._monitor.stop_monitoring()
        if self._thread is not None:
            self._thread.join(client_config.LIVE_COACH_STOP_TIMEOUT_S)

    def _run(self) -> None:
        try:
            prefs = load_user_prefs() or UserPrefs()
            pool = _saved_pool(prefs.pool_name)
            # Le moniteur se construit dans ce fil : ses connexions SQLite n'en sortent pas.
            self._monitor = monitor = DraftMonitor(
                verbose=self._verbose,
                auto_select_pool=pool is None,
                auto_hover=prefs.auto_hover,
                auto_accept_queue=prefs.auto_accept_queue,
                auto_ban_hover=prefs.auto_ban_hover,
                preselected_pool_name=pool,
                console_input=False,
                bus=self._bus,
            )
            waiting = False
            while not self._stopping.is_set():
                if monitor.lcu.find_lcu_credentials() is not None:
                    if monitor.start_monitoring() is not False:
                        return  # la surveillance s'est arrêtée
                if not waiting:
                    print("[INFO] Live Coach en attente du client League of Legends")
                    waiting = True
                self._stopping.wait(client_config.LIVE_COACH_RETRY_S)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            print(f"[ALERTE] Live Coach arrêté : {exc}")


def _wait_for_interrupt() -> None:
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        pass


def run_client(verbose: bool = False) -> bool:
    """Lance le client et rend la main à la fermeture de la fenêtre (bloquant).

    Renvoie False si rien n'a pu démarrer (dépendances, base ou serveur). Si la fenêtre ne s'ouvre
    pas, la page s'ouvre dans le navigateur et le client tourne jusqu'à Ctrl+C.
    """
    if not check_dependencies() or not check_database():
        return False
    bus = EventBus()
    url = server.start(config.DATABASE_PATH, bus, LCUClient(verbose=verbose))
    if url is None:
        return False
    print(f"[INFO] Client LeagueStats sur {url}")
    events = LcuEvents(bus, LCUClient(verbose=verbose).find_lcu_credentials)
    coach = LiveCoachThread(bus, verbose)
    try:
        events.start()
        coach.start()
        if not window.run(url):
            print("[INFO] Ctrl+C pour arrêter le client")
            _wait_for_interrupt()
    finally:
        coach.stop()
        events.stop()
        server.stop()
    return True
