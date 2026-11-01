"""Écran Stratégies (SPEC-46 §4.6) : choisir la stratégie active, dupliquer, régler et supprimer les perso.

Les stratégies système (Simple, Counter, Méta, Complet) se choisissent et se dupliquent, mais ne
s'éditent pas. La stratégie active et les stratégies perso sont mémorisées dans `user_prefs.json`.
Les refus sont des `Refusal` affichés dans le corps de l'écran, sans écriture. Les bornes du
formulaire (poids max, pas, longueur des noms, nombre de stratégies) viennent de `draft_config`.
"""

from typing import Any, Dict, Optional, Tuple

from ..analysis.strategy import WEIGHTS, Strategy, all_strategies, find_strategy, strategy_from_dict
from ..config_constants import draft_config
from ..user_prefs import load_strategies, save_active_strategy, save_strategies
from .draft_actions import Refusal
from .draft_view import fr

SYSTEM_HINT = "Stratégie système : duplique-la pour la modifier"

# Textes d'interface des termes (pas un réglage) ; l'ordre est celui de l'écran.
TERM_LABELS = {
    "force": "Force",
    "duel": "Duel de lane",
    "other": "Matchups hors lane",
    "synergy": "Synergie",
    "mastery": "Maîtrise",
}
HELP = "1 = valeur calibrée, 0 = terme coupé. Les % de victoire ne changent pas."


def active_name() -> str:
    """Nom de la stratégie active (repli sur la stratégie par défaut, comme le Live Coach)."""
    active, custom = load_strategies()
    return find_strategy(active, custom).name


def _mode(strategy: Strategy) -> str:
    return "Anticipation" if strategy.search else "Immédiat"


def _limits() -> dict:
    return {
        "weight_max": draft_config.STRATEGY_WEIGHT_MAX,
        "weight_step": draft_config.STRATEGY_WEIGHT_STEP,
        "name_max": draft_config.STRATEGY_NAME_MAX,
        "max_count": draft_config.STRATEGY_MAX_COUNT,
    }


def strategies_view(selected: Optional[str], notice: Optional[str] = None) -> dict:
    """La liste des stratégies, la stratégie ouverte (l'active à défaut) et ses poids.

    `limits` donne les bornes du formulaire, lues de `draft_config`.
    """
    active_raw, custom = load_strategies()
    active = find_strategy(active_raw, custom)
    everything = all_strategies(custom)
    chosen = find_strategy(selected, custom) if selected else active
    weights = [
        {
            "key": key,
            "label": TERM_LABELS[key],
            "value": float(getattr(chosen, key)),
            "text": fr(float(getattr(chosen, key)), 2),
        }
        for key in WEIGHTS
    ]
    return {
        "notice": notice,
        "help": HELP,
        "limits": _limits(),
        "count": len(everything),
        "active": active.name,
        "selected": {
            "name": chosen.name,
            "system": chosen.system,
            "editable": not chosen.system,
            "active": chosen.name == active.name,
            "search": chosen.search,
            "mode": _mode(chosen),
            "weights": weights,
        },
        "strategies": [
            {
                "name": s.name,
                "system": s.system,
                "active": s.name == active.name,
                "open": s.name == chosen.name,
                "mode": _mode(s),
            }
            for s in everything
        ],
    }


def _validated(raw: Dict[str, Any]) -> Strategy:
    """Stratégie construite par `strategy_from_dict` ; son refus devient un `Refusal`."""
    try:
        return strategy_from_dict(raw)
    except ValueError as error:
        raise Refusal(f"Stratégie refusée : {error}") from error


def _copy_fields(strategy: Strategy) -> Dict[str, Any]:
    """Poids et mode de calcul d'une stratégie, au format de `strategy_from_dict`."""
    fields: Dict[str, Any] = {key: float(getattr(strategy, key)) for key in WEIGHTS}
    fields["search"] = strategy.search
    return fields


def edit(action: str, name: str, form: Dict[str, str]) -> Tuple[str, Optional[str]]:
    """Applique `action` à la stratégie `name` ; `form` est le corps du formulaire.

    `actif` ; `dupliquer` (nom de la copie dans `form["nom"]`) ; `modifier` (poids et `search` du
    formulaire) ; `supprimer`. Une stratégie système ne se modifie ni ne se supprime.

    Returns:
        (note affichée, stratégie à ouvrir ensuite ; None après une suppression).

    Raises:
        Refusal: action inconnue, stratégie inconnue ou système, validation, préférences non écrites.
    """
    active_raw, custom = load_strategies()
    everything = all_strategies(custom)
    current = next((s for s in everything if s.name.casefold() == name.casefold()), None)
    if action == "actif":
        if current is None:
            raise Refusal("Stratégie inconnue")
        if not save_active_strategy(current.name):
            raise Refusal("Préférences non enregistrées")
        return f"Stratégie active : « {current.name} » (dans la draft en cours)", current.name
    if action not in ("dupliquer", "modifier", "supprimer"):
        raise Refusal("Action inconnue")
    if current is None:
        raise Refusal("Stratégie inconnue")

    if action == "dupliquer":
        if len(everything) >= draft_config.STRATEGY_MAX_COUNT:
            raise Refusal(
                f"{draft_config.STRATEGY_MAX_COUNT} stratégies au plus : "
                "supprime-en une avant d'en dupliquer"
            )
        copy = _validated({**_copy_fields(current), "name": form.get("nom", "")})
        if copy.name.casefold() in {s.name.casefold() for s in everything}:
            raise Refusal("Nom déjà pris")
        if not save_strategies([*custom, copy]):
            raise Refusal("Préférences non enregistrées")
        return f"« {current.name} » dupliqué en « {copy.name} »", copy.name

    if current.system:
        raise Refusal(SYSTEM_HINT)

    if action == "modifier":
        raw: Dict[str, Any] = {"name": current.name, "search": form.get("search") == "1"}
        for key in WEIGHTS:
            try:
                raw[key] = float(form.get(key, ""))
            except ValueError as error:
                raise Refusal(f"le poids « {TERM_LABELS[key]} » doit être un nombre") from error
        edited = _validated(raw)
        if not save_strategies([edited if s.name == current.name else s for s in custom]):
            raise Refusal("Préférences non enregistrées")
        return f"Stratégie « {current.name} » enregistrée", current.name

    # supprimer : la stratégie active revient à la stratégie par défaut.
    if not save_strategies([s for s in custom if s.name != current.name]):
        raise Refusal("Préférences non enregistrées")
    if find_strategy(active_raw, custom).name == current.name:
        save_active_strategy(draft_config.STRATEGY_DEFAULT)
    return f"Stratégie « {current.name} » supprimée", None
