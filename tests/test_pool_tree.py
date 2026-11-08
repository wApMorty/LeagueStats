"""SPEC-54 tâche 267 : arbre de décision du pool (src/analysis/pool_tree.py)."""

from src.analysis.pool_swipe import PoolScorer
from src.analysis.pool_tree import TreeChoice, build_tree


class FakeEvaluator:
    """Évaluateur factice aux valeurs données à la main, même interface que PoolEvaluator.

    Un champion sans valeur donnée vaut 0 face à chaque adversaire et a une force nulle.
    """

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


def _fixture():
    """Pool A, B, C ; adversaires E1 (0,2), E2 (0,5), E3 (0,3), sans force ni tirage.

    Valeurs contre E1 : A 3, C 2, B 1 ; contre E2 : B 2, C 1, A 0 ; contre E3 : A 1, C 0,5, B 0.
    """
    return FakeEvaluator(
        enemies=["E1", "E2", "E3"],
        popularity=[0.2, 0.5, 0.3],
        values={
            "A": [3.0, 0.0, 1.0],
            "B": [1.0, 2.0, 0.0],
            "C": [2.0, 1.0, 0.5],
        },
    )


def _names(choices):
    return [c.champion for c in choices]


def test_blind_table_holds_scorer_blind_in_decreasing_order():
    scorer = _scorer(_fixture())
    tree = build_tree(scorer, ["A", "B", "C"])

    assert sorted(_names(tree.blind)) == ["A", "B", "C"]
    for choice in tree.blind:
        assert choice.value == scorer.blind(choice.champion)
    values = [c.value for c in tree.blind]
    assert values == sorted(values, reverse=True)


def test_counter_table_holds_scorer_values_in_decreasing_order():
    scorer = _scorer(_fixture())
    tree = build_tree(scorer, ["A", "B", "C"])
    expected = {"E1": ["A", "C", "B"], "E2": ["B", "C", "A"], "E3": ["A", "C", "B"]}

    for enemy, _, table in tree.counters:
        assert _names(table) == expected[enemy]
        index = scorer.enemies.index(enemy)
        for choice in table:
            assert choice.value == scorer.values(choice.champion)[index]


def test_equal_values_are_ordered_alphabetically_without_regard_to_case():
    evaluator = FakeEvaluator(enemies=["Zed", "alpha"], popularity=[0.5, 0.5])
    tree = build_tree(_scorer(evaluator), ["b", "A", "c"])

    assert _names(tree.blind) == ["A", "b", "c"]
    assert _names(tree.counters[0][2]) == ["A", "b", "c"]
    # Popularités égales : adversaires dans l'ordre alphabétique sans casse.
    assert [enemy for enemy, _, _ in tree.counters] == ["alpha", "Zed"]


def test_leaf_with_seen_opponent_takes_counter_branch_without_regard_to_case():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])

    leaf = tree.leaf("e2", ())

    assert leaf.branch == "counter"
    assert leaf.opponent == "E2"
    assert leaf.skipped == ()
    assert _names(leaf.choices) == ["B", "C", "A"]
    assert leaf.choices[0] == TreeChoice("B", 2.0)


def test_leaf_without_opponent_or_with_unknown_opponent_takes_blind_branch():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])

    for opponent in (None, "Unknown"):
        leaf = tree.leaf(opponent, ())
        assert leaf.branch == "blind"
        assert leaf.opponent is None
        assert leaf.choices == tree.blind
        assert leaf.skipped == ()


def test_unavailable_is_compared_without_regard_to_case():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])

    leaf = tree.leaf("E2", ["b"])

    assert _names(leaf.choices) == ["C", "A"]
    assert leaf.skipped == ("B",)


def test_fallback_skips_first_choice_and_keeps_next_one():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])

    leaf = tree.leaf("E1", ["A"])

    assert _names(leaf.choices) == ["C", "B"]
    assert leaf.skipped == ("A",)


def test_unavailable_ranked_before_first_choice_are_all_skipped():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])

    leaf = tree.leaf("E1", ["a", "C"])

    assert _names(leaf.choices) == ["B"]
    assert leaf.skipped == ("A", "C")


def test_unavailable_ranked_after_first_choice_is_not_skipped():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])

    leaf = tree.leaf("E1", ["C"])

    assert _names(leaf.choices) == ["A", "B"]
    assert leaf.skipped == ()


def test_all_unavailable_gives_empty_choices_and_skipped():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])

    leaf = tree.leaf("E1", ["A", "B", "C"])

    assert leaf.choices == ()
    assert leaf.skipped == ()


def test_blind_branch_skips_unavailable_top_blind_champion():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])
    top = tree.blind[0].champion

    leaf = tree.leaf(None, [top])

    assert leaf.branch == "blind"
    assert leaf.skipped == (top,)
    assert leaf.choices == tree.blind[1:]


def test_duplicates_in_pool_are_kept_once_first_wins():
    tree = build_tree(_scorer(_fixture()), ["A", "a", "B"])

    assert _names(tree.blind).count("A") + _names(tree.blind).count("a") == 1
    assert sorted(c.casefold() for c in _names(tree.blind)) == ["a", "b"]
    assert len(tree.counters[0][2]) == 2


def test_empty_pool_gives_empty_tables():
    tree = build_tree(_scorer(_fixture()), [])

    assert tree.lane == "top"
    assert tree.blind == ()
    assert tree.counters == ()
    assert tree.leaf("E1", ()).choices == ()


def test_counters_are_sorted_by_popularity():
    tree = build_tree(_scorer(_fixture()), ["A", "B", "C"])

    assert [(enemy, pop) for enemy, pop, _ in tree.counters] == [
        ("E2", 0.5),
        ("E3", 0.3),
        ("E1", 0.2),
    ]
