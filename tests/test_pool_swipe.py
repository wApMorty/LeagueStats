"""SPEC-49 tâche 241 et SPEC-50 tâche 246 : pile de suggestions de pool (src/analysis/pool_swipe.py)."""

import pytest

from src.analysis.pool_swipe import PoolScorer, pool_score, swap_cards
from src.analysis.pool_value import PoolEvaluator
from src.config_constants import pool_stats_config


class FakeEvaluator:
    """Évaluateur factice aux valeurs données à la main, même interface que PoolEvaluator.

    Un champion sans valeur donnée vaut 0 face à chaque adversaire et a une force nulle.
    """

    counter_value = PoolEvaluator.counter_value

    def __init__(self, enemies, popularity, strength=None, values=None, lane="top"):
        self.lane = lane
        self.enemies = list(enemies)
        self.popularity = list(popularity)
        self.strength = {k.lower(): v for k, v in (strength or {}).items()}
        self._values = {k.lower(): v for k, v in (values or {}).items()}

    def values(self, champion):
        return self._values.get(champion.lower(), [0.0] * len(self.enemies))


def _scorer(evaluator, draws=None):
    """Scorer sans tirage, sauf s'il en reçoit."""
    return PoolScorer(evaluator, draws or {})


def _pool_fixture():
    """Pool [A, B] ; C est le seul entrant qui fait gagner le pool.

    Contre-pick : A bat E1, B bat E2, C bat E2 et s'accorde avec lui-même.
    Blind : A a la force 1,0 ; C a la force 2,0 (B : 0).
    """
    return FakeEvaluator(
        enemies=["E1", "E2", "C"],
        popularity=[0.5, 0.3, 0.2],
        strength={"A": 1.0, "B": 0.0, "C": 2.0},
        values={
            "A": [1.0, 0.0, 0.0],
            "B": [0.0, 2.0, 0.0],
            "C": [0.0, 3.0, 2.0],
        },
    )


def _two_champions():
    """C et D valent 1,0 face à tout (duels nuls) : deux entrants à gain 1,0 contre le pool [A]."""
    return FakeEvaluator(
        enemies=["C", "D"],
        popularity=[0.5, 0.5],
        strength={"C": 1.0, "D": 1.0},
        values={"C": [1.0, 1.0], "D": [1.0, 1.0]},
    )


def test_gain_uses_the_best_outgoing_and_splits_counter_and_blind():
    # Blinds sans tirage, pire duel sur 7 tirages (k = 7) :
    #   blind(A) : duels E1 0 (0,5), E2 −1 (0,3), C −1 (0,2) ; E[min] = −1 + 0,5^7 ; blind = 1/128 = 0,0078.
    #   blind(B) : duels 0, 2 (0,3), 0 ; seul E2 tiré sept fois donne 2 : blind = 2·0,3^7 = 0,0004.
    #   blind(C) : duels E1 −2 (0,625), E2 +1 (0,375) ; blind = 3·0,375^7 = 0,0031.
    # Counter base [A, B] = 0,5·1 + 0,3·2 = 1,1 ; blind base = max(A, B) = 0,0078.
    # Remplacer A par C : counter [C, B] = 1,3 (gain ½·0,2 = 0,1), blind max(C, B) = 0,0031 (gain −0,0023) : 0,0977.
    # Remplacer B par C : counter [A, C] = 1,8 (gain 0,35), blind max(A, C) = 0,0078 (gain 0) : 0,35.
    # Le sortant optimal est B. Entrants E1 et E2 : counter en baisse, gains négatifs, écartés.
    cards = swap_cards(_scorer(_pool_fixture()), ["A", "B"])

    assert [c.incoming for c in cards] == ["C"]
    card = cards[0]
    assert card.outgoing == "B"
    assert card.gain == pytest.approx(0.35)
    assert card.counter_gain == pytest.approx(0.35)
    assert card.blind_gain == pytest.approx(0.0)
    assert card.gain == pytest.approx(card.counter_gain + card.blind_gain)
    assert card.lane == "top"
    # Duel gagné : E2 passe de 2,0 (B) à 3,0 (C). L'entrant, lui, n'est pas un duel.
    assert [e for e, _ in card.wins] == ["E2"]
    assert card.wins[0][1] == pytest.approx(1.0)
    assert card.losses == ()


def test_pool_score_is_half_counter_plus_half_blind():
    scorer = _scorer(_pool_fixture())

    # counter(A, B) = 0,5·1 + 0,3·2 = 1,1 ; blind(A, B) = max(1/128, 0,0004) = 1/128.
    # score = ½·1,1 + ½·1/128 = 0,55390625.
    assert pool_score(scorer, ["A", "B"]) == pytest.approx(0.55390625)
    # Ce score ne dépend pas de l'ordre du pool.
    assert pool_score(scorer, ["B", "A"]) == pytest.approx(0.55390625)
    assert pool_score(scorer, []) == 0.0


def test_one_card_per_entrant_even_with_several_positive_outgoings():
    evaluator = FakeEvaluator(
        enemies=["E1", "E2", "C", "D"],
        popularity=[0.4, 0.3, 0.15, 0.15],
        strength={"A": 1.0, "B": 0.0, "C": 2.0, "D": 1.5},
        values={
            "A": [1.0, 0.0, 0.0, 0.0],
            "B": [0.0, 2.0, 0.0, 0.0],
            "C": [0.0, 3.0, 2.0, 0.0],
            "D": [0.0, 2.5, 0.0, 1.5],
        },
    )

    cards = swap_cards(_scorer(evaluator), ["A", "B"])
    incomings = [c.incoming for c in cards]

    # C : gain 0,3002 (sortant B) ; D : gain 0,1875 (sortant B). Les deux restent.
    assert incomings.count("C") == 1
    assert incomings.count("D") == 1
    assert len(incomings) == len(set(incomings))


def test_candidate_below_one_percent_is_excluded_and_one_percent_is_kept():
    # D a des valeurs nulles en duel (1,0 face à tous) : son blind vaut sa force, 1,0.
    # Sans cela, D perdrait 1,0 de blind contre E1 et serait écarté à tort.
    # E1 (0,981) : valeurs et force nulles, gain 0 : écarté. C (0,009) : sous le seuil.
    evaluator = FakeEvaluator(
        enemies=["E1", "C", "D"],
        popularity=[0.981, 0.009, 0.01],
        strength={"C": 1.0, "D": 1.0},
        values={"D": [1.0, 1.0, 1.0]},
    )

    cards = swap_cards(_scorer(evaluator), ["A"])

    assert [c.incoming for c in cards] == ["D"]


def test_passed_champion_is_excluded_without_regard_to_case():
    evaluator = _two_champions()

    assert [c.incoming for c in swap_cards(_scorer(evaluator), ["A"], passed=["c"])] == ["D"]
    assert [c.incoming for c in swap_cards(_scorer(evaluator), ["A"], passed=["D"])] == ["C"]
    assert swap_cards(_scorer(evaluator), ["A"], passed=["C", "d"]) == []


def test_excluded_champion_is_left_out_like_passed_without_regard_to_case():
    evaluator = _two_champions()

    assert [c.incoming for c in swap_cards(_scorer(evaluator), ["A"], excluded=["c"])] == ["D"]
    assert [c.incoming for c in swap_cards(_scorer(evaluator), ["A"], excluded=["D"])] == ["C"]
    assert swap_cards(_scorer(evaluator), ["A"], excluded=["C", "d"]) == []
    assert swap_cards(_scorer(evaluator), ["A"], passed=["c"], excluded=["D"]) == []


@pytest.mark.parametrize(("strength", "below"), [(0.38, True), (0.40, False)])
def test_below_noise_is_true_under_the_noise_threshold_and_false_at_it(strength, below):
    # Pool [A] face à un seul adversaire : gain = ½ · force de C = 0,19 ou 0,20.
    # Le blind de C vaut sa force (aucun autre adversaire) ; le counter reste à 0.
    evaluator = FakeEvaluator(enemies=["C"], popularity=[1.0], strength={"C": strength})

    (card,) = swap_cards(_scorer(evaluator), ["A"])

    assert card.gain == pytest.approx(strength / 2)
    assert card.below_noise is below


def test_cards_are_sorted_by_gain_then_name_and_never_have_a_non_positive_gain():
    # Valeur constante de chaque champion (duels nuls) : gain = sa force.
    # Delta 0,60 ; Alpha 0,20 ; Charlie 0,20 (égalité : nom) ; Foxtrot −0,10, écarté.
    evaluator = FakeEvaluator(
        enemies=["Delta", "Charlie", "Foxtrot", "Alpha"],
        popularity=[0.4, 0.3, 0.2, 0.1],
        strength={"Delta": 0.6, "Charlie": 0.2, "Alpha": 0.2, "Foxtrot": -0.1},
        values={
            "Delta": [0.6] * 4,
            "Charlie": [0.2] * 4,
            "Alpha": [0.2] * 4,
            "Foxtrot": [-0.1] * 4,
        },
    )

    cards = swap_cards(_scorer(evaluator), ["A"])

    assert [c.incoming for c in cards] == ["Delta", "Alpha", "Charlie"]
    assert all(c.gain > 0 for c in cards)


def test_empty_pool_or_no_enemies_gives_no_card():
    evaluator = _pool_fixture()
    no_enemies = FakeEvaluator(enemies=[], popularity=[], strength={"A": 1.0})

    assert swap_cards(_scorer(evaluator), []) == []
    assert swap_cards(_scorer(no_enemies), ["A"]) == []


def test_outgoing_is_a_pool_member_and_the_incoming_is_not_in_the_pool():
    scorer = _scorer(_pool_fixture())

    for card in swap_cards(scorer, ["B", "A"]):
        assert card.outgoing in ("B", "A")
        assert card.incoming.lower() not in ("a", "b")
    # C remplace B (gain 0,35) plutôt que A (gain 0,098).
    cards = swap_cards(scorer, ["B", "A"])
    assert cards[0].outgoing == "B"


def test_wins_and_losses_list_the_three_largest_moves_in_the_right_direction():
    # Pool [A] : A bat E1 (1,0), n'a rien contre E2..E5. Entrant C : E1 à 0 (perte de 1,0),
    # E2 à 2,0, E3 à 1,0, E4 à 3,0, E5 à 0,5. Son propre duel (C contre C) est écarté.
    evaluator = FakeEvaluator(
        enemies=["E1", "E2", "E3", "E4", "E5", "C"],
        popularity=[0.3, 0.25, 0.2, 0.1, 0.05, 0.1],
        strength={"A": 0.0, "C": 1.0},
        values={
            "A": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "C": [0.0, 2.0, 1.0, 3.0, 0.5, 1.0],
        },
    )

    (card,) = [c for c in swap_cards(_scorer(evaluator), ["A"]) if c.incoming == "C"]

    # Pondérés : E2 0,50 ; E4 0,30 ; E3 0,20 ; E5 0,025 (écarté, au-delà de 3).
    assert [e for e, _ in card.wins] == ["E2", "E4", "E3"]
    assert [d for _, d in card.wins] == [pytest.approx(2.0), pytest.approx(3.0), pytest.approx(1.0)]
    assert [e for e, _ in card.losses] == ["E1"]
    assert card.losses[0][1] == pytest.approx(-1.0)


@pytest.mark.parametrize(
    ("draws", "expected"),
    # Duels de A : E1 à −1 (poids 0,6), E2 à +2 (poids 0,4), force 0. Le min vaut +2 seulement si
    # les k tirages tombent tous sur E2 (0,4^k) : E[min] = 2·0,4^k − (1 − 0,4^k) = 3·0,4^k − 1.
    # k = 1 : moyenne pondérée 0,6·(−1) + 0,4·2 = 0,2 ; k grand : pire duel, −1.
    [(1, 0.2), (2, -0.52), (7, -0.9950848), (200, -1.0)],
)
def test_expected_min_over_k_draws_is_the_weighted_mean_then_the_worst_duel(
    monkeypatch, draws, expected
):
    monkeypatch.setattr(pool_stats_config, "POOL_BLIND_DRAWS", draws)
    evaluator = FakeEvaluator(
        enemies=["E1", "E2"], popularity=[0.6, 0.4], values={"A": [-1.0, 2.0]}
    )

    assert PoolScorer(evaluator, {}).blind("A") == pytest.approx(expected, abs=1e-9)


def test_homonym_is_left_out_of_the_blind_without_regard_to_case():
    # L'adversaire « c » est le champion lui-même : son duel (7,0 − 1,0 = 6) est écarté.
    # Reste D : duel 0,5 − 1,0 = −0,5, poids renormalisé 1 ; blind = 1,0 − 0,5 = 0,5.
    evaluator = FakeEvaluator(
        enemies=["c", "D"],
        popularity=[0.5, 0.5],
        strength={"C": 1.0},
        values={"C": [7.0, 0.5]},
    )

    assert PoolScorer(evaluator, {}).blind("C") == pytest.approx(0.5)


def test_draws_shift_values_and_blind_and_match_champions_without_regard_to_case():
    # Un seul ennemi E1 : duel de A = 1,0 − 1,0 = 0, donc blind = force − tirage.
    evaluator = FakeEvaluator(
        enemies=["E1"], popularity=[1.0], strength={"A": 1.0}, values={"A": [1.0]}
    )

    for draws in ({"a": 0.25}, {"A": 0.25}):
        scorer = PoolScorer(evaluator, draws)
        assert scorer.values("A") == [pytest.approx(0.75)]
        assert scorer.values("a") == [pytest.approx(0.75)]
        assert scorer.blind("A") == pytest.approx(0.75)
        assert scorer.counter_value(["A"]) == pytest.approx(0.75)
    # Champion sans tirage : valeurs brutes, rien retiré.
    assert PoolScorer(evaluator, {"A": 0.25}).values("E1") == [0.0]


def test_blind_gain_is_half_the_change_in_the_best_blind_and_draws_shrink_it():
    # Un seul ennemi C : pas de duel, blind = force − tirage. Pool [A] : force et valeur 0,1.
    # Entrant C : force et valeur 0,5. Counter 0,1 -> 0,5 : gain 0,2 ; blind 0,1 -> 0,5 : gain 0,2.
    evaluator = FakeEvaluator(
        enemies=["C"],
        popularity=[1.0],
        strength={"A": 0.1, "C": 0.5},
        values={"A": [0.1], "C": [0.5]},
    )

    (card,) = swap_cards(_scorer(evaluator), ["A"])

    assert card.counter_gain == pytest.approx(0.2)
    assert card.blind_gain == pytest.approx(0.2)
    assert card.gain == pytest.approx(0.4)

    # Tirage de C à 0,3 : valeur et blind de C à 0,2. Counter 0,1 -> 0,2 (gain 0,05), blind
    # 0,1 -> 0,2 (gain 0,05) : gain 0,1.
    (card,) = swap_cards(_scorer(evaluator, {"c": 0.3}), ["A"])

    assert card.counter_gain == pytest.approx(0.05)
    assert card.blind_gain == pytest.approx(0.05)
    assert card.gain == pytest.approx(0.1)


def test_real_evaluator_puts_the_expected_swap_first(db, insert_matchup):
    """Vrai PoolEvaluator : Darius bat Teemo et fait mieux que Garen contre lui."""

    def both_ways(champion, enemy, delta2, games):
        insert_matchup(champion, enemy, 50.0 + delta2, 0.0, delta2, 10.0, games, lane="top")
        insert_matchup(enemy, champion, 50.0 - delta2, 0.0, -delta2, 10.0, games, lane="top")

    for i in range(10):
        both_ways(f"Filler{i}", f"Filler{(i + 1) % 10}", 0.0, 20000)
    both_ways("Garen", "Teemo", -4.0, 20000)
    both_ways("Garen", "Darius", 1.0, 20000)
    both_ways("Darius", "Teemo", 4.0, 20000)
    both_ways("Kassadin", "Teemo", 15.0, 100)

    cards = swap_cards(_scorer(PoolEvaluator(db, "top")), ["Garen"])

    assert cards[0].incoming == "Darius"
    assert cards[0].outgoing == "Garen"
    assert cards[0].gain > 0
    assert all(c.incoming != "Kassadin" for c in cards)
