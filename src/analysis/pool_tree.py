"""Arbre de décision du pool (SPEC-54), lu dans la règle D depuis SPEC-55.

Ce module ne contient que les types de l'arbre et le classement d'une table : ``TreeChoice``
(un champion et sa valeur en points de winrate), ``PoolTree`` (table blind et une table par
adversaire) et ``_ranked``. Les tables sont remplies par ``analysis/exposure.py`` (``exposure_tree``).
Aucune I/O, aucun calcul de score ici.
"""

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple


@dataclass(frozen=True)
class TreeChoice:
    """Un champion du pool et sa valeur : score D du champion, en points de winrate."""

    champion: str
    value: float  # points de winrate


@dataclass(frozen=True)
class PoolTree:
    """Tables du pool sur une lane : blind, et une table par adversaire."""

    lane: Optional[str]
    blind: Tuple[TreeChoice, ...]  # tout le pool, blind décroissant
    counters: Tuple[Tuple[str, float, Tuple[TreeChoice, ...]], ...]
    # (adversaire, popularité, pool trié par valeur décroissante), par popularité décroissante


def _ranked(choices: Sequence[TreeChoice]) -> Tuple[TreeChoice, ...]:
    """Valeur décroissante, égalité : nom sans casse."""
    return tuple(sorted(choices, key=lambda c: (-c.value, c.champion.casefold())))
