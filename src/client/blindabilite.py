"""Écran Blindabilité : matrice des postes et distribution des tirages (`analysis/blindability.py`).

Vue pure : elle se teste avec des dictionnaires, sans base. Le pas de l'histogramme est dans
`config_client.py`.
"""

import math
from typing import Dict, List, Optional

from ..config_client import client_config
from ..config_constants import scraping_config
from .draft_view import ROLE_LABELS, Champions, fr, signed

_DEFAULT_LANE = "middle"
# Un écart de 100 % à la moyenne de la ligne colore la case au maximum.
_FULL_COLOR_PCT = 100.0


def _cell(spread: float, mean: float) -> dict:
    """Case de matrice : écart à la moyenne de la ligne ; ligne sans signal mesurable, « — »."""
    if not mean:
        return {"text": "—", "tone": "", "alpha": 0, "title": "Aucun signal mesurable"}
    pct = 100 * (spread / mean - 1)
    return {
        "text": f"{signed(round(pct), 0)} %",  # jamais « −0 % »
        "tone": "up" if pct >= 0 else "down",
        "alpha": round(min(abs(pct) / _FULL_COLOR_PCT, 1.0), 2),
        "title": f"{fr(spread, 2)} pp de dispersion",
    }


def _matrix(matrix: Dict[str, Dict[str, float]]) -> Optional[dict]:
    """Une matrice pour le gabarit, une ligne et une colonne par poste ; None sans données."""
    if not matrix:
        return None
    rows = []
    for lane in scraping_config.LANES:
        spreads = matrix.get(lane, {})
        mean = sum(spreads.values()) / len(spreads) if spreads else 0.0
        rows.append(
            {
                "label": ROLE_LABELS[lane],
                "cells": [
                    _cell(spreads[other], mean) if other in spreads else None
                    for other in scraping_config.LANES
                ],
            }
        )
    return {"columns": [ROLE_LABELS[lane] for lane in scraping_config.LANES], "rows": rows}


def _histogram(draws: Dict[str, float], champions: Champions) -> List[dict]:
    """Colonnes de l'histogramme, symétriques autour de 0 : `{label, tone, champions}`."""
    if not draws:
        return []
    step = client_config.BLINDABILITE_BIN_PP
    reach = max(1, math.ceil(max(abs(value) for value in draws.values()) / step - 0.5))
    bins: Dict[int, List[dict]] = {index: [] for index in range(-reach, reach + 1)}
    for name, value in sorted(draws.items(), key=lambda item: abs(item[1])):
        portrait = champions.by_name(name) or {"img": None, "name": name}
        bins[round(value / step)].append({**portrait, "value": signed(value, 2)})
    return [
        {
            "label": signed(index * step, 2) if index % 2 == 0 else "",
            "tone": "up" if index > 0 else "down" if index < 0 else "",
            "champions": column,
        }
        for index, column in bins.items()
    ]


def blindabilite_view(data: dict, champions: Champions, lane: Optional[str]) -> dict:
    """Ce qu'affiche l'écran.

    Args:
        data: Sortie de `compute_blindability`, ou `{}` sans base lisible.
        champions: Portraits.
        lane: Poste de la distribution ; un poste inconnu revient à celui par défaut.

    Returns:
        `{empty, matchups, synergies, lanes, histogram}`, prêt pour le gabarit.
    """
    lane = lane if lane in scraping_config.LANES else _DEFAULT_LANE
    matchups = _matrix(data.get("matchups", {}))
    return {
        "empty": matchups is None,
        "matchups": matchups,
        "synergies": _matrix(data.get("synergies", {})),
        "lanes": [
            {"key": key, "label": ROLE_LABELS[key], "on": key == lane}
            for key in scraping_config.LANES
        ],
        "histogram": _histogram(data.get("draws", {}).get(lane, {}), champions),
    }
