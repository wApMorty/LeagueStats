"""Regression test — tier list generator ignored the lane filter.

Bug report (2026-09-04): the user noticed the tier list generator didn't use
the lane column already wired into the Live Coach (fix #46,
get_matchups_for_draft(lane=...)). Investigation confirmed champion_scores
held a single score per champion, computed by
GlobalScoreCalculator.calculate_all() from
db.get_champion_matchups_by_name(champion) with no lane filter -- a
multi-lane champion's matchups from every lane were blended into one score.
TierListGenerator.generate_tier_list()/Assistant.generate_tier_list() had no
`lane` parameter to scope them, even though the pool selector already tracks
each pool's role/lane (src/pool_manager.py ChampionPool.role) and discarded
it before calling into the tier list generator.

Fix: champion_scores gained a `lane` column (migration
3e87f22f2ec1_add_lane_column_to_champion_scores.py, composite PK
(id, lane)). GlobalScoreCalculator now saves one row per champion for the
toutes-lanes aggregate (lane=analysis_config.ALL_LANES_KEY) plus one row per
scraping_config.LANES value the champion has matchups for.
TierListGenerator.generate_tier_list() and Assistant.generate_tier_list()
gained an optional `lane` parameter threaded through to
db.get_all_champion_scores()/get_champion_scores_by_name(), and the tier
list UI now passes the selected pool's lane
(via src.pool_manager.pool_role_to_lane()).
"""

import pytest

from src.analysis.champion_scores import GlobalScoreCalculator
from src.analysis.tier_list import TierListGenerator
from src.config_constants import analysis_config


def _insert_yasuo_matchups(insert_matchup):
    """Deliberately opposite matchups per lane: a lane-blind average sits
    between the two, so a lane-scoped score that fails to filter would not
    reproduce either raw value."""
    insert_matchup("Yasuo", "Darius", 40.0, -300.0, -2.0, 10.0, 1000, lane="top")
    insert_matchup("Yasuo", "Zed", 60.0, 300.0, 2.6, 10.0, 1000, lane="middle")


class TestGlobalScoreCalculatorLaneScoping:
    """GlobalScoreCalculator must persist one row per (champion, lane)."""

    def test_calculate_all_saves_one_row_per_lane_plus_aggregate(self, db, scorer, insert_matchup):
        _insert_yasuo_matchups(insert_matchup)
        db.init_champion_scores_table()

        rows_scored = GlobalScoreCalculator(db, scorer).calculate_all()

        # Yasuo: 'all' + 'top' + 'middle' = 3 rows. jungle/bottom/support have
        # no matchup data for Yasuo and must be skipped, not fabricated.
        assert rows_scored == 3

    def test_lane_scoped_scores_diverge_from_each_other_and_from_aggregate(
        self, db, scorer, insert_matchup
    ):
        _insert_yasuo_matchups(insert_matchup)
        db.init_champion_scores_table()
        GlobalScoreCalculator(db, scorer).calculate_all()

        top_score = db.get_champion_scores_by_name("Yasuo", lane="top")
        mid_score = db.get_champion_scores_by_name("Yasuo", lane="middle")
        all_score = db.get_champion_scores_by_name("Yasuo", lane=analysis_config.ALL_LANES_KEY)

        assert top_score["avg_delta2"] == pytest.approx(-2.0)
        assert mid_score["avg_delta2"] == pytest.approx(2.6)
        # Before the fix, only one lane-blind row existed and every lane
        # query would have returned the same blended value.
        assert top_score["avg_delta2"] != mid_score["avg_delta2"]
        assert all_score["avg_delta2"] == pytest.approx((-2.0 + 2.6) / 2)


class TestTierListGeneratorLaneParameter:
    """generate_tier_list() must scope champion_scores lookups to `lane`."""

    def test_generate_tier_list_scopes_to_requested_lane(self, db, scorer, insert_matchup):
        _insert_yasuo_matchups(insert_matchup)
        db.init_champion_scores_table()
        GlobalScoreCalculator(db, scorer).calculate_all()

        tier_gen = TierListGenerator(db, scorer)

        top_result = tier_gen.generate_tier_list(["Yasuo"], lane="top")
        mid_result = tier_gen.generate_tier_list(["Yasuo"], lane="middle")

        assert top_result and mid_result
        top_delta2 = top_result[0]["metrics"]["avg_delta2_raw"]
        mid_delta2 = mid_result[0]["metrics"]["avg_delta2_raw"]

        assert top_delta2 == pytest.approx(-2.0)
        assert mid_delta2 == pytest.approx(2.6)
        assert top_delta2 != mid_delta2

    def test_generate_tier_list_defaults_to_all_lanes_aggregate(self, db, scorer, insert_matchup):
        """lane=None must keep the historical toutes-lanes behavior (used by
        multi-lane/custom pools that don't map to a single lane)."""
        _insert_yasuo_matchups(insert_matchup)
        db.init_champion_scores_table()
        GlobalScoreCalculator(db, scorer).calculate_all()

        tier_gen = TierListGenerator(db, scorer)
        result = tier_gen.generate_tier_list(["Yasuo"])

        assert result
        assert result[0]["metrics"]["avg_delta2_raw"] == pytest.approx((-2.0 + 2.6) / 2)
