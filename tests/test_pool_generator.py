"""SPEC-50 tâche 248 : générateur de pool (src/analysis/pool_generator.py), sur évaluateurs factices."""

import itertools
import random

import pytest

from src.analysis.pool_generator import _candidates, generate_pool, mean_score
from src.analysis.pool_swipe import PoolScorer, pool_score
from src.config_constants import pool_stats_config


class FakeEvaluator:
    """Évaluateur factice aux valeurs données, même interface que PoolEvaluator (sans maîtrise)."""

    def __init__(self, enemies, popularity, strength=None, values=None, lane="top"):
        self.lane = lane
        self.enemies = list(enemies)
        self.popularity = list(popularity)
        self.strength = {k.lower(): v for k, v in (strength or {}).items()}
        self._values = {k.lower(): v for k, v in (values or {}).items()}

    def values(self, champion):
        return self._values.get(champion.lower(), [0.0] * len(self.enemies))


def _random_scorers(rng, names, count=2):
    """``count`` scorers sur les mêmes ``names`` (12 candidats), valeurs tirées au hasard."""
    popularity = [rng.uniform(0.02, 1.0) for _ in names]
    total = sum(popularity)
    popularity = [p / total for p in popularity]
    scorers = []
    for _ in range(count):
        strength = {n: rng.uniform(-2.0, 2.0) for n in names}
        values = {n: [rng.uniform(-3.0, 3.0) for _ in names] for n in names}
        scorers.append(
            PoolScorer(
                FakeEvaluator(names, popularity, strength=strength, values=values),
                {},
            )
        )
    return scorers


def _uniform_scorer(names, values=None, strength=None, popularity=None):
    """Scorer à popularité égale sauf indication ; valeurs nulles par défaut."""
    count = len(names)
    return PoolScorer(
        FakeEvaluator(
            names,
            popularity or [1.0 / count] * count,
            strength=strength,
            values=values,
        ),
        {},
    )


@pytest.mark.parametrize("seed", range(25))
def test_result_is_locally_optimal_for_one_for_one_swaps(seed):
    """Sur 12 candidats et des tailles 3 à 5 : aucun échange un pour un ne gagne plus de 1e-12."""
    rng = random.Random(seed)
    names = [f"Champ{i:02d}" for i in range(12)]
    scorers = _random_scorers(rng, names)
    size = 3 + seed % 3

    result = generate_pool(scorers, size, excluded=())

    assert result is not None
    pool = list(result.champions)
    current = mean_score(scorers, pool)
    assert result.score == pytest.approx(current, abs=1e-9)
    candidates = _candidates(scorers, ())
    for i in range(size):
        for candidate in candidates:
            if candidate in pool:
                continue
            trial = pool[:i] + [candidate] + pool[i + 1 :]
            assert mean_score(scorers, trial) <= current + 1e-12


def test_greedy_alone_is_suboptimal_and_swaps_reach_the_exhaustive_optimum():
    """Cas construit à la main : 4 candidats à 0,25, taille 2, blinds sans tirage.

    Valeurs (lignes = champion, colonnes = ennemi A, B, C, D ; force 0 ; le blind d'un champion
    vaut E[min] de ses duels hors lui-même sur 7 tirages, poids égaux) :
        A : 2 3 1 1    blind A = 1 + 2/3^7 = 2189/2187
        B : 1 2 2 2    blind B = 1 + 2^7/3^7 = 2315/2187
        C : 0 3 3 3    blind C = 3 · (2/3)^7 = 384/2187
        D : 1 3 3 0    blind D = 1 + 2·(2/3)^7 = 2443/2187
    Contre-pick : Σ_ennemi ¼ · max valeur du pool. Pool de deux : J = ½ counter + ½ max blind.

    Glouton seul : D (J = ½·7/4 + ½·D = 1,433528, meilleur seul), puis C (J(D, C) = ½·10/4 +
    ½·D = 1,808528, contre 1,683528 pour D, A ou D, B) : pool {C, D}, J = 1,808528.
    Optimum : {A, C}, counter 11/4, blind max = A : J = 11/8 + 2189/4374 = 1,875457.
    Un seul échange (D → A) passe de {C, D} à {A, C}, gain 0,066929. Sans la boucle d'échanges,
    le test échoue.
    """
    names = ["A", "B", "C", "D"]
    values = {
        "A": [2.0, 3.0, 1.0, 1.0],
        "B": [1.0, 2.0, 2.0, 2.0],
        "C": [0.0, 3.0, 3.0, 3.0],
        "D": [1.0, 3.0, 3.0, 0.0],
    }
    scorer = _uniform_scorer(names, values=values)

    result = generate_pool([scorer], 2, excluded=())

    best = max(mean_score([scorer], list(combo)) for combo in itertools.combinations(names, 2))
    assert result is not None
    assert best == pytest.approx(11 / 8 + 2189 / 4374, abs=1e-9)
    assert result.score == pytest.approx(best, abs=1e-9)
    assert set(result.champions) == {"A", "C"}


def test_score_is_the_mean_of_per_scrape_scores_over_two_scorers():
    rng = random.Random(7)
    names = [f"Champ{i:02d}" for i in range(12)]
    scorers = _random_scorers(rng, names, count=2)

    result = generate_pool(scorers, 4, excluded=())

    expected = [pool_score(scorer, list(result.champions)) for scorer in scorers]
    assert result.per_scrape == pytest.approx(tuple(expected))
    assert result.score == pytest.approx(sum(expected) / 2)


def test_candidate_under_min_popularity_in_one_scrape_is_dropped():
    """Un champion à 0,5 % dans le scrape ancien est écarté, même très fort dans le récent."""
    names = ["A", "B", "C", "Rare"]
    recent = _uniform_scorer(
        names,
        values={"Rare": [5.0, 5.0, 5.0, 5.0]},
        strength={"Rare": 5.0},
    )
    old = _uniform_scorer(
        names,
        popularity=[0.33, 0.33, 0.335, 0.005],
    )
    assert 0.005 < pool_stats_config.POOL_SWIPE_MIN_POPULARITY

    result = generate_pool([recent, old], 3, excluded=())

    assert result is not None
    assert result.candidates == 3
    assert "Rare" not in result.champions


def test_excluded_champions_are_ignored_whatever_the_case():
    names = ["Ahri", "Zed", "Yasuo", "Lux"]
    strength = {"Ahri": 9.0, "Zed": 1.0, "Yasuo": 1.0, "Lux": 1.0}
    scorer = _uniform_scorer(names, strength=strength)

    result = generate_pool([scorer], 2, excluded=["AHRI"])

    assert result is not None
    assert "Ahri" not in result.champions
    assert result.candidates == 3


def test_too_few_candidates_returns_none():
    names = ["A", "B", "C"]
    scorer = _uniform_scorer(names)

    assert generate_pool([scorer], 4, excluded=()) is None
    assert generate_pool([scorer], 3, excluded=["A"]) is None
    assert generate_pool([], 3, excluded=()) is None


def test_ties_go_to_alphabetical_order():
    """Trois champions identiques : le premier par ordre alphabétique est pris."""
    names = ["Zed", "Ahri", "Milio"]
    scorer = _uniform_scorer(names)

    result = generate_pool([scorer], 1, excluded=())

    assert result is not None
    assert result.champions == ("Ahri",)


def test_champions_are_sorted_by_blind_on_the_most_recent_scrape():
    names = ["Weak", "Strong", "Mid", "Enemy"]
    # Valeur constante = force : le duel vaut 0, donc blind = force.
    values = {"Weak": [0.5] * 4, "Strong": [3.0] * 4, "Mid": [1.5] * 4, "Enemy": [0.0] * 4}
    recent = _uniform_scorer(
        names,
        values=values,
        strength={"Weak": 0.5, "Strong": 3.0, "Mid": 1.5, "Enemy": 0.0},
    )
    old = _uniform_scorer(names, strength={"Weak": 9.0})

    result = generate_pool([recent, old], 3, excluded=())

    assert result is not None
    blinds = [blind for _, blind in result.blind]
    assert [name for name, _ in result.blind] == list(result.champions)
    assert blinds == sorted(blinds, reverse=True)
    assert result.champions[0] == "Strong"


def test_counter_share_sums_to_one_and_is_per_champion():
    names = ["A", "B", "C", "D"]
    values = {
        "A": [1.0, 0.0, 0.0, 0.0],
        "B": [0.0, 2.0, 0.0, 0.0],
        "C": [0.0, 0.0, 0.5, 0.5],
        "D": [0.0, 0.0, 0.5, 0.5],
    }
    scorer = _uniform_scorer(names, values=values)

    result = generate_pool([scorer], 3, excluded=())

    assert result is not None
    shares = dict(result.counter_share)
    assert set(shares) == set(result.champions)
    assert sum(shares.values()) == pytest.approx(1.0)


def test_generate_pool_ne_construit_pas_d_arbre():
    """L'arbre se pose par la route (règle D, `exposure_tree`) : le générateur le laisse à None."""
    names = ["Big", "Mid", "Small", "Tiny"]
    values = {n: [1.0, 1.0, 1.0, 1.0] for n in names}
    scorer = _uniform_scorer(names, values=values, popularity=[0.5, 0.3, 0.19, 0.01])

    result = generate_pool([scorer], 3, excluded=())

    assert result is not None
    assert result.tree is None
