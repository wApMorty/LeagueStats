"""SPEC-18 §4 : valeur d'un pool (un blind pick, des contre-picks) sur une lane."""

import pytest

from src.analysis.pool_value import PoolEvaluator
from src.analysis.scoring import ChampionScorer
from src.analysis.champion_scores import GlobalScoreCalculator
from src.analysis.tier_list import TierListGenerator


def _both_ways(insert_matchup, champion, enemy, delta2, games):
    insert_matchup(champion, enemy, 50.0 + delta2, 0.0, delta2, 10.0, games, lane="top")
    insert_matchup(enemy, champion, 50.0 - delta2, 0.0, -delta2, 10.0, games, lane="top")


def _neutral_lane(insert_matchup, size=10):
    """Des champions moyens, bien mesurés : sans eux, K s'estimerait sur 4
    champions et le petit échantillon de Kassadin passerait pour du signal."""
    for i in range(size):
        _both_ways(insert_matchup, f"Filler{i}", f"Filler{(i + 1) % size}", 0.0, 20000)


@pytest.fixture
def lane(db, insert_matchup):
    """Garen, le blind, perd contre Teemo. Darius bat Teemo sur beaucoup de
    parties ; Kassadin le bat de beaucoup, mais sur un échantillon minuscule."""
    _neutral_lane(insert_matchup)
    _both_ways(insert_matchup, "Garen", "Teemo", -4.0, 20000)
    _both_ways(insert_matchup, "Garen", "Darius", 1.0, 20000)
    _both_ways(insert_matchup, "Darius", "Teemo", 4.0, 20000)
    _both_ways(insert_matchup, "Kassadin", "Teemo", 15.0, 100)
    return PoolEvaluator(db, "top")


def test_counter_duo_prefers_measured_advantage_over_thin_sample(lane):
    with_darius = lane.counter_value(["Garen", "Darius"])
    with_kassadin = lane.counter_value(["Garen", "Kassadin"])

    assert with_darius > with_kassadin


def test_counter_value_takes_the_best_champion_per_enemy(lane):
    """Ajouter un champion au pool ne peut jamais faire baisser sa valeur."""
    assert lane.counter_value(["Garen", "Darius"]) >= lane.counter_value(["Garen"])


def test_floor_scores_a_champion_only_where_it_beats_the_lane_average(lane):
    alone = lane.counter_value(["Darius"])
    floored = lane.counter_value(["Darius"], floor=0.0)

    assert floored >= max(alone, 0.0)


def test_coverage_is_a_share_of_the_lane_games(lane):
    assert 0.0 <= lane.coverage(["Garen"]) < lane.coverage(["Garen", "Darius"]) <= 1.0


def test_counter_tier_list_ranks_on_counter_gain(db, insert_matchup):
    """La tier list contre-pick suit le gain de contre-pick, pas le pic
    d'impact brut : Darius, mesuré, devant Kassadin, spectaculaire sur 100 parties."""
    _neutral_lane(insert_matchup)
    for champion, enemy, delta2, games in [
        ("Garen", "Teemo", -4.0, 20000),
        ("Darius", "Teemo", 4.0, 20000),
        ("Kassadin", "Teemo", 15.0, 100),
    ]:
        _both_ways(insert_matchup, champion, enemy, delta2, games)
    db.init_champion_scores_table()
    scorer = ChampionScorer(db)
    GlobalScoreCalculator(db, scorer).calculate_all()

    tier_list = TierListGenerator(db, scorer).generate_tier_list(
        ["Darius", "Kassadin"], analysis_type="counter_pick", lane="top"
    )
    gains = {e["champion"]: e["metrics"]["counter_gain"] for e in tier_list}

    assert gains["Darius"] > gains["Kassadin"]
