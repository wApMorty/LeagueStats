"""Réglages du modèle appliqués par l'utilisateur via « Appliquer ? o/n ».

`calibration.json` (à côté de l'exécutable, comme `user_prefs.json`) porte
K_MATCHUP, K_SYNERGY et MODEL_VERSION. Il est lu à l'import de
`config_constants` et écrase les valeurs par défaut du code : appliquer une
calibration ne demande jamais d'ouvrir le code. Sans fichier, ou avec un
fichier invalide, les valeurs du code restent en vigueur.
"""

import json
import math
import os
import re
from typing import Any, Dict, Optional

CALIBRATION_FILENAME = "calibration.json"
_VERSION_SUFFIX = re.compile(r"\+cal(\d+)$")


def get_calibration_path() -> str:
    from .pool_manager import get_user_data_path

    return get_user_data_path(CALIBRATION_FILENAME)


def next_version(version: str) -> str:
    """`spec13-v1` -> `spec13-v1+cal1` -> `spec13-v1+cal2` : une calibration
    appliquée change toujours MODEL_VERSION, pour ne jamais mélanger les
    prédictions de deux réglages (cf. config_constants.MODEL_VERSION)."""
    match = _VERSION_SUFFIX.search(version)
    if match:
        return f"{version[: match.start()]}+cal{int(match.group(1)) + 1}"
    return f"{version}+cal1"


def _valid(data: Any) -> bool:
    return (
        isinstance(data, dict)
        and all(
            isinstance(data.get(key), (int, float))
            and not isinstance(data.get(key), bool)
            and math.isfinite(data[key])
            and data[key] > 0
            for key in ("K_MATCHUP", "K_SYNERGY")
        )
        and isinstance(data.get("MODEL_VERSION"), str)
        and bool(data["MODEL_VERSION"].strip())
    )


def load_overrides(path: Optional[str] = None) -> Dict[str, Any]:
    """Les trois réglages, ou {} si le fichier est absent, illisible ou invalide
    (tout ou rien : une version sans ses K ne doit jamais s'appliquer seule)."""
    path = path or get_calibration_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not _valid(data):
        return {}
    return {key: data[key] for key in ("K_MATCHUP", "K_SYNERGY", "MODEL_VERSION")}


def apply_overrides(config: Any, path: Optional[str] = None) -> Dict[str, Any]:
    """Écrase les réglages de `config` (un AnalysisConfig) ; rend ce qui a été posé."""
    overrides = load_overrides(path)
    for key, value in overrides.items():
        setattr(config, key, value)
    return overrides


def save_overrides(
    k_matchup: float, k_synergy: float, model_version: str, path: Optional[str] = None
) -> bool:
    """Best-effort : ne lève jamais, rend False si l'écriture échoue."""
    path = path or get_calibration_path()
    data = {"K_MATCHUP": k_matchup, "K_SYNERGY": k_synergy, "MODEL_VERSION": model_version}
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError as e:
        print(f"[WARNING] Impossible de sauvegarder la calibration: {e}")
        return False
