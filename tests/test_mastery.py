"""Tests de src/analysis/mastery.py : shrink_k (méthode des moments) et masteries (SPEC-41)."""

import random

import pytest

from src.analysis.mastery import (
    ci95,
    decide,
    fit_logistic,
    leave_one_out_points,
    masteries,
    player_bootstrap,
    player_mean_bootstrap,
    pooled_shrink_k,
    shrink_k,
)
from src.analysis.probability import sigmoid


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


# ---------- étude du terme (tâche 199) ----------


def _simulated(b_offset: float, seed: int, n: int = 5_000):
    """Lignes [1, logit de draft, offset] et issues tirées d'une logistique connue, 50 joueurs."""
    rng = random.Random(seed)
    players, xs, ys = [], [], []
    for i in range(n):
        x = [1.0, rng.gauss(0.0, 0.3), rng.gauss(0.0, 5.0)]
        p = sigmoid(0.1 + 0.9 * x[1] + b_offset * x[2])
        players.append(f"p{i % 50}")
        xs.append(x)
        ys.append(1 if rng.random() < p else 0)
    return players, xs, ys


def test_fit_logistic_retrouve_les_coefficients_simules():
    """n = 5 000 : biais 0,1, draft 0,9, offset 0,08 retrouvés à ±0,15."""
    _, xs, ys = _simulated(0.08, seed=1)

    coef = fit_logistic(xs, ys)

    for got, want in zip(coef, (0.1, 0.9, 0.08)):
        assert got == pytest.approx(want, abs=0.15)


def test_bootstrap_par_joueur_effet_fort_puis_nul():
    """Effet fort : l'IC95 contient la vraie valeur et exclut 0 ; effet nul : il contient 0."""
    players, xs, ys = _simulated(0.08, seed=2)
    coef = fit_logistic(xs, ys)
    low, high = ci95([c[2] for c in player_bootstrap(players, xs, ys, coef, 300, seed=3)])
    assert low < 0.08 < high
    assert low > 0

    players, xs, ys = _simulated(0.0, seed=4)
    coef = fit_logistic(xs, ys)
    low, high = ci95([c[2] for c in player_bootstrap(players, xs, ys, coef, 300, seed=5)])
    assert low < 0 < high


def test_moyenne_bootstrap_par_joueur():
    """Les observations d'un même joueur sont tirées ensemble : un seul joueur donne sa moyenne."""
    assert set(player_mean_bootstrap(["a", "a"], [1.0, 3.0], 20, seed=0)) == {2.0}
    low, high = ci95(player_mean_bootstrap(["a", "b"], [0.0, 10.0], 200, seed=0))
    assert low == 0.0 and high == 10.0


@pytest.mark.parametrize(
    "coef_ci, gain_ci, adopted",
    [
        ((0.01, 0.05), (0.0001, 0.002), True),
        ((-0.01, 0.05), (0.0001, 0.002), False),
        ((0.01, 0.05), (-0.0001, 0.002), False),
        ((-0.05, -0.01), (-0.002, -0.0001), False),
    ],
)
def test_decide_seuil_fige(coef_ci, gain_ci, adopted):
    """Adopté seulement si l'IC du coefficient exclut 0 et celui du gain est positif."""
    assert decide(coef_ci, gain_ci) is adopted


@pytest.mark.parametrize("norms", [None, {"Gnar": 4.0, "Ahri": -1.0}])
def test_leave_one_out_egale_masteries_sur_les_autres_parties(norms):
    """L'offset en O(1) vaut `masteries` recalculé sans la partie, 0 pour un champion joué une fois."""
    rng = random.Random(7)
    games = [(rng.choice(["Gnar", "Ahri", "Lux"]), rng.gauss(0.0, 15.0)) for _ in range(25)]
    games.append(("Zed", 3.0))

    got = leave_one_out_points(games, k=6.0, norms=norms)

    for i, (champion, _) in enumerate(games):
        others = games[:i] + games[i + 1 :]
        mastery = masteries(others, k=6.0, norms=norms).get(champion)
        assert got[i] == pytest.approx(mastery.points if mastery else 0.0, abs=1e-9)
    assert got[-1] == 0.0


def test_pooled_shrink_k_ignore_le_niveau_des_joueurs():
    """300 joueurs de niveaux très différents (σ_joueur = 20), 1 à 6 champions chacun, effet de
    champion τ = 4 et bruit σ = 16 : K ≈ 16, quand centrer puis `shrink_k` écrase τ²."""
    rng = random.Random(43)
    players = []
    for _ in range(300):
        level = rng.gauss(0.0, 20.0)
        groups = {}
        for c in range(rng.randint(1, 6)):
            effect = rng.gauss(0.0, 4.0)
            groups[f"c{c}"] = [
                level + effect + rng.gauss(0.0, 16.0) for _ in range(rng.randint(2, 15))
            ]
        players.append(groups)

    k = pooled_shrink_k(players)

    assert k is not None
    assert 0.6 * 16 <= k <= 1.6 * 16


def test_pooled_shrink_k_un_joueur_valeur_a_la_main():
    """Un seul joueur, calculé à la main : σ² = 54 / 6 = 9, SS inter = 656,22 (moyenne 59/9),
    poids de τ² = 9 − 29/9, τ² = (656,22 − 2 × 9) / 5,778 = 110,46, K = 9 / τ² = 0,0815."""
    groups = {"a": [1.0, 5.0, 9.0], "b": [20.0, 24.0], "c": [-3.0, 1.0, 2.0, 0.0]}
    assert pooled_shrink_k([groups]) == pytest.approx(0.081478, abs=1e-5)
    assert shrink_k(groups) == pytest.approx(0.081478, abs=1e-5)
