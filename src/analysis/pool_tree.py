"""Arbre de décision du pool (SPEC-54) : ordre de pick d'un pool sur une lane.

Politique optimisée par ``pool_score`` (SPEC-50) : deux branches, selon que le vis-à-vis
est connu ou non. Vis-à-vis vu : la table des valeurs nettes contre lui. Sinon : le blind.
Calcul sur les matrices seules, sans maîtrise. Aucune I/O : tout vient d'un ``PoolScorer``.
"""

from dataclasses import dataclass
from typing import Collection, List, Optional, Sequence, Tuple

from .pool_swipe import PoolScorer


@dataclass(frozen=True)
class TreeChoice:
    """Un champion du pool et sa valeur : blind exposé, ou valeur nette contre le vis-à-vis."""

    champion: str
    value: float  # points de winrate


@dataclass(frozen=True)
class TreeLeaf:
    """Réponse de l'arbre à une situation de draft."""

    branch: str  # "blind" | "counter"
    opponent: Optional[str]  # vis-à-vis de la branche counter, None en blind
    choices: Tuple[TreeChoice, ...]  # disponibles, du choix au dernier repli
    skipped: Tuple[str, ...]  # champions de l'arbre classés avant le choix et indisponibles


@dataclass(frozen=True)
class PoolTree:
    """Tables du pool sur une lane : blind, et une table par adversaire."""

    lane: Optional[str]
    blind: Tuple[TreeChoice, ...]  # tout le pool, blind décroissant
    counters: Tuple[Tuple[str, float, Tuple[TreeChoice, ...]], ...]
    # (adversaire, popularité, pool trié par valeur décroissante), par popularité décroissante

    def leaf(self, opponent: Optional[str], unavailable: Collection[str]) -> TreeLeaf:
        """Feuille pour ``opponent`` (None : vis-à-vis inconnu) et les champions ``unavailable``.

        Adversaire absent de ``counters`` : branche blind. Noms comparés sans casse.
        """
        gone = {name.casefold() for name in unavailable}
        table: Tuple[TreeChoice, ...] = self.blind
        branch, name = "blind", None
        if opponent is not None:
            key = opponent.casefold()
            for enemy, _, enemy_table in self.counters:
                if enemy.casefold() == key:
                    branch, name, table = "counter", enemy, enemy_table
                    break

        choices: List[TreeChoice] = []
        skipped: List[str] = []
        for choice in table:
            if choice.champion.casefold() not in gone:
                choices.append(choice)
            elif not choices:
                skipped.append(choice.champion)
        if not choices:
            return TreeLeaf(branch, name, (), ())
        return TreeLeaf(branch, name, tuple(choices), tuple(skipped))


def _dedupe(pool: Sequence[str]) -> List[str]:
    """Pool sans doublons (sans casse), premier gardé."""
    seen = set()
    unique: List[str] = []
    for champion in pool:
        key = champion.casefold()
        if key not in seen:
            seen.add(key)
            unique.append(champion)
    return unique


def _ranked(choices: Sequence[TreeChoice]) -> Tuple[TreeChoice, ...]:
    """Valeur décroissante, égalité : nom sans casse."""
    return tuple(sorted(choices, key=lambda c: (-c.value, c.champion.casefold())))


def build_tree(scorer: PoolScorer, pool: Sequence[str]) -> PoolTree:
    """Arbre du pool : table blind, et une table par adversaire de ``scorer.enemies``."""
    champions = _dedupe(pool)
    if not champions:
        return PoolTree(lane=scorer.lane, blind=(), counters=())
    blind = _ranked(TreeChoice(c, scorer.blind(c)) for c in champions)
    counters = []
    for i, enemy in enumerate(scorer.enemies):
        table = _ranked(TreeChoice(c, scorer.values(c)[i]) for c in champions)
        counters.append((enemy, scorer.popularity[i], table))
    counters.sort(key=lambda row: (-row[1], row[0].casefold()))
    return PoolTree(lane=scorer.lane, blind=blind, counters=tuple(counters))
