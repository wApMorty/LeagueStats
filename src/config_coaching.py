"""Constantes du coach de gameplay (SPEC-19).

Sorties de config_constants.py, qui dépassait 500 lignes ; il les réexporte
(`from .config_constants import coaching_config` reste valable).
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class CoachingConfig:
    """Coach de gameplay (SPEC-19). Valeurs relevées par le spike du 2026-09-28."""

    # Files capturées : SoloQ et Flex (queueId de l'historique LCU, queueType
    # du classement et de l'écran de fin).
    QUEUE_IDS: tuple = (420, 440)
    RANKED_QUEUES: tuple = ("RANKED_SOLO_5x5", "RANKED_FLEX_SR")
    QUEUE_NAMES: Dict[int, str] = field(default_factory=lambda: {420: "SoloQ", 440: "Flex"})

    # L'historique LCU sert 20 parties au plus, quelle que soit la demande.
    HISTORY_DEPTH: int = 20

    # Une timeline absente juste après la partie est réessayée ; au-delà de
    # ce délai après la fin, la partie est capturée sans elle.
    TIMELINE_GRACE_S: int = 3600

    # ---------- métriques (tâche 31) ----------

    # Poste de chaque joueur quand l'écran de fin manque (rattrapage) :
    # `roleBoundItem`, l'objet de quête de rôle. Relevé le 2026-09-29 sur les
    # 24 premières parties capturées : 60 sur 60 conformes à
    # `detectedTeamPosition` là où l'écran de fin existe. Tout autre objet non
    # nul est une paire de bottes, soit la quête du tireur.
    ROLE_BOUND_ITEMS: Dict[int, str] = field(
        default_factory=lambda: {
            1220: "top",
            1221: "top",
            1209: "jungle",
            1206: "middle",
            1208: "support",
            2055: "support",
        }
    )
    SMITE_SPELL_ID: int = 11
    # Instants fixes, en minutes. Écarts d'or et d'XP pris à 15 min comme
    # `gd15`/`exp15` d'OneTricks, pour que l'objectif soit comparable.
    EARLY_MINUTE: int = 10
    LANE_MINUTE: int = 14
    DIFF_MINUTE: int = 15

    # ---------- références et constats (tâches 33-35) ----------

    # Incrémenté à chaque changement de grille ou de métriques : les analyses
    # d'une autre version sont recalculées au démarrage (SPEC-19 §8).
    GRID_VERSION: int = 1
    # La norme se lit sur les parties les plus récentes, pour suivre le niveau.
    NORM_WINDOW_GAMES: int = 50
    # Sous ces tailles d'échantillon, un Z est stocké mais jamais affiché.
    MIN_NORM_SAMPLE: int = 15
    MIN_OBJECTIVE_SAMPLE: int = 20
    MIN_ABS_Z: float = 1.0
    TOP_NEGATIVE: int = 3
    TOP_POSITIVE: int = 2

    # ---------- suivi dans le temps (tâches 36-38) ----------

    RECURRENCE_WINDOW: int = 10
    # Seuil α du test binomial des schémas, comme SPEC-15 §3.2.1.
    RECURRENCE_ALPHA: float = 0.05
    MIN_TREND_SAMPLE: int = 5  # parties par moitié de fenêtre comparée
    TREND_MIN_T: float = 2.0  # écart / erreur type au-delà duquel on conclut
    MAX_ACTIVE_GOALS: int = 2
    GOAL_WINDOW: int = 5
    GOAL_HOLD: int = 4
    REVIEW_EVERY: int = 10


coaching_config = CoachingConfig()
