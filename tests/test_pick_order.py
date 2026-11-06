"""Ordre de pick conseillé (`src/analysis/pick_order.py`, SPEC-51 §1.3).

Les matrices sont fabriquées à la main ou tirées avec une graine fixe. L'optimum est recalculé par
une recherche exhaustive sans mémoïsation, indépendante de la programmation dynamique du module.
"""

import math
import random
from typing import Dict, FrozenSet, List, Tuple

import pytest

from src.analysis.pick_order import PICK_SEQUENCE, Pick, pick_order
from src.config_constants import scraping_config

LANES = scraping_config.LANES
Matrix = Dict[str, Dict[str, float]]


def _uniform(value: float) -> Matrix:
    return {lane: {other: value for other in LANES} for lane in LANES}


def _random_matrix(rng: random.Random) -> Matrix:
    return {lane: {other: rng.uniform(0.0, 6.0) for other in LANES} for lane in LANES}


def _cell(matrix: Matrix, lane: str, other: str) -> float:
    return matrix.get(lane, {}).get(other, 0.0)


def _gain(matchups: Matrix, synergies: Matrix, lane: str, mine: FrozenSet, theirs: FrozenSet):
    total = sum(_cell(matchups, lane, e) ** 2 for e in theirs)
    total += sum(_cell(synergies, lane, a) ** 2 for a in mine)
    return math.sqrt(total)


def _optimum(matchups: Matrix, synergies: Matrix, t: int = 0, blue=frozenset(), red=frozenset()):
    """Valeur optimale par recherche exhaustive (blue maximise, red minimise)."""
    if t == len(PICK_SEQUENCE):
        return 0.0
    is_blue = PICK_SEQUENCE[t] == "B"
    mine, theirs = (blue, red) if is_blue else (red, blue)
    values = []
    for lane in LANES:
        if lane in mine:
            continue
        signed = _gain(matchups, synergies, lane, mine, theirs) * (1 if is_blue else -1)
        taken = mine | {lane}
        nb, nr = (taken, theirs) if is_blue else (theirs, taken)
        values.append(signed + _optimum(matchups, synergies, t + 1, nb, nr))
    return max(values) if is_blue else min(values)


def _line_value(line: List[Pick], matchups: Matrix, synergies: Matrix) -> float:
    """Valeur signée d'une ligne de picks, rejouée pas à pas."""
    blue: FrozenSet = frozenset()
    red: FrozenSet = frozenset()
    total = 0.0
    for pick in line:
        is_blue = pick.side == "blue"
        mine, theirs = (blue, red) if is_blue else (red, blue)
        total += _gain(matchups, synergies, pick.lane, mine, theirs) * (1 if is_blue else -1)
        if is_blue:
            blue = blue | {pick.lane}
        else:
            red = red | {pick.lane}
    return total


def test_matrice_vide_rend_liste_vide():
    assert pick_order({}, {}) == []


def test_dix_picks_cinq_postes_par_cote():
    line = pick_order(_random_matrix(random.Random(0)), _random_matrix(random.Random(1)))

    assert [p.slot for p in line] == list(range(1, 11))
    assert [p.side for p in line] == [("blue" if c == "B" else "red") for c in PICK_SEQUENCE]
    for side in ("blue", "red"):
        lanes = [p.lane for p in line if p.side == side]
        assert sorted(lanes) == sorted(LANES)


def test_matrices_nulles_suivent_ordre_de_lanes():
    line = pick_order(_uniform(0.0), _uniform(0.0))

    assert [(p.side, p.lane) for p in line] == [
        ("blue", "top"),
        ("red", "top"),
        ("red", "jungle"),
        ("blue", "jungle"),
        ("blue", "middle"),
        ("red", "middle"),
        ("red", "bottom"),
        ("blue", "bottom"),
        ("blue", "support"),
        ("red", "support"),
    ]


def test_diagonale_forte_sur_un_poste_pick_en_fin_de_draft():
    matchups = _uniform(0.1)
    matchups["middle"]["middle"] = 10.0

    line = pick_order(matchups, _uniform(0.0))
    slots = {
        side: [p.slot for p in line if p.side == side and p.lane == "middle"]
        for side in ("blue", "red")
    }

    # Red prend le milieu en dernier ; blue le prend en avant-dernier, après que red a commencé.
    assert slots == {"blue": [8], "red": [10]}


def test_egalite_deterministe():
    matchups = _random_matrix(random.Random(2))
    synergies = _random_matrix(random.Random(3))

    assert pick_order(matchups, synergies) == pick_order(matchups, synergies)


def test_synergies_changent_l_ordre():
    # Matchups nuls : seules les synergies départagent les postes.
    zero = _uniform(0.0)
    synergies = {
        "top": {"jungle": 1.0, "middle": 0.0, "bottom": 6.0, "support": 0.0},
        "jungle": {"top": 1.0, "middle": 0.0, "support": 3.0, "bottom": 6.0},
        "middle": {"jungle": 0.0, "top": 0.0, "support": 6.0, "bottom": 6.0},
        "bottom": {"top": 6.0, "jungle": 6.0, "middle": 6.0, "support": 1.0},
        "support": {"jungle": 3.0, "middle": 6.0, "bottom": 1.0, "top": 0.0},
    }

    with_synergies = [p.lane for p in pick_order(zero, synergies)]
    without = [p.lane for p in pick_order(zero, _uniform(0.0))]

    assert without != with_synergies
    assert with_synergies == [
        "middle",
        "middle",
        "bottom",
        "bottom",
        "support",
        "support",
        "jungle",
        "jungle",
        "top",
        "top",
    ]


@pytest.mark.parametrize("seed", [0, 1, 2, 3, 4])
def test_valeur_de_la_ligne_egale_l_optimum_exhaustif(seed: int):
    rng = random.Random(seed)
    matchups = _random_matrix(rng)
    synergies = _random_matrix(rng)

    line = pick_order(matchups, synergies)

    assert _line_value(line, matchups, synergies) == pytest.approx(
        _optimum(matchups, synergies), abs=1e-9
    )
