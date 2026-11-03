"""SPEC-49 tâche 241 : calcul de la pile de suggestions de pool (src/analysis/pool_swipe.py)."""

import pytest

from src.analysis.pool_swipe import pool_score, swap_cards
from src.analysis.pool_value import PoolEvaluator


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


def test_gain_uses_the_best_outgoing_and_splits_counter_and_blind():
    # Remplacer A par C : counter 1,1 -> 1,3 (gain 0,1), blind 1,0 -> 2,0 (gain 0,5) : 0,6.
    # Remplacer B par C : counter 1,1 -> 1,8 (gain 0,35), blind 1,0 -> 2,0 (gain 0,5) : 0,85.
    # Le sortant optimal est B.
    cards = swap_cards(_pool_fixture(), ["A", "B"])

    assert [c.incoming for c in cards] == ["C"]
    card = cards[0]
    assert card.outgoing == "B"
    assert card.gain == pytest.approx(0.85)
    assert card.counter_gain == pytest.approx(0.35)
    assert card.blind_gain == pytest.approx(0.5)
    assert card.gain == pytest.approx(card.counter_gain + card.blind_gain)
    assert card.lane == "top"
    # Duel gagné : E2 passe de 2,0 (B) à 3,0 (C). L'entrant, lui, n'est pas un duel.
    assert [e for e, _ in card.wins] == ["E2"]
    assert card.wins[0][1] == pytest.approx(1.0)
    assert card.losses == ()


def test_pool_score_is_half_counter_plus_half_blind():
    evaluator = _pool_fixture()

    # counter(A, B) = 0,5·1 + 0,3·2 = 1,1 ; blind = 1,0 ; score = 1,05.
    assert pool_score(evaluator, ["A", "B"]) == pytest.approx(1.05)
    # Ce score ne dépend pas de l'ordre du pool.
    assert pool_score(evaluator, ["B", "A"]) == pytest.approx(1.05)
    assert pool_score(evaluator, []) == 0.0


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

    cards = swap_cards(evaluator, ["A", "B"])
    incomings = [c.incoming for c in cards]

    assert incomings.count("C") == 1
    assert incomings.count("D") == 1
    assert len(incomings) == len(set(incomings))


def test_candidate_below_one_percent_is_excluded_and_one_percent_is_kept():
    evaluator = FakeEvaluator(
        enemies=["E1", "C", "D"],
        popularity=[0.981, 0.009, 0.01],
        strength={"C": 1.0, "D": 1.0},
    )

    cards = swap_cards(evaluator, ["A"])

    assert [c.incoming for c in cards] == ["D"]


def test_passed_champion_is_excluded_without_regard_to_case():
    evaluator = FakeEvaluator(
        enemies=["C", "D"],
        popularity=[0.5, 0.5],
        strength={"C": 1.0, "D": 1.0},
    )

    assert [c.incoming for c in swap_cards(evaluator, ["A"], passed=["c"])] == ["D"]
    assert [c.incoming for c in swap_cards(evaluator, ["A"], passed=["D"])] == ["C"]
    assert swap_cards(evaluator, ["A"], passed=["C", "d"]) == []


@pytest.mark.parametrize(("strength", "below"), [(0.38, True), (0.40, False)])
def test_below_noise_is_true_under_the_noise_threshold_and_false_at_it(strength, below):
    # Pool [A] face à un seul adversaire : gain = ½ · force de C = 0,19 ou 0,20.
    evaluator = FakeEvaluator(enemies=["C"], popularity=[1.0], strength={"C": strength})

    (card,) = swap_cards(evaluator, ["A"])

    assert card.gain == pytest.approx(strength / 2)
    assert card.below_noise is below


def test_cards_are_sorted_by_gain_then_name_and_never_have_a_non_positive_gain():
    evaluator = FakeEvaluator(
        enemies=["Delta", "Charlie", "Foxtrot", "Alpha"],
        popularity=[0.4, 0.3, 0.2, 0.1],
        strength={"Delta": 0.6, "Charlie": 0.2, "Alpha": 0.2, "Foxtrot": -0.1},
    )

    cards = swap_cards(evaluator, ["A"])

    # Gains : Delta 0,30 ; Alpha 0,10 ; Charlie 0,10 (égalité : nom) ; Foxtrot < 0, écarté.
    assert [c.incoming for c in cards] == ["Delta", "Alpha", "Charlie"]
    assert all(c.gain > 0 for c in cards)


def test_empty_pool_or_no_enemies_gives_no_card():
    evaluator = _pool_fixture()
    no_enemies = FakeEvaluator(enemies=[], popularity=[], strength={"A": 1.0})

    assert swap_cards(evaluator, []) == []
    assert swap_cards(no_enemies, ["A"]) == []


def test_outgoing_is_a_pool_member_and_the_incoming_is_not_in_the_pool():
    evaluator = _pool_fixture()

    for card in swap_cards(evaluator, ["B", "A"]):
        assert card.outgoing in ("B", "A")
        assert card.incoming.lower() not in ("a", "b")
    cards = swap_cards(evaluator, ["B", "A"])
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

    (card,) = [c for c in swap_cards(evaluator, ["A"]) if c.incoming == "C"]

    # Pondérés : E2 0,50 ; E4 0,30 ; E3 0,20 ; E5 0,025 (écarté, au-delà de 3).
    assert [e for e, _ in card.wins] == ["E2", "E4", "E3"]
    assert [d for _, d in card.wins] == [pytest.approx(2.0), pytest.approx(3.0), pytest.approx(1.0)]
    assert [e for e, _ in card.losses] == ["E1"]
    assert card.losses[0][1] == pytest.approx(-1.0)


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

    cards = swap_cards(PoolEvaluator(db, "top"), ["Garen"])

    assert cards[0].incoming == "Darius"
    assert cards[0].outgoing == "Garen"
    assert cards[0].gain > 0
    assert all(c.incoming != "Kassadin" for c in cards)
