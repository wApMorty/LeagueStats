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
    # patch les rendrait inutiles. ~3 patchs de 14 jours.
    CRAWL_MAX_AGE_DAYS: int = 42

    # Patchs conservés (collecte et purge, SPEC-20 §3.1).
    WINPROB_PATCH_WINDOW: int = 3


winprob_config = WinProbConfig()
