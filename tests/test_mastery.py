"""Tests de src/analysis/mastery.py : shrink_k (méthode des moments) et masteries (SPEC-41)."""

import math
import random
from unittest.mock import Mock

import pytest

from src.analysis.mastery import (
    MasteryTerm,
    ci95,
    decide,
    fit_logistic,
    leave_one_out_matchup_deviation,
    leave_one_out_points,
    masteries,
    matchup_deviations,
    matchup_shrink_k,
    player_bootstrap,
    player_mean_bootstrap,
    pooled_shrink_k,
    shrink_k,
    term_of,
    to_win_points,
    with_term,
)
from src.analysis.probability import sigmoid
from src.config_constants import analysis_config


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


# ---------- le terme dans le moteur (tâche 200) ----------


def _capture(db, game_id: int, champion: str, delta_p: float, queue_id: int = 420) -> None:
    """Une partie capturée de @pj35 (participant 1) avec son impact ΔP et son champion."""
    cursor = db.connection.cursor()
    cursor.execute("INSERT OR IGNORE INTO champions (name, role) VALUES (?, 'top')", (champion,))
    champion_id = cursor.execute("SELECT id FROM champions WHERE name = ?", (champion,)).fetchone()[
        0
    ]
    cursor.execute(
        "INSERT INTO game_records (game_id, queue_id, game_creation_utc, player_participant_id, "
        "raw_game, captured_utc) VALUES (?, ?, ?, 1, '{}', '2026-10-21')",
        (game_id, queue_id, f"2026-10-21 10:{game_id:02d}:00"),
    )
    cursor.execute(
        "INSERT INTO game_metrics (game_id, participant_id, metric, is_player, champion_id, value) "
        "VALUES (?, 1, 'cs_14', 1, ?, 0)",
        (game_id, champion_id),
    )
    for share in (0.5, 0.5):  # deux lignes d'impact : la somme fait foi
        cursor.execute(
            "INSERT INTO game_impact VALUES (?, 1, 0, 'kill', ?, 'v')", (game_id, delta_p * share)
        )
    db.connection.commit()


def test_mastery_term_charge_les_parties_capturees(db):
    """3 parties de Gnar à −0,10 et 2 d'Olaf à +0,05 : logit = coefficient × points rétrécis à K."""
    for game_id, (champion, delta) in enumerate(
        [("Gnar", -0.10), ("Gnar", -0.10), ("Gnar", -0.10), ("Olaf", 0.05), ("Olaf", 0.05)], 1
    ):
        _capture(db, game_id, champion, delta)
    _capture(db, 9, "Gnar", 0.90, queue_id=440)  # Flex : hors MASTERY_QUEUE_IDS

    term = MasteryTerm.load(db)

    expected = masteries([("Gnar", -10.0)] * 3 + [("Olaf", 5.0)] * 2, analysis_config.MASTERY_K)[
        "Gnar"
    ].points
    assert term.games("gnar") == 3
    assert term.logit("GNAR") == pytest.approx(analysis_config.MASTERY_LOGIT_PER_POINT * expected)
    assert term.logit("Gnar") < 0 < term.logit("Olaf")
    assert term.points("Gnar") == pytest.approx(to_win_points(term.logit("Gnar")))
    assert term.logit("Teemo") == 0.0 and term.games("Teemo") == 0


def test_mastery_term_vide_sans_parties_ou_en_erreur(db):
    """Base sans parties : terme vide ; requête qui lève : terme vide, sans exception."""
    assert MasteryTerm.load(db).logit("Gnar") == 0.0

    broken = Mock()
    broken.get_all_champion_names.side_effect = RuntimeError("base fermée")
    assert MasteryTerm.load(broken).logit("Gnar") == 0.0
    with pytest.raises(RuntimeError):
        MasteryTerm.read(broken)  # `read` laisse l'appelant garder son terme


def test_with_term_ajoute_le_terme_en_log_odds():
    """Valeur écrite à la main : p = 0,6, terme 0,2 -> 1 / (1 + exp(−(ln(0,6 / 0,4) + 0,2)))."""
    expected = 1.0 / (1.0 + math.exp(-(math.log(0.6 / 0.4) + 0.2)))
    assert with_term(0.6, 0.2) == pytest.approx(expected, abs=1e-12)
    assert with_term(0.6, 0.0) == 0.6


def test_term_of_ignore_un_monitor_mock():
    """Un monitor `Mock()` n'a pas de vrai terme : `term_of` rend un terme vide, pas un Mock."""
    assert term_of(Mock()).logit("Gnar") == 0.0
    real = MasteryTerm({"Gnar": masteries([("Gnar", -10.0), ("Olaf", 10.0)], 1.0)["Gnar"]})
    monitor = Mock()
    monitor.mastery = real
    assert term_of(monitor) is real


# ---------- maîtrise par matchup (SPEC-42, tâche 204) ----------


def test_matchup_shrink_k_retrouve_le_k_synthetique():
    """400 (joueur, champion) : niveau propre gauss(0, 20), 2 à 6 vis-à-vis, effet de case τ = 4,
    bruit σ = 16, 2 à 10 parties par case : K₂ attendu = 256 / 16 = 16, à ±20 % (graine fixe)."""
    rng = random.Random(42)
    cells = []
    for _ in range(400):
        level = rng.gauss(0.0, 20.0)
        mapping = {}
        for v in range(rng.randint(2, 6)):
            effect = rng.gauss(0.0, 4.0)
            mapping[f"v{v}"] = [
                level + effect + rng.gauss(0.0, 16.0) for _ in range(rng.randint(2, 10))
            ]
        cells.append(mapping)

    k2 = matchup_shrink_k(cells)

    assert k2 is not None
    assert 0.8 * 16 <= k2 <= 1.2 * 16


def test_matchup_shrink_k_none_sans_variance_entre_vis_a_vis():
    """Cases de même moyenne exacte (τ² ≤ 0) → None."""
    cells = [
        {"Darius": [1.0, 3.0], "Sylas": [0.0, 4.0]},
        {"Darius": [2.0, 2.0], "Sylas": [-1.0, 5.0]},
    ]
    assert matchup_shrink_k(cells) is None


def test_leave_one_out_matchup_egale_le_recalcul_sans_la_partie():
    """200 tirages de 30 parties (3 champions, 4 vis-à-vis dont None) : la valeur leave-one-out
    égale matchup_deviations recalculé sans la partie (0 si la case est absente), à 1e-9."""
    rng = random.Random(9)
    for _ in range(200):
        games = [
            (
                rng.choice(["Gnar", "Ahri", "Lux"]),
                rng.choice(["Darius", "Sylas", "Malphite", None]),
                rng.gauss(0.0, 15.0),
            )
            for _ in range(30)
        ]
        got = leave_one_out_matchup_deviation(games, k2=3.0)

        for i, (champion, opponent, _) in enumerate(games):
            others = games[:i] + games[i + 1 :]
            table = matchup_deviations(others, k2=3.0)
            want = (
                table[(champion, opponent)][1]
                if opponent is not None and (champion, opponent) in table
                else 0.0
            )
            assert got[i] == pytest.approx(want, abs=1e-9)


def test_matchup_deviation_vis_a_vis_inconnu_ou_case_unique():
    """Gnar : Darius 10, Darius 4, Sylas 0, None 2 ; k2 = 2. Champion = 4 (16 / 4).
    Darius 10 : case sans elle = 4, champion sans elle = 2 → (4 − 2) × 1 / 3 = 2/3.
    Darius 4 : case sans elle = 10, champion sans elle = 4 → (10 − 4) × 1 / 3 = 2.
    Sylas (case unique) et None → 0."""
    games = [
        ("Gnar", "Darius", 10.0),
        ("Gnar", "Darius", 4.0),
        ("Gnar", "Sylas", 0.0),
        ("Gnar", None, 2.0),
    ]

    got = leave_one_out_matchup_deviation(games, k2=2.0)

    assert got == pytest.approx([2.0 / 3.0, 2.0, 0.0, 0.0], abs=1e-9)
    table = matchup_deviations(games, k2=2.0)
    # Darius : 2 parties, moyenne 7 ; (7 − 4) × 2 / (2 + 2) = 1,5. Sylas : (0 − 4) × 1 / 3 = −4/3.
    assert table[("Gnar", "Darius")] == (2, pytest.approx(1.5, abs=1e-9))
    assert table[("Gnar", "Sylas")] == (1, pytest.approx(-4.0 / 3.0, abs=1e-9))
    assert ("Gnar", None) not in table
