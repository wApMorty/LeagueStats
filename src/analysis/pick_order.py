"""Ordre de pick conseillé sur les matrices de blindabilité (SPEC-51 §1.3, §4.1).

Un pick du poste ``r`` rapporte ``sqrt(Σ M[r][e]² pour les postes e déjà pickés par l'adversaire
+ Σ S[r][a]² pour les postes a déjà pickés par son propre camp)``, M et S étant les matrices de
``compute_blindability`` en points de winrate. Blue maximise la somme des gains de son camp moins
celle de red, red la minimise ; la séquence de pick est fixée par la draft classée.

Programmation dynamique sur les postes déjà pickés de chaque côté (32 × 32 états). Égalité de
valeur : le premier poste dans l'ordre de ``scraping_config.LANES`` gagne.
"""

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import FrozenSet, Iterator, List, Mapping, Optional, Tuple

from ..config_constants import scraping_config

# Règle de la draft classée (B = blue, R = red) : 5 picks par côté, pas de bans pris en compte.
PICK_SEQUENCE = "BRRBBRRBBR"

Matrix = Mapping[str, Mapping[str, float]]


@dataclass(frozen=True)
class Pick:
    """Un pick de la ligne principale.

    Attributes:
        slot: rang du pick, de 1 à 10.
        side: ``"blue"`` ou ``"red"``.
        lane: poste pické, un élément de ``scraping_config.LANES``.
    """

    slot: int
    side: str
    lane: str


def pick_order(matchups: Matrix, synergies: Matrix) -> List[Pick]:
    """Ligne principale de pick (10 picks) qui maximise l'avantage de blue.

    Args:
        matchups: matrice des postes adverses, ``{poste: {autre poste: écart-type en points}}``.
        synergies: matrice des postes alliés, même format ; case absente = 0.

    Returns:
        Les 10 picks dans l'ordre de ``PICK_SEQUENCE``, ou ``[]`` si ``matchups`` est vide.
    """
    if not matchups:
        return []
    lanes = scraping_config.LANES

    def gain(lane: str, mine: FrozenSet[str], theirs: FrozenSet[str]) -> float:
        total = sum(matchups.get(lane, {}).get(e, 0.0) ** 2 for e in theirs)
        total += sum(synergies.get(lane, {}).get(a, 0.0) ** 2 for a in mine)
        return math.sqrt(total)

    def children(
        t: int, blue: FrozenSet[str], red: FrozenSet[str]
    ) -> Iterator[Tuple[str, float, FrozenSet[str], FrozenSet[str]]]:
        """Coups possibles au tour t : (poste, gain signé, blue suivant, red suivant)."""
        is_blue = PICK_SEQUENCE[t] == "B"
        mine, theirs = (blue, red) if is_blue else (red, blue)
        sign = 1.0 if is_blue else -1.0
        for lane in lanes:
            if lane in mine:
                continue
            taken = mine | {lane}
            nb, nr = (taken, theirs) if is_blue else (theirs, taken)
            yield lane, sign * gain(lane, mine, theirs), nb, nr

    @lru_cache(maxsize=None)
    def best(
        t: int, blue: FrozenSet[str], red: FrozenSet[str]
    ) -> Tuple[float, Optional[str], FrozenSet[str], FrozenSet[str]]:
        """(valeur future, poste du meilleur coup, blue suivant, red suivant) depuis l'état."""
        if t == len(PICK_SEQUENCE):
            return 0.0, None, blue, red
        options = [
            (signed + best(t + 1, nb, nr)[0], lane, nb, nr)
            for lane, signed, nb, nr in children(t, blue, red)
        ]
        # max/min rendent le premier élément optimal rencontré : ordre de LANES en cas d'égalité.
        choose = max if PICK_SEQUENCE[t] == "B" else min
        return choose(options, key=lambda option: option[0])

    line: List[Pick] = []
    blue: FrozenSet[str] = frozenset()
    red: FrozenSet[str] = frozenset()
    for t, letter in enumerate(PICK_SEQUENCE):
        _, lane, blue, red = best(t, blue, red)
        line.append(Pick(slot=t + 1, side="blue" if letter == "B" else "red", lane=lane))
    return line
