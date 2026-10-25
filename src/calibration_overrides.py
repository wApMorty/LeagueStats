"""Réglages du modèle appliqués par l'utilisateur via « Appliquer ? o/n ».

`calibration.json` (à côté de l'exécutable, comme `user_prefs.json`) porte
K_MATCHUP, K_SYNERGY, MODEL_VERSION et, depuis SPEC-43, K_INTRINSIC (facultatif :
un fichier à deux K reste lisible). Il est lu à l'import de
`config_constants` et écrase les valeurs par défaut du code : appliquer une
calibration ne demande jamais d'ouvrir le code. Sans fichier, ou avec un
fichier invalide, les valeurs du code restent en vigueur. Un fichier réglé pour
une autre base de version que le code (ex. `spec13-v1+cal1` sous `spec43-v1`)
est ignoré, avec un `[INFO]`.
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


def base_version(version: str) -> str:
    """`spec43-v1+cal2` -> `spec43-v1` : la version sans le suffixe de calibration."""
    return _VERSION_SUFFIX.sub("", version)


def _positive_finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value > 0
    )


def _valid(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    keys = ["K_MATCHUP", "K_SYNERGY"]
    if "K_INTRINSIC" in data:
        keys.append("K_INTRINSIC")
    return (
        all(_positive_finite(data.get(key)) for key in keys)
        and isinstance(data.get("MODEL_VERSION"), str)
        and bool(data["MODEL_VERSION"].strip())
    )


def load_overrides(path: Optional[str] = None) -> Dict[str, Any]:
    """Les réglages présents, ou {} si le fichier est absent, illisible ou invalide
    (tout ou rien : une version sans ses K ne doit jamais s'appliquer seule).
    K_INTRINSIC n'est rendu que s'il est dans le fichier."""
    path = path or get_calibration_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    if not _valid(data):
        return {}
    keys = ("K_MATCHUP", "K_SYNERGY", "K_INTRINSIC", "MODEL_VERSION")
    return {key: data[key] for key in keys if key in data}


def apply_overrides(config: Any, path: Optional[str] = None) -> Dict[str, Any]:
    """Écrase les réglages de `config` (un AnalysisConfig) ; rend ce qui a été posé.
    Rien n'est posé si la version du fichier n'a pas la même base que `config.MODEL_VERSION`."""
    overrides = load_overrides(path)
    if not overrides:
        return {}
    file_version = overrides["MODEL_VERSION"]
    if base_version(file_version) != base_version(config.MODEL_VERSION):
        print(
            f"[INFO] calibration.json ignoré : réglé pour {file_version}, "
            f"le modèle est {config.MODEL_VERSION}"
        )
        return {}
    for key, value in overrides.items():
        setattr(config, key, value)
    return overrides


def save_overrides(
    k_matchup: float,
    k_synergy: float,
    model_version: str,
    k_intrinsic: Optional[float] = None,
    path: Optional[str] = None,
) -> bool:
    """Best-effort : ne lève jamais, rend False si l'écriture échoue.
    K_INTRINSIC n'est écrit que s'il est fourni."""
    path = path or get_calibration_path()
    data = {"K_MATCHUP": k_matchup, "K_SYNERGY": k_synergy, "MODEL_VERSION": model_version}
    if k_intrinsic is not None:
        data["K_INTRINSIC"] = k_intrinsic
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except OSError as e:
        print(f"[WARNING] Impossible de sauvegarder la calibration: {e}")
        return False
