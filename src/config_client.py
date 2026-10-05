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

    # Fenêtre sans bordure (SPEC-21 §2 et §8). Le fond évite l'éclair blanc avant la première image.
    WINDOW_TITLE: str = "LeagueStats"
    WINDOW_SIZE: Tuple[int, int] = (1280, 800)
    WINDOW_MIN_SIZE: Tuple[int, int] = (960, 600)
    WINDOW_BACKGROUND: str = "#030e0a"  # équivalent hexadécimal de `--bg` (style.css)

    # Réglage Motion (SPEC-21 §4.3) : « systeme » suit `prefers-reduced-motion`, « reduit » coupe
    # tout, « complet » anime quel que soit le système (Windows annonce `reduce` chez @pj35).
    MOTION_MODES: Tuple[str, ...] = ("systeme", "complet", "reduit")
    MOTION_DEFAULT: str = "complet"

    # Data Dragon (SPEC-21 tâche 86) : images et données de la draft, mises en cache sur disque.
    # Version vide = la plus récente de `versions.json` (renouvelée une fois par jour).
    DDRAGON_BASE: str = "https://ddragon.leagueoflegends.com"
    DDRAGON_VERSION: str = ""
    DDRAGON_LOCALE: str = "fr_FR"
    ASSETS_DIR: str = "data/client_assets"
    ASSETS_TIMEOUT_S: float = 10.0
    ASSETS_VERSIONS_TTL_S: int = 86400
    ASSETS_RETRY_S: float = 300.0  # délai avant de retenter un téléchargement échoué
    ASSETS_BROWSER_CACHE_S: int = 86400

    # Live Coach lancé en fil par le client : attente du client LoL (secondes) entre deux essais
    # et délai d'arrêt à la fermeture de la fenêtre.
    LIVE_COACH_RETRY_S: float = 15.0
    LIVE_COACH_STOP_TIMEOUT_S: float = 5.0

    # Banc `/_motion` (critère 11) : budget par image (60 Hz) et durée d'une scène.
    MOTION_BUDGET_MS: float = 16.7
    MOTION_BENCH_SCENE_S: int = 3

    # État du client LoL (sonde légère, mise en cache) et rafraîchissement de la pastille.
    LCU_PROBE_ENDPOINT: str = "/lol-gameflow/v1/gameflow-phase"
    LCU_PROBE_TTL_S: float = 3.0
    LCU_STATE_POLL_S: int = 5

    # Bus interne : file par abonné (le plus ancien message est abandonné quand elle déborde),
    # sondage de la file par le flux SSE (sert aussi à constater la déconnexion), battement SSE.
    BUS_QUEUE_SIZE: int = 256
    SSE_POLL_S: float = 1.0
    SSE_PING_S: int = 15
    # Un flux SSE ouvert retiendrait l'arrêt du serveur : délai avant de le couper.
    SERVER_GRACEFUL_SHUTDOWN_S: int = 2

    # WebSocket LCU (SPEC-21 §4.2) : événements suivis (préfixes d'URI), abonnement, et reconnexion
    # exponentielle bornée.
    LCU_EVENT_PREFIXES: Tuple[str, ...] = (
        "/lol-gameflow",
        "/lol-lobby",
        "/lol-matchmaking",
        "/lol-champ-select",
        "/lol-chat",
        "/lol-end-of-game",
        "/lol-ranked",
    )
    LCU_WS_SUBSCRIBE_EVENT: str = "OnJsonApiEvent"
    LCU_WS_BACKOFF_MIN_S: float = 1.0
    LCU_WS_BACKOFF_MAX_S: float = 30.0
    LCU_WS_STOP_TIMEOUT_S: float = 5.0

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
