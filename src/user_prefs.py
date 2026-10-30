"""Préférences persistées du draft coach (SPEC-06 D2).

Écriture/lecture best-effort : un fichier absent, illisible ou corrompu
retombe silencieusement sur les questions habituelles, sans jamais bloquer
le lancement du draft coach.

`pools_by_role` (SPEC-44) désigne un pool par poste (clés : lanes de
`LCU_POSITION_TO_LANE`). Une entrée invalide y est filtrée sans invalider
le reste du fichier.
"""

import json
import os
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .analysis.strategy import Strategy, parse_strategies, strategy_to_dict
from .config_client import client_config
from .config_constants import LCU_POSITION_TO_LANE
from .pool_manager import get_user_data_path

PREFS_FILENAME = "user_prefs.json"

_KNOWN_LANES = frozenset(LCU_POSITION_TO_LANE.values())

# Clés hors de `UserPrefs`, écrites par lecture brute : `save_user_prefs` les reporte, sinon
# la fin de chaque draft coach les effacerait.
_KEPT_KEYS = ("motion", "active_strategy", "strategies")


@dataclass
class UserPrefs:
    """Dernier choix de l'utilisateur pour chaque question du draft coach."""

    auto_hover: bool = False
    auto_accept_queue: bool = False
    auto_ban_hover: bool = False
    pool_name: Optional[str] = None
    pools_by_role: Dict[str, str] = field(default_factory=dict)


def _parse_pools_by_role(raw: Any) -> Dict[str, str]:
    """Garde les seules entrées `lane -> nom de pool` valides.

    Renvoie `{}` si la valeur n'est pas un objet ; ignore les clés hors lanes
    connues et les valeurs qui ne sont pas des chaînes.
    """
    if not isinstance(raw, dict):
        return {}
    return {
        lane: name for lane, name in raw.items() if lane in _KNOWN_LANES and isinstance(name, str)
    }


def get_user_prefs_path() -> str:
    """Emplacement du fichier de préférences (même logique que les pools)."""
    return get_user_data_path(PREFS_FILENAME)


def load_user_prefs() -> Optional[UserPrefs]:
    """Charge les préférences sauvegardées.

    Returns:
        None si le fichier est absent, illisible, corrompu, ou contient une
        valeur invalide (ex : pool_name qui n'est pas une chaîne). Une valeur
        invalide de `pools_by_role` ne rend jamais None : elle est filtrée
        (voir `_parse_pools_by_role`).

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
            pools_by_role=_parse_pools_by_role(data.get("pools_by_role")),
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

    Les clés de `_KEPT_KEYS` (Motion, stratégies) ne sont pas des champs de `UserPrefs` :
    elles sont reportées telles quelles, sinon chaque fin de draft coach les effacerait.
    """
    data = asdict(prefs)
    raw = _read_raw()
    for key in _KEPT_KEYS:
        if raw.get(key) is not None:
            data[key] = raw[key]
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


def load_strategies() -> Tuple[Optional[str], List[Strategy]]:
    """Nom de la stratégie active (None si aucune choisie) et stratégies perso.

    Une entrée invalide de `strategies` est écartée par `parse_strategies` ; un
    `active_strategy` qui n'est pas une chaîne vaut None.
    """
    raw = _read_raw()
    active = raw.get("active_strategy")
    return (active if isinstance(active, str) else None), parse_strategies(raw.get("strategies"))


def save_active_strategy(name: str) -> bool:
    """Mémorise la stratégie active en gardant les autres clés du fichier."""
    return _write_raw({**_read_raw(), "active_strategy": name})


def save_strategies(strategies: Sequence[Strategy]) -> bool:
    """Mémorise les stratégies perso en gardant les autres clés du fichier."""
    return _write_raw({**_read_raw(), "strategies": [strategy_to_dict(s) for s in strategies]})


def save_pool_name(name: str) -> bool:
    """Mémorise le pool actif du Live Coach en gardant les autres préférences.

    Sans fichier complet, les défauts de `UserPrefs` sont ceux que le Live Coach du client applique déjà.
    """
    return save_user_prefs(replace(load_user_prefs() or UserPrefs(), pool_name=name))


def save_role_pool(lane: str, name: Optional[str]) -> bool:
    """Désigne le pool `name` pour le poste `lane`, ou retire la désignation si `name` est None.

    Renvoie False sans rien écrire si `lane` n'est pas une lane connue (ex : "mid" au lieu de
    "middle"). Les autres préférences et les autres désignations sont conservées : la base vient
    de la lecture brute, pas de `load_user_prefs`, qui renvoie None tant que les clés du draft
    coach manquent.
    """
    if lane not in _KNOWN_LANES:
        return False
    pools_by_role = _parse_pools_by_role(_read_raw().get("pools_by_role"))
    if name is None:
        pools_by_role.pop(lane, None)
    else:
        pools_by_role[lane] = name
    prefs = load_user_prefs() or UserPrefs()
    return save_user_prefs(replace(prefs, pools_by_role=pools_by_role))
