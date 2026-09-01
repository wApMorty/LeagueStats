"""Regression guard for SPEC-05 B7: the old clamp on team winrate must never
reappear. Before B7, ChampionScorer.calculate_team_winrate clamped individual
winrates to [20, 80] and the geometric-mean result to [25, 75] -- an
arbitrary ceiling/floor, not a real prediction. 5 champions stacked at an
extreme, DB-realistic matchup (delta2 near the real min/max cited in
SPEC-05 §1.2: -51.43 / +31.74) used to hit that ceiling/floor exactly.
"""

from src.analysis.probability import sigmoid


def _advantage_percent(scorer, delta2: float) -> float:
    """delta2 -> saturating win-probability delta, in percentage points
    (mirrors what score_against_team now returns, SPEC-05 B7)."""
    logit_advantage = scorer.delta2_to_win_advantage(delta2)
    return (sigmoid(logit_advantage) - 0.5) * 100.0


def test_extreme_advantage_does_not_hit_old_clamp_ceiling(scorer):
    # delta2 = 31.74 is the real DB maximum cited in SPEC-05 §1.2 -- worst
    # case: 5 champions all in this extreme a matchup at once.
    advantage_pct = _advantage_percent(scorer, 31.74)
    individual_winrates = [50.0 + advantage_pct] * 5

    result = scorer.calculate_team_winrate(individual_winrates)
    team_winrate = result["team_winrate"]

    assert team_winrate != 75.0  # the old [25, 75] clamp is gone
    assert team_winrate < 100.0
    assert team_winrate > 0.0


def test_extreme_disadvantage_does_not_hit_old_clamp_floor(scorer):
    # delta2 = -51.43 is the real DB minimum cited in SPEC-05 §1.2.
    advantage_pct = _advantage_percent(scorer, -51.43)
    individual_winrates = [50.0 + advantage_pct] * 5

    result = scorer.calculate_team_winrate(individual_winrates)
    team_winrate = result["team_winrate"]

    assert team_winrate != 25.0  # the old [25, 75] clamp is gone
    assert team_winrate > 0.0
    assert team_winrate < 100.0


def test_five_stacked_extreme_matchups_both_sides_stay_unclamped(scorer):
    """The full draft picture: our team stacked with the best possible
    matchup, the enemy team stacked with the worst -- neither team's
    predicted winrate lands on the old 25/75 clamp."""
    our_winrates = [50.0 + _advantage_percent(scorer, 31.74)] * 5
    enemy_winrates = [50.0 + _advantage_percent(scorer, -51.43)] * 5

    our_result = scorer.calculate_team_winrate(our_winrates)
    enemy_result = scorer.calculate_team_winrate(enemy_winrates)

    for team_winrate in (our_result["team_winrate"], enemy_result["team_winrate"]):
        assert team_winrate not in (25.0, 75.0)
        assert 0.0 < team_winrate < 100.0
