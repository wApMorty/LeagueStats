"""Le client LoL est-il ouvert ? (SPEC-21 §4.6, états « client LoL fermé »)

`LCUClient.connect()` imprime et scrute les processus : trop lourd et trop bavard pour chaque page.
Cette sonde ne lit que la porte d'entrée (identifiants, puis une requête légère), garde sa réponse
quelques secondes et ne lève jamais.
"""

import threading
import time
from typing import Any

from ..config_client import client_config


class LcuProbe:
    """Sonde en cache d'un `LCUClient` (celui du serveur, jamais celui du Live Coach)."""

    def __init__(self, lcu: Any) -> None:
        self._lcu = lcu
        self._lock = threading.Lock()
        self._checked_at = float("-inf")
        self._open = False

    def is_open(self) -> bool:
        """Vrai si le client LoL répond ; la réponse vaut `LCU_PROBE_TTL_S` secondes."""
        with self._lock:
            now = time.monotonic()
            if now - self._checked_at >= client_config.LCU_PROBE_TTL_S:
                self._open = self._probe()
                self._checked_at = now
            return self._open

    def _probe(self) -> bool:
        lcu = self._lcu
        if lcu is None:
            return False
        try:
            if lcu.credentials is None:
                lcu.credentials = lcu.find_lcu_credentials()
            if lcu.credentials is None:
                return False
            if lcu._make_request(client_config.LCU_PROBE_ENDPOINT) is not None:
                return True
            lcu.credentials = None  # port ou mot de passe périmés : le client a redémarré
        except Exception:  # pylint: disable=broad-exception-caught
            pass
        return False
