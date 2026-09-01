"""Préférences persistées du draft coach (SPEC-06 D2).

Écriture/lecture best-effort : un fichier absent, illisible ou corrompu
retombe silencieusement sur les questions habituelles, sans jamais bloquer
le lancement du draft coach.
"""

import json
import os
from dataclasses import asdict, dataclass
from typing import Optional

from .pool_manager import get_user_data_path

PREFS_FILENAME = "user_prefs.json"


@dataclass
class UserPrefs:
    """Dernier choix de l'utilisateur pour chaque question du draft coach."""

    auto_hover: bool = False
    auto_accept_queue: bool = False
    auto_ban_hover: bool = False
    open_onetricks: bool = True
    synergy_weight: float = 0.5
    pool_name: Optional[str] = None


def get_user_prefs_path() -> str:
    """Emplacement du fichier de préférences (même logique que les pools)."""
    return get_user_data_path(PREFS_FILENAME)


def load_user_prefs() -> Optional[UserPrefs]:
    """Charge les préférences sauvegardées.

    Returns:
        None si le fichier est absent, illisible, corrompu, ou contient une
        valeur hors bornes (ex : synergy_weight hors [0.0, 1.0]).
    """
    path = get_user_prefs_path()
    if not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        prefs = UserPrefs(
            auto_hover=bool(data["auto_hover"]),
            auto_accept_queue=bool(data["auto_accept_queue"]),
            auto_ban_hover=bool(data["auto_ban_hover"]),
            open_onetricks=bool(data["open_onetricks"]),
            synergy_weight=float(data["synergy_weight"]),
            pool_name=data.get("pool_name"),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None

    if not (0.0 <= prefs.synergy_weight <= 1.0):
        return None
    if prefs.pool_name is not None and not isinstance(prefs.pool_name, str):
        return None

    return prefs


def save_user_prefs(prefs: UserPrefs) -> bool:
    """Sauvegarde les préférences. Best-effort : ne lève jamais d'exception."""
    path = get_user_prefs_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(prefs), f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(f"[WARNING] Impossible de sauvegarder les préférences: {e}")
        return False
