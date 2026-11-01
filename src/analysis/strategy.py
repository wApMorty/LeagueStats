"""Stratégies de draft (SPEC-46) : poids par terme du classement de pick.

Une stratégie règle le poids de chaque terme de ``GameEvaluator`` (force, duel de
lane, matchups hors lane, synergie, maîtrise) et le mode de calcul (immédiat ou
recherche). Elle ne touche ni aux probabilités affichées ni au modèle calibré :
``WeightedEvaluator`` applique les poids par-dessus les termes de ``GameEvaluator``,
qui reste la référence.

Seul ``strategy_from_dict`` valide une stratégie saisie ou lue depuis
``user_prefs.json`` ; ``parse_strategies`` et l'écran Stratégies passent par lui.
"""

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..config_constants import analysis_config, draft_config
from .game_eval import GameEvaluator, Placed
from .probability import sigmoid, winrate_points_to_logit

# Termes pondérés, dans l'ordre de l'écran. La maîtrise est appliquée par le moteur, pas ici.
WEIGHTS = ("force", "duel", "other", "synergy", "mastery")


@dataclass(frozen=True)
class Strategy:
    """Poids par terme (0 à STRATEGY_WEIGHT_MAX) et mode de calcul d'une stratégie."""

    name: str
    force: float = 1.0
    duel: float = 1.0
    other: float = 1.0  # matchups hors lane
    synergy: float = 1.0
    mastery: float = 1.0
    search: bool = False  # False = calcul immédiat
    system: bool = False

    @property
    def is_calibrated(self) -> bool:
        """Tous les poids à 1 : le logit de la stratégie est celui de `GameEvaluator`."""
        return all(getattr(self, weight) == 1.0 for weight in WEIGHTS)


SYSTEM_STRATEGIES = (
    Strategy("Simple", 1.0, 1.0, 1.0, 0.0, 1.0, search=False, system=True),
    Strategy("Counter", 0.5, 2.0, 1.0, 0.0, 0.25, search=False, system=True),
    Strategy("Méta", 1.0, 0.0, 0.0, 0.0, 0.0, search=False, system=True),
    Strategy("Complet", 1.0, 1.0, 1.0, 1.0, 1.0, search=True, system=True),
)


def _system_names() -> set:
    return {strategy.name.casefold() for strategy in SYSTEM_STRATEGIES}


def strategy_from_dict(raw: Mapping[str, Any]) -> Strategy:
    """Stratégie perso validée depuis un dict (préférences ou formulaire).

    Lève ``ValueError`` avec un message en français si le nom ou un poids est invalide.
    Le pas des curseurs n'est pas contrôlé : c'est un réglage de l'interface.
    """
    name = raw.get("name")
    if not isinstance(name, str):
        raise ValueError("le nom de la stratégie doit être du texte")
    name = name.strip()
    if not name:
        raise ValueError("le nom de la stratégie est vide")
    if len(name) > draft_config.STRATEGY_NAME_MAX:
        raise ValueError(f"le nom fait plus de {draft_config.STRATEGY_NAME_MAX} caractères")
    if name.casefold() in _system_names():
        raise ValueError(f"« {name} » est le nom d'une stratégie de base")

    weights: Dict[str, float] = {}
    for weight in WEIGHTS:
        value = raw.get(weight)
        if value is None:
            raise ValueError(f"le poids « {weight} » est absent")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"le poids « {weight} » doit être un nombre")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"le poids « {weight} » n'est pas un nombre fini")
        if not 0.0 <= value <= draft_config.STRATEGY_WEIGHT_MAX:
            raise ValueError(
                f"le poids « {weight} » doit être entre 0 et {draft_config.STRATEGY_WEIGHT_MAX:g}"
            )
        weights[weight] = value
    if all(value == 0.0 for value in weights.values()):
        raise ValueError("au moins un poids doit être non nul")

    return Strategy(name=name, search=raw.get("search", False) is True, **weights)


def strategy_to_dict(strategy: Strategy) -> Dict[str, Any]:
    """Forme persistée d'une stratégie : nom, poids et mode de calcul."""
    data: Dict[str, Any] = {"name": strategy.name}
    for weight in WEIGHTS:
        data[weight] = float(getattr(strategy, weight))
    data["search"] = strategy.search
    return data


def parse_strategies(raw: Any) -> List[Strategy]:
    """Stratégies perso lues de `user_prefs.json` ; une entrée invalide ou un doublon est écarté.

    Pas de bornage sur STRATEGY_MAX_COUNT : il s'applique à l'écriture.
    """
    if not isinstance(raw, list):
        return []
    strategies: List[Strategy] = []
    seen = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            strategy = strategy_from_dict(entry)
        except ValueError:
            continue
        key = strategy.name.casefold()
        if key in seen:
            continue
        seen.add(key)
        strategies.append(strategy)
    return strategies


def all_strategies(custom: Sequence[Strategy]) -> List[Strategy]:
    """Les stratégies système, puis les perso."""
    return list(SYSTEM_STRATEGIES) + list(custom)


def find_strategy(name: Optional[str], custom: Sequence[Strategy]) -> Strategy:
    """La stratégie `name` (casse ignorée), sinon `draft_config.STRATEGY_DEFAULT`."""
    if isinstance(name, str):
        wanted = name.casefold()
        for strategy in all_strategies(custom):
            if strategy.name.casefold() == wanted:
                return strategy
    default = draft_config.STRATEGY_DEFAULT.casefold()
    for strategy in SYSTEM_STRATEGIES:
        if strategy.name.casefold() == default:
            return strategy
    return SYSTEM_STRATEGIES[0]


def strategy_of(monitor) -> Strategy:
    """`monitor.strategy` s'il en est une, sinon la stratégie par défaut.

    Les tests construisent souvent le monitor avec `Mock()` : son attribut serait un `Mock`.
    """
    strategy = getattr(monitor, "strategy", None)
    return strategy if isinstance(strategy, Strategy) else find_strategy(None, ())


def _same_lane(champion: Placed, enemy: Placed) -> bool:
    """Vrai si les deux champions sont sur la même lane connue (duel, sinon hors lane)."""
    return bool(champion[1]) and champion[1] == enemy[1]


class WeightedEvaluator:
    """L'interface de `GameEvaluator` dont la recherche a besoin, avec les poids d'une stratégie.

    Les termes restent ceux de `GameEvaluator` ; seuls les poids changent. La recherche
    appelle `contribution`, `team_logit` et `probability` comme sur `GameEvaluator`.
    """

    def __init__(self, base: GameEvaluator, strategy: Strategy) -> None:
        self.base = base
        self.strategy = strategy

    def parts(
        self, champion: Placed, own_team: Sequence[Placed], opposing_team: Sequence[Placed]
    ) -> Dict[str, float]:
        """Log-odds pondérés par terme : `force`, `duel`, `other`, `synergy`.

        Somme égale à `contribution` (à l'arrondi près). Ni I/O ni exception nouvelle.
        """
        strategy = self.strategy
        duel = 0.0
        other = 0.0
        for enemy in opposing_team:
            logit = self.base.matchup_logit(champion, enemy)
            if _same_lane(champion, enemy):
                duel += logit
            else:
                other += logit
        synergy = sum(self.base.synergy_logit(champion, ally) for ally in own_team)
        return {
            "force": strategy.force * self.base.intrinsic_logit(champion),
            "duel": strategy.duel * duel,
            "other": strategy.other * other,
            "synergy": strategy.synergy * synergy,
        }

    def draw_correction(self, champion: Placed, opposing_team: Sequence[Placed]) -> float:
        """Log-odds à ajouter au score de classement de `champion`, jamais à ses probabilités (ADR-004).

        La force contient déjà les adversaires que le champion rencontre d'habitude. Vis-à-vis vu : le
        duel le compte aussi, on retire tout le tirage. Vis-à-vis non vu : un contre-pick perd le gain
        qu'il ne tirera pas ; un champion souvent contré paie déjà ce prix dans sa force.
        """
        points = self.base.draw_points(champion)
        if not any(_same_lane(champion, enemy) for enemy in opposing_team):
            points = max(points, 0.0)
        return -self.strategy.force * winrate_points_to_logit(points * analysis_config.K_INTRINSIC)

    def contribution(
        self, champion: Placed, own_team: Sequence[Placed], opposing_team: Sequence[Placed]
    ) -> float:
        """Log-odds pondérés qu'ajoute `champion`, du point de vue de son camp.

        Même contrat que `GameEvaluator.contribution`. Sommé en ligne, sans passer par `parts`,
        pour ne pas allouer un dict à chaque nœud de recherche. L'ordre des additions est celui
        de `GameEvaluator` : à poids 1, le résultat est identique bit à bit.
        """
        strategy = self.strategy
        matchups = 0.0
        for enemy in opposing_team:
            weight = strategy.duel if _same_lane(champion, enemy) else strategy.other
            matchups += weight * self.base.matchup_logit(champion, enemy)
        synergies = 0.0
        for ally in own_team:
            synergies += strategy.synergy * self.base.synergy_logit(champion, ally)
        return strategy.force * self.base.intrinsic_logit(champion) + matchups + synergies

    def team_logit(self, allies: Sequence[Placed], enemies: Sequence[Placed]) -> float:
        """Log-odds pondérés de victoire alliée. Même double boucle que `GameEvaluator.team_logit`."""
        total = 0.0
        for index, champion in enumerate(allies):
            total += self.contribution(champion, allies[:index], enemies)
        for index, champion in enumerate(enemies):
            total -= self.contribution(champion, enemies[:index], ())
        return total

    @staticmethod
    def probability(logit: float) -> float:
        """Conversion logit -> probabilité, comme `GameEvaluator.probability`."""
        return sigmoid(logit)
