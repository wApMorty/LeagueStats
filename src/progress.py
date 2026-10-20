"""Progression et arrêt du pipeline de scrape (SPEC-37).

Module feuille (aucun import du projet) : ``parallel_parser_roles``,
``multilane`` et ``pipeline`` l'importent tous, sans créer de cycle.
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

Progress = Callable[[dict], None]


class PipelineCancelled(Exception):
    """Arrêt demandé par le signal `stop` (fermeture du client en cours de mise à jour, SPEC-37)."""


def emit(progress: Optional[Progress], event: dict) -> None:
    """Appelle `progress(event)` ; avale toute exception (la progression ne fait jamais échouer un scrape).

    Args:
        progress: Callback de progression, ou None (aucun effet).
        event: Dictionnaire décrivant l'événement (clé `step` obligatoire).
    """
    if progress is None:
        return
    try:
        progress(event)
    except Exception as e:
        logger.warning("Callback de progression en erreur (ignoré): %s", e)
