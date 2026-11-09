"""SPEC-54 tâche 267, réduit en SPEC-55 tâche 276 : `_ranked` (src/analysis/pool_tree.py).

L'arbre lui-même se construit par `exposure_tree` (tests/test_exposure.py).
"""

from src.analysis.pool_tree import TreeChoice, _ranked


def test_ranked_valeur_decroissante_puis_nom_sans_casse():
    choices = [
        TreeChoice("b", 1.0),
        TreeChoice("Zed", 2.0),
        TreeChoice("A", 1.0),
        TreeChoice("c", 0.5),
    ]

    ranked = _ranked(choices)

    assert [c.champion for c in ranked] == ["Zed", "A", "b", "c"]
