"""Constantes de la win chance et de la collecte (SPEC-20)."""

from dataclasses import dataclass


@dataclass
class WinProbConfig:
    """Collecte LCU de parties tierces (SPEC-20 §3.1), phase 1."""

    CRAWL_DB_FILENAME: str = "crawl.db"

    # Débit : ~1 requête/s (SPEC-20 §2, à valider par la semaine de mesure).
    CRAWL_REQUEST_INTERVAL_S: float = 1.0

    # Reprise après un 429 (SPEC-20 §11.1).
    CRAWL_BACKOFF_S: float = 900.0

    # 1 : joueurs de tes parties ; 2 : leurs adversaires. Au-delà, on s'éloigne
    # de ton MMR.
    CRAWL_MAX_DEPTH: int = 2

    # Parties de tes dernières captures dont les joueurs alimentent la file.
    CRAWL_SEED_GAMES: int = 20

    # Les parties plus vieilles que ça ne sont pas collectées : la dérive de
    # patch les rendrait inutiles. Marge pour garder le patch précédent en secours.
    CRAWL_MAX_AGE_DAYS: int = 42

    # Patchs conservés (purge, SPEC-20 §3.1) : le dernier seulement (@pj35,
    # 2026-10-02, ~2 000 parties/h), complété par les précédents tant que le
    # dernier compte moins de WINPROB_MIN_PATCH_GAMES parties lues, pour ne pas
    # repartir de zéro à chaque patch.
    WINPROB_PATCH_WINDOW: int = 1
    WINPROB_MIN_PATCH_GAMES: int = 5000

    # Plafond de parties lues, les plus anciennes supprimées d'abord (~16 Ko
    # chacune, soit ~1,6 Go). Choisi haut et à réduire à l'usage (@pj35).
    CRAWL_MAX_GAMES: int = 100_000

    # Purge toutes les N parties lues (elle a lieu aussi à chaque seed()).
    CRAWL_PURGE_EVERY: int = 500


winprob_config = WinProbConfig()
