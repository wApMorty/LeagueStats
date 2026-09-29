"""Grille par rôle et références : norme, objectif (SPEC-19 §4, §5, tâche 33).

- **Norme** : les autres joueurs du même poste dans tes parties précédentes
  (`game_metrics`, lignes hors joueur), sur les NORM_WINDOW_GAMES dernières.
- **Objectif** : l'historique OneTricks (100 parties Master+ de ton champion)
  pour les métriques qu'il publie. Aucune valeur repère sourcée n'a été
  retenue pour les autres (§5.2) : elles ne se lisent que contre la norme.
"""

from dataclasses import dataclass
from math import sqrt
from statistics import mean, stdev
from typing import Callable, Dict, List, Optional

from ..config_constants import coaching_config
from .metrics import METRICS

# Poids par rôle : 2 = métrique principale (●●), 1 = secondaire (●). Grille
# de §5.1, révisée par l'exploration du 2026-09-29 (24 parties, spec §5.3) :
# d < 0,3 fait perdre un rang, un d de mauvais signe retire la métrique,
# d >= 1 fait monter à 2, d >= 0,9 ajoute une métrique absente au rang 1.
GRID: Dict[str, Dict[str, int]] = {
    "top": {
        "cs_10": 1,
        "gold_diff_15": 2,
        "xp_diff_15": 2,
        "deaths_before_14": 2,
        "solo_deaths": 2,
        "deaths_per_10": 2,
        "damage_per_min": 1,
        "structure_damage_per_min": 2,
    },
    "jungle": {
        "cs_10": 1,
        "cs_per_min": 1,
        "gold_diff_15": 1,
        "xp_diff_15": 1,
        "deaths_before_14": 1,
        "solo_deaths": 1,
        "deaths_per_10": 2,
        "kill_participation": 1,
        "objective_presence": 1,
        "structure_damage_per_min": 1,
    },
    "middle": {
        "cs_10": 1,
        "cs_per_min": 1,
        "gold_diff_15": 2,
        "xp_diff_15": 2,
        "deaths_before_14": 1,
        "solo_deaths": 1,
        "deaths_per_10": 2,
        "kill_participation": 1,
        "damage_per_min": 2,
        "damage_share": 2,
        "structure_damage_per_min": 1,
    },
    "bottom": {
        "cs_10": 1,
        "cs_14": 2,
        "cs_per_min": 2,
        "gold_diff_15": 2,
        "xp_diff_15": 2,
        "deaths_before_14": 2,
        "solo_deaths": 2,
        "deaths_per_10": 2,
        "objective_presence": 1,
        "damage_per_min": 2,
        "damage_share": 2,
        "structure_damage_per_min": 2,
    },
    "support": {
        "gold_diff_15": 1,
        "xp_diff_15": 1,
        "deaths_before_14": 1,
        "deaths_per_10": 2,
        "kill_participation": 1,
        "objective_presence": 1,
        "vision_per_min": 2,
        "wards_killed_per_10": 1,
        "control_wards_per_10": 2,
        "structure_damage_per_min": 1,
    },
}


@dataclass(frozen=True)
class Reference:
    """Moyenne, écart-type et taille d'échantillon d'une référence."""

    mean: float
    sd: Optional[float]
    n: int
    source: str = ""


def reference_from(values: List[float], source: str = "") -> Optional[Reference]:
    if not values:
        return None
    sd = stdev(values) if len(values) > 1 else None
    return Reference(mean(values), sd, len(values), source)


def norm_reference(metric: str, values: List[float]) -> Optional[Reference]:
    """Norme d'une métrique à partir des valeurs des pairs.

    Un écart face à l'adversaire direct est à somme nulle : dans tes parties,
    tes adversaires de lane ont exactement l'opposé de ton propre écart, et
    leur moyenne ne mesurerait que toi. Sa norme est donc 0 par construction ;
    seule sa dispersion (écart quadratique autour de 0) vient des pairs.
    """
    if not METRICS[metric].zero_sum:
        return reference_from(values)
    if not values:
        return None
    sd = sqrt(sum(v * v for v in values) / len(values)) if len(values) > 1 else None
    return Reference(0.0, sd, len(values))


def z_score(value: float, ref: Optional[Reference], sense: int) -> Optional[float]:
    """Écart orienté : positif = bonne nouvelle. None sans écart-type."""
    if ref is None or not ref.sd:
        return None
    return sense * (value - ref.mean) / ref.sd


# ---------- objectif OneTricks ----------

# Métrique -> valeur tirée d'une partie de `matchHistory` (forme relevée le
# 2026-09-29 sur la page Olaf top).
_ONETRICKS_METRICS: Dict[str, Callable[[dict], Optional[float]]] = {
    "cs_per_min": lambda g: g["details"]["playerData"]["stats"]["cs"]
    / (g["details"]["gameDuration"] / 60),
    "deaths_per_10": lambda g: g["details"]["playerData"]["stats"]["deaths"]
    / (g["details"]["gameDuration"] / 600),
    "kill_participation": lambda g: (
        (
            g["details"]["playerData"]["stats"]["kills"]
            + g["details"]["playerData"]["stats"]["assists"]
        )
        / g["details"]["teamKills"]
        if g["details"]["teamKills"]
        else None
    ),
    "gold_diff_15": lambda g: g["gameRoles"]["gd15"],
    "xp_diff_15": lambda g: g["gameRoles"]["exp15"],
}
# Rôle OneTricks (`gameRoles.playerRole`) de chaque lane interne.
_ONETRICKS_ROLES = {"middle": "mid", "bottom": "bot"}


def objective_from_history(history: List[dict], lane: str, source: str) -> Dict[str, Reference]:
    """Références par métrique, sur les parties du rôle joué. Parties mal formées ignorées."""
    role = _ONETRICKS_ROLES.get(lane, lane)
    games = [g for g in history if (g.get("gameRoles") or {}).get("playerRole") == role]
    refs: Dict[str, Reference] = {}
    for metric, extract in _ONETRICKS_METRICS.items():
        values = []
        for game in games:
            try:
                value = extract(game)
            except (KeyError, TypeError, ZeroDivisionError):
                continue
            if value is not None:
                values.append(float(value))
        ref = reference_from(values, f"{source} n={len(values)}")
        if ref and ref.n >= coaching_config.MIN_OBJECTIVE_SAMPLE:
            refs[metric] = ref
    return refs


_objectives: Dict[tuple, Dict[str, Reference]] = {}


def onetricks_objective(champion: str, lane: str) -> Dict[str, Reference]:
    """Objectif OneTricks de (champion, lane), une requête par session. {} en cas d'échec."""
    key = (champion, lane)
    if key not in _objectives:
        from ..draft.loadout import fetch_page  # réseau : importé à l'usage

        page = fetch_page(champion, lane)
        history = (page or {}).get("matchHistory") or []
        refs = objective_from_history(history, lane, f"OneTricks {champion}")
        if not page:
            return refs  # échec réseau : retenté à la prochaine partie
        _objectives[key] = refs
    return _objectives[key]
