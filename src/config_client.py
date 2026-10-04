"""Constantes du client LeagueStats (SPEC-21).

Réexportées par config_constants.py comme config_coaching.py
(`from .config_constants import client_config` reste valable).
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass
class ClientConfig:
    """Serveur local, base et sécurité du client (SPEC-21 §4.1, §4.7)."""

    # Le serveur n'écoute que sur la boucle locale ; port 0 = port libre choisi par l'OS
    # (la fenêtre locale n'a pas besoin d'un port connu, @pj35, 2026-10-04).
    HOST: str = "127.0.0.1"
    PORT: int = 0
    SERVER_START_TIMEOUT_S: float = 10.0
    SERVER_STOP_TIMEOUT_S: float = 5.0

    # Lecture pendant que le Live Coach écrit : attente d'un verrou avant d'abandonner.
    DB_READ_TIMEOUT_S: float = 5.0

    # Jeton de session (octets aléatoires) et en-tête qui le porte.
    SESSION_TOKEN_BYTES: int = 32
    TOKEN_HEADER: str = "X-Session-Token"

    # Hôtes acceptés dans `Host` et `Origin` (anti-DNS rebinding, anti-CSRF).
    ALLOWED_HOSTS: Tuple[str, ...] = ("127.0.0.1", "localhost")

    # Méthodes qui modifient quelque chose, et lectures qui exigent aussi le jeton (SSE).
    TOKEN_METHODS: Tuple[str, ...] = ("POST", "PUT", "PATCH", "DELETE")
    TOKEN_PATHS: Tuple[str, ...] = ("/events",)


client_config = ClientConfig()
