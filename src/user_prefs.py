"""Préférences persistées du draft coach (SPEC-06 D2).

Écriture/lecture best-effort : un fichier absent, illisible ou corrompu
retombe silencieusement sur les questions habituelles, sans jamais bloquer
le lancement du draft coach.
"""

import json
import os
from dataclasses import asdict, dataclass
from typing import Optional

from .config_client import client_config
from .pool_manager import get_user_data_path

PREFS_FILENAME = "user_prefs.json"


@dataclass
class UserPrefs:
    """Dernier choix de l'utilisateur pour chaque question du draft coach."""

    auto_hover: bool = False
    auto_accept_queue: bool = False
    auto_ban_hover: bool = False
    pool_name: Optional[str] = None


def get_user_prefs_path() -> str:
    """Emplacement du fichier de préférences (même logique que les pools)."""
    return get_user_data_path(PREFS_FILENAME)


def load_user_prefs() -> Optional[UserPrefs]:
    """Charge les préférences sauvegardées.

    Returns:
        None si le fichier est absent, illisible, corrompu, ou contient une
        valeur invalide (ex : pool_name qui n'est pas une chaîne).

    Les clés inconnues sont ignorées : un fichier écrit par une version
    antérieure (qui contenait ``synergy_weight``, supprimé avec le curseur
    synergie/matchup, ou ``open_onetricks``, supprimé avec la fenêtre
    OneTricks en 4.0.0) se recharge donc sans erreur, et la clé disparaît
    d'elle-même à la prochaine sauvegarde.
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
            pool_name=data.get("pool_name"),
        )
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None

    if prefs.pool_name is not None and not isinstance(prefs.pool_name, str):
        return None

    return prefs


def _read_raw() -> dict:
    """Contenu brut du fichier ({} s'il est absent, illisible ou n'est pas un objet)."""
    try:
        with open(get_user_prefs_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_raw(data: dict) -> bool:
    path = get_user_prefs_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except OSError as e:
        print(f"[WARNING] Impossible de sauvegarder les préférences: {e}")
        return False


def save_user_prefs(prefs: UserPrefs) -> bool:
    """Sauvegarde les préférences. Best-effort : ne lève jamais d'exception.

    Le réglage Motion du client (`motion`, voir `save_motion`) n'est pas un champ de `UserPrefs` :
    il est reporté tel quel, sinon chaque fin de draft coach l'effacerait.
    """
    data = asdict(prefs)
    motion = _read_raw().get("motion")
    if motion is not None:
        data["motion"] = motion
    return _write_raw(data)


def load_motion() -> str:
    """Réglage Motion du client (SPEC-21 §4.3) ; le défaut si absent ou inconnu."""
    motion = _read_raw().get("motion")
    return motion if motion in client_config.MOTION_MODES else client_config.MOTION_DEFAULT


def save_motion(mode: str) -> bool:
    """Mémorise le réglage Motion en gardant les autres clés du fichier.

    Un fichier créé ici ne contient pas les clés du draft coach : `load_user_prefs` renvoie alors
    None et le draft coach pose ses questions habituelles, comme sans fichier.
    """
    if mode not in client_config.MOTION_MODES:
        return False
    return _write_raw({**_read_raw(), "motion": mode})
