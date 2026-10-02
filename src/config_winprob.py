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

    # État de partie (SPEC-20 §4.1, state.py). Durées des buffs en secondes ;
    # l'âme se gagne au 4e dragon ; temps de réapparition de base par niveau
    # (1 à 18, wiki League of Legends, approximation).
    BARON_BUFF_S: float = 180.0
    ELDER_BUFF_S: float = 150.0
    SOUL_DRAGONS: int = 4
    RESPAWN_BASE_S: tuple = (
        10,
        10,
        12,
        12,
        14,
        16,
        20,
        25,
        28,
        32.5,
        35,
        37.5,
        40,
        42.5,
        45,
        47.5,
        50,
        52.5,
    )

    # Modèle de win chance (SPEC-20 §4, model.py et train.py).
    WINPROB_MODEL_FILENAME: str = "winprob_model.json"

    # Parties les plus récentes mises de côté pour valider, jamais entraînées (§4.4).
    WINPROB_VALIDATION_FRACTION: float = 0.2

    # Images tirées au hasard, au plus, pour l'entraînement et pour la validation :
    # la logistique n'a qu'une trentaine de poids, au-delà le Python pur ne gagne rien.
    WINPROB_MAX_ROWS: int = 300_000

    # Régularisation L2 (par rapport à la perte moyenne) sur les variables
    # centrées-réduites, légère : le jeu compte des dizaines de milliers d'images ; lignes servant à
    # estimer la hessienne de Newton ; itérations au plus.
    WINPROB_L2: float = 1e-4
    WINPROB_HESSIAN_ROWS: int = 20_000
    WINPROB_ITERATIONS: int = 15

    # Critères d'acceptation (SPEC-20 §11.2), mesurés sur les images après N minutes.
    WINPROB_EVAL_AFTER_MIN: float = 10.0
    WINPROB_BRIER_MAX: float = 0.20
    WINPROB_GAP_MAX: float = 0.05

    # Réentraînement (§4.4) : un nouveau patch de WINPROB_MIN_PATCH_GAMES parties, ou une
    # base grossie d'au moins ce ratio et de ce nombre de parties depuis le dernier modèle.
    WINPROB_RETRAIN_GROWTH: float = 0.2
    WINPROB_RETRAIN_MIN_NEW_GAMES: int = 10_000


winprob_config = WinProbConfig()
