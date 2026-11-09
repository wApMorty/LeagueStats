"""SPEC-55 tâche 273 : règle D et arbre d'exposition (src/analysis/exposure.py)."""

import pytest

from src.analysis.exposure import d_scores, exposure_tree, lane_popularity
from src.analysis.mastery import to_win_points
from src.analysis.probability import winrate_points_to_logit
from src.config_constants import analysis_config


class FakeEvaluator:
    """Évaluateur factice, même interface que GameEvaluator pour la règle D.

    ``contribution`` = force de base + somme des ``matchup_logit`` contre les ennemis posés.
    Une paire absente vaut 0.
    """

    def __init__(self, base=None, logits=None, draws=None):
        self._base = {k.casefold(): v for k, v in (base or {}).items()}
        self._logits = {(a.casefold(), b.casefold()): v for (a, b), v in (logits or {}).items()}
        self._draws = {k.casefold(): v for k, v in (draws or {}).items()}

    def matchup_logit(self, champion, enemy):
        return self._logits.get((champion[0].casefold(), enemy[0].casefold()), 0.0)

    def draw_points(self, champion):
        return self._draws.get(champion[0].casefold(), 0.0)

    def contribution(self, champion, own_team, opposing_team):
        total = self._base.get(champion[0].casefold(), 0.0)
        return total + sum(self.matchup_logit(champion, enemy) for enemy in opposing_team)


class FakeDb:
    """Base factice : ``get_lane_winrates`` renvoie ``{nom: (winrate, games)}`` par lane."""

    def __init__(self, lanes):
        self._lanes = lanes

    def get_lane_winrates(self, lane):
        return dict(self._lanes.get(lane, {}))


# Deux adversaires sur la lane top, parts 0,75 / 0,25 ; C vaut −0,4 contre E1 et 0,8 contre E2.
TOP_POPULARITY = {"top": [("E1", 0.75), ("E2", 0.25)]}
TOP_LOGITS = {("C", "E1"): -0.4, ("C", "E2"): 0.8}


def _expected_two_duels():
    """E[min] de 7 tirages : −0,4 sauf si les 7 tirages tombent sur E2 (P = 0,25^7), alors 0,8."""
    return -0.4 * (1 - 0.25**7) + 0.8 * 0.25**7


def test_exposure_matches_hand_computed_expected_min():
    evaluator = FakeEvaluator(logits=TOP_LOGITS)
    (score,) = d_scores(evaluator, "top", ["C"], [], [], [], TOP_POPULARITY)

    assert score.exposure == pytest.approx(_expected_two_duels())
    assert score.known == pytest.approx(0.0)
    assert score.total == pytest.approx(score.known + score.exposure)


def test_posed_enemy_lane_leaves_exposure_others_stay():
    popularity = {
        "top": [("E1", 0.75), ("E2", 0.25)],
        "jungle": [("J1", 0.6), ("J2", 0.4)],
    }
    logits = {**TOP_LOGITS, ("C", "J1"): 0.5, ("C", "J2"): -0.2}
    evaluator = FakeEvaluator(logits=logits)

    (open_lanes,) = d_scores(evaluator, "top", ["C"], [], [], [], popularity)
    (jungle_posed,) = d_scores(evaluator, "top", ["C"], [], [("X", "jungle")], [], popularity)

    # Jungle triée : J2 = −0,2 (0,4), J1 = 0,5 (0,6) ; E[min] = −0,2·(1 − 0,6^7) + 0,5·0,6^7.
    jungle_part = -0.2 * (1 - 0.6**7) + 0.5 * 0.6**7
    assert open_lanes.exposure == pytest.approx(_expected_two_duels() + jungle_part)
    assert jungle_posed.exposure == pytest.approx(_expected_two_duels())


def test_taken_banned_and_candidate_are_excluded_from_draws():
    popularity = {"top": [("C", 0.2), ("E1", 0.3), ("E2", 0.3), ("E3", 0.2)]}
    logits = {("C", "C"): 5.0, ("C", "E1"): -0.4, ("C", "E2"): 0.8, ("C", "E3"): 0.1}
    evaluator = FakeEvaluator(logits=logits)

    # E1 pris (ennemi posé en jungle) : reste E2 (0,3) et E3 (0,2), renormalisés 0,6 / 0,4.
    # Duels triés : E3 = 0,1 (0,4), E2 = 0,8 (0,6) ; E[min] = 0,1·(1 − 0,6^7) + 0,8·0,6^7.
    (picked,) = d_scores(evaluator, "top", ["C"], [], [("E1", "jungle")], [], popularity)
    # E2 banni : reste E1 (0,3) et E3 (0,2), renormalisés 0,6 / 0,4.
    # Duels triés : E1 = −0,4 (0,6), E3 = 0,1 (0,4) ; E[min] = −0,4·(1 − 0,4^7) + 0,1·0,4^7.
    (banned,) = d_scores(evaluator, "top", ["C"], [], [], ["E2"], popularity)

    assert picked.exposure == pytest.approx(0.1 * (1 - 0.6**7) + 0.8 * 0.6**7)
    assert banned.exposure == pytest.approx(-0.4 * (1 - 0.4**7) + 0.1 * 0.4**7)


def test_allied_pick_does_not_remove_any_lane_from_exposure():
    popularity = {
        "top": [("E1", 0.75), ("E2", 0.25)],
        "jungle": [("J1", 0.6), ("J2", 0.4)],
    }
    logits = {**TOP_LOGITS, ("C", "J1"): 0.5, ("C", "J2"): -0.2}
    evaluator = FakeEvaluator(logits=logits)

    (alone,) = d_scores(evaluator, "top", ["C"], [], [], [], popularity)
    (with_ally,) = d_scores(evaluator, "top", ["C"], [("A1", "jungle")], [], [], popularity)

    assert with_ally.exposure == pytest.approx(alone.exposure)


@pytest.mark.parametrize("draw", [2.0, -1.5])
@pytest.mark.parametrize("vis_a_vis", [None, 0.6, -0.9])
def test_draw_is_removed_in_full_with_or_without_opponent(draw, vis_a_vis):
    logits = {} if vis_a_vis is None else {("C", "E"): vis_a_vis}
    evaluator = FakeEvaluator(base={"C": 0.3}, logits=logits, draws={"C": draw})
    enemies = [] if vis_a_vis is None else [("E", "top")]

    (score,) = d_scores(evaluator, "top", ["C"], [], enemies, [], {})

    expected = (
        0.3 + (vis_a_vis or 0.0) - winrate_points_to_logit(draw * analysis_config.K_INTRINSIC)
    )
    assert score.known == pytest.approx(expected)


def test_equal_totals_sort_by_name_and_unavailable_is_absent():
    evaluator = FakeEvaluator()

    scores = d_scores(evaluator, "top", ["Zed", "alpha", "Beta", "beta"], [], [], ["Zed"], {})

    assert [s.champion for s in scores] == ["alpha", "Beta"]


def test_lane_popularity_threshold_normalisation_and_empty_lane():
    db = FakeDb(
        {
            "top": {
                "A": (50.0, 120),
                "B": (50.0, 60),
                "C": (50.0, 17),
                "D": (50.0, 2),
                "E": (50.0, 1),
            },
        }
    )

    popularity = lane_popularity(db)

    assert [name for name, _ in popularity["top"]] == ["A", "B", "C", "D"]
    assert popularity["top"][0][1] == pytest.approx(0.6)
    assert popularity["top"][1][1] == pytest.approx(0.3)
    assert popularity["top"][2][1] == pytest.approx(0.085)
    assert popularity["top"][3][1] == pytest.approx(0.01)
    assert popularity["jungle"] == []


def test_exposure_tree_blind_and_counter_rows_match_d_scores():
    popularity = {"top": [("E1", 0.75), ("E2", 0.25)]}
    logits = {**TOP_LOGITS, ("D", "E1"): 0.3, ("E1", "C"): 0.2, ("E1", "D"): 0.1}
    evaluator = FakeEvaluator(base={"C": 0.4, "D": -0.1}, logits=logits, draws={"D": 1.0})
    pool = ["C", "D", "E1"]

    tree = exposure_tree(evaluator, "top", pool, popularity)

    blind_expected = {
        s.champion: to_win_points(s.total)
        for s in d_scores(evaluator, "top", pool, [], [], [], popularity)
    }
    assert {c.champion: c.value for c in tree.blind} == pytest.approx(blind_expected)

    enemy, share, row = tree.counters[0]
    assert (enemy, share) == ("E1", 0.75)
    row_expected = {
        s.champion: to_win_points(s.total)
        for s in d_scores(evaluator, "top", pool, [], [("E1", "top")], ["E1"], popularity)
    }
    assert {c.champion: c.value for c in row} == pytest.approx(row_expected)
    assert "E1" not in [c.champion for c in row]


def test_exposure_tree_empty_pool():
    tree = exposure_tree(FakeEvaluator(), "top", [], {"top": [("E1", 1.0)]})

    assert tree.lane == "top"
    assert tree.blind == ()
    assert tree.counters == ()
