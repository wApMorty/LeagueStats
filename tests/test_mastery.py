"""Tests de src/analysis/mastery.py : shrink_k (méthode des moments) et masteries (SPEC-41)."""

import random

import pytest

from src.analysis.mastery import masteries, shrink_k


def test_shrink_k_retrouve_le_k_synthetique():
    """200 groupes de 3 à 30 valeurs, τ = 4 et σ = 16 : K attendu = 256 / 16 = 16."""
    rng = random.Random(41)
    groups = {}
    for g in range(200):
        size = rng.randint(3, 30)
        effect = rng.gauss(0.0, 4.0)
        groups[f"c{g}"] = [effect + rng.gauss(0.0, 16.0) for _ in range(size)]

    k = shrink_k(groups)

    assert k is not None
    assert 0.8 * 16 <= k <= 1.2 * 16


def test_shrink_k_none_sans_variance_inter_groupe():
    """Groupes de même moyenne exacte (τ² estimé ≤ 0) → None ; un seul groupe → None."""
    same_mean = {"a": [-1.0, 1.0], "b": [-2.0, 0.0, 2.0]}
    assert shrink_k(same_mean) is None
    assert shrink_k({"a": [-1.0, 1.0, 3.0, -3.0]}) is None


def test_masteries_valeurs_connues():
    """Trois champions, valeurs calculées à la main : référence = 1,0."""
    games = [("Gnar", 2.0), ("Gnar", 4.0), ("Ahri", 1.0), ("Lux", -3.0)]

    result = masteries(games, k=2.0)

    assert result["Gnar"].games == 2
    assert result["Gnar"].raw_points == pytest.approx(2.0, abs=1e-9)
    assert result["Gnar"].points == pytest.approx(1.0, abs=1e-9)
    assert result["Ahri"].raw_points == pytest.approx(0.0, abs=1e-9)
    assert result["Ahri"].points == pytest.approx(0.0, abs=1e-9)
    assert result["Lux"].games == 1
    assert result["Lux"].raw_points == pytest.approx(-4.0, abs=1e-9)
    assert result["Lux"].points == pytest.approx(-4.0 / 3.0, abs=1e-9)


def test_masteries_retrecissement_monotone():
    """Même écart de champion, n croissant : |points| croît et reste sous |raw_points|."""
    k = 10.0
    previous = 0.0
    for n in (1, 2, 4, 8, 16, 32):
        games = [("X", 5.0)] * n + [("Y", 1.0)] * n
        mastery = masteries(games, k)["X"]

        assert mastery.raw_points == pytest.approx(2.0, abs=1e-9)
        assert abs(mastery.points) > previous
        assert abs(mastery.points) < abs(mastery.raw_points)
        previous = abs(mastery.points)


def test_masteries_variante_b_retranche_la_norme():
    """norms = {"Gnar": 5.0} : valeurs corrigées 3, 1 (Gnar) et 2, 0 (Ahri), référence 1,5.

    Gnar : moyenne 2, raw = 2 − 1,5 = 0,5. Ahri sans norme (0) : moyenne 1, raw = 1 − 1,5 = −0,5.
    Variante a sur les mêmes données donnait Gnar raw = 3 (référence 4).
    """
    games = [("Gnar", 8.0), ("Gnar", 6.0), ("Ahri", 2.0), ("Ahri", 0.0)]

    variante_a = masteries(games, k=0.0)
    variante_b = masteries(games, k=0.0, norms={"Gnar": 5.0})

    assert variante_a["Gnar"].raw_points == pytest.approx(3.0, abs=1e-9)
    assert variante_b["Gnar"].raw_points == pytest.approx(0.5, abs=1e-9)
    assert variante_b["Ahri"].raw_points == pytest.approx(-0.5, abs=1e-9)


def test_masteries_champion_jamais_joue_absent():
    """Un champion sans partie n'est pas dans le dict ; une liste vide donne {}."""
    result = masteries([("Gnar", 1.0), ("Gnar", 3.0)], k=5.0)

    assert set(result) == {"Gnar"}
    assert masteries([], k=5.0) == {}
