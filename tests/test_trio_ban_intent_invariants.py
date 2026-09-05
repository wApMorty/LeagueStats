"""Intent tests for src/analysis/trio_* and src/analysis/ban_recommendations.py
(SPEC-10 S3.5).

These modules already sit at 73-88% line coverage (see
docs/specs/SPEC-10-couverture-chemin-critique.md S2) via characterization
tests in tests/test_assistant_trio_*.py and tests/test_ban_recommendations.py
-- tests that pin whatever the code currently does, line by line, without
asserting *why* it should do that. They would not have caught (and would not
catch a reintroduction of) the September 2026 lane bug: nothing in them
requires that a lane-scoped query actually stays scoped to that lane.

This file adds a *few* narrow business-invariant tests instead, each
targeting one thing a characterization test cannot express. Two of them
(TestHolisticTrioFinderLaneIsolation, TestCounterpickTrioFinderLaneIsolation)
exercise trio_holistic.py/trio_counterpick.py directly -- not through
src.assistant.Assistant, unlike the existing
tests/test_trio_lane_aware.py::TestOptimalTrioFromPoolLaneAware, which is a
facade-level regression test for the same bug class. Locking it at both
layers means a future refactor of Assistant's wiring cannot silently drop the
lane parameter again without both suites noticing.

Per the spec: verified while writing that each test below actually fails if
its invariant is broken (lane arg dropped / threat formula inverted /
already-banned guard removed).
"""

from unittest.mock import Mock, patch

import pytest

from src.analysis.ban_recommendations import BanRecommender
from src.analysis.trio_counterpick import CounterpickTrioFinder
from src.analysis.trio_holistic import HolisticTrioFinder
from src.analysis.trio_weights import AdaptiveWeightCalculator
from src.draft.ban_advice import BanAdvisor
from src.draft.state import DraftState
from src.models import Matchup


def _dummy_validate_pool(pool):
    """A validate_pool stub that considers every champion viable."""
    report = {
        champ: {"avg_delta2": 0.0, "total_games": 1000, "matchups": 5, "has_data": True}
        for champ in pool
    }
    return list(pool), report


class TestHolisticTrioFinderLaneIsolation:
    """HolisticTrioFinder.find() called directly (no Assistant facade)."""

    def test_find_forwards_lane_to_the_bulk_matchup_load(self):
        mock_db = Mock()
        mock_db.get_all_matchups_bulk.return_value = {}
        mock_db.get_all_champion_names.return_value = {}
        weights = AdaptiveWeightCalculator(mock_db, verbose=False)
        finder = HolisticTrioFinder(mock_db, weights, verbose=False)

        finder.find(
            ["Aatrox", "Darius", "Garen"],
            num_results=1,
            validate_pool=_dummy_validate_pool,
            lane="top",
        )

        mock_db.get_all_matchups_bulk.assert_called_once_with(lane="top")

    def test_find_without_lane_requests_the_unscoped_bulk_load(self):
        """None (default) must reach the DB as None, not silently default to
        some lane -- this is the "no regression on the unscoped path" half of
        the same invariant."""
        mock_db = Mock()
        mock_db.get_all_matchups_bulk.return_value = {}
        mock_db.get_all_champion_names.return_value = {}
        weights = AdaptiveWeightCalculator(mock_db, verbose=False)
        finder = HolisticTrioFinder(mock_db, weights, verbose=False)

        finder.find(
            ["Aatrox", "Darius", "Garen"], num_results=1, validate_pool=_dummy_validate_pool
        )

        mock_db.get_all_matchups_bulk.assert_called_once_with(lane=None)


class TestCounterpickTrioFinderLaneIsolation:
    """CounterpickTrioFinder.optimal_trio_from_pool() called directly (no
    Assistant facade) -- the classic blind-pick + counterpick-duo search."""

    def test_optimal_trio_from_pool_forwards_lane_to_matchup_lookups(self):
        mock_db = Mock()
        mock_db.get_all_champion_names.return_value = {1: "Zed"}
        mock_db.get_champion_matchups_by_name.return_value = [
            Matchup(
                enemy_name="Zed", winrate=50.0, delta1=0.0, delta2=1.0, pickrate=5.0, games=1000
            )
        ]
        tactics = Mock()
        finder = CounterpickTrioFinder(mock_db, tactics, verbose=False)

        finder.optimal_trio_from_pool(
            ["Aatrox", "Darius", "Garen"], validate_pool=_dummy_validate_pool, lane="top"
        )

        assert mock_db.get_champion_matchups_by_name.call_count > 0
        for call in mock_db.get_champion_matchups_by_name.call_args_list:
            assert call.kwargs.get("lane") == "top"
        tactics.analyze.assert_called_once()
        assert tactics.analyze.call_args.kwargs.get("lane") == "top"


class TestBanRecommenderThreatMonotonicity:
    """A worse best-response delta2 (i.e. our pool counters that enemy worse)
    can never be ranked as LESS threatening than a better one, all else
    (pickrate, coverage) held equal -- the ordering that pool bans exist to
    get right."""

    def test_worse_matchup_is_ranked_at_least_as_threatening(self, db, insert_matchup):
        # Aatrox vs Darius: our best (only) response is a bad matchup (-5.0).
        insert_matchup("Aatrox", "Darius", 30.0, -500, -5.0, 10.0, 1000)
        # Aatrox vs Garen: our best (only) response is a mild matchup (-2.0).
        insert_matchup("Aatrox", "Garen", 45.0, -200, -2.0, 10.0, 1000)

        recommender = BanRecommender(db, verbose=False)
        recs = recommender.get_ban_recommendations(["Aatrox"], num_bans=5)

        by_enemy = {enemy: threat for enemy, threat, *_ in recs}
        assert by_enemy["Darius"] > by_enemy["Garen"]
        assert recs[0][0] == "Darius"  # sorted descending by threat

    def test_equal_matchups_produce_equal_threat(self, db, insert_matchup):
        """Sanity check on the fixture itself: with identical delta2,
        pickrate and coverage, threat scores must tie (not be swayed by
        insertion order or champion name)."""
        insert_matchup("Aatrox", "Darius", 40.0, -300, -3.0, 10.0, 1000)
        insert_matchup("Aatrox", "Garen", 40.0, -300, -3.0, 10.0, 1000)

        recommender = BanRecommender(db, verbose=False)
        recs = recommender.get_ban_recommendations(["Aatrox"], num_bans=5)

        by_enemy = {enemy: threat for enemy, threat, *_ in recs}
        assert by_enemy["Darius"] == pytest.approx(by_enemy["Garen"])


class TestBanAdvisorNeverHoversAnAlreadyBannedChampion:
    """BanAdvisor.handle_auto_ban_hover() is the layer where the current
    draft's bans actually reach the ban recommendation -- BanRecommender
    itself is state-blind (no ally_bans/enemy_bans param), so this guard is
    the whole enforcement point today."""

    def _make_monitor(self, top_recommendation="Darius"):
        monitor = Mock()
        monitor.verbose = False
        monitor.pool_name = None  # force the real-time fallback path
        monitor.current_pool = ["Aatrox"]
        monitor.pool_lane = None
        monitor.last_ban_recommendation = None
        monitor.assistant.get_ban_recommendations.return_value = [
            (top_recommendation, 12.0, -5.0, "Aatrox", 1)
        ]
        monitor._is_player_ban_turn.return_value = True
        monitor._get_display_name.side_effect = lambda champ_id: {1: "Darius"}.get(
            champ_id, f"Champion{champ_id}"
        )
        return monitor

    def test_skips_hover_when_top_recommendation_is_already_banned(self, capsys):
        monitor = self._make_monitor(top_recommendation="Darius")
        advisor = BanAdvisor(monitor)
        state = DraftState(phase="BAN_PICK", ally_bans=[1], enemy_bans=[])

        advisor.handle_auto_ban_hover(state)

        monitor._auto_hover_champion.assert_not_called()
        assert "déjà banni" in capsys.readouterr().out

    def test_hovers_when_top_recommendation_is_not_banned(self):
        monitor = self._make_monitor(top_recommendation="Darius")
        monitor._auto_hover_champion.return_value = True
        advisor = BanAdvisor(monitor)
        state = DraftState(phase="BAN_PICK", ally_bans=[], enemy_bans=[])

        advisor.handle_auto_ban_hover(state)

        monitor._auto_hover_champion.assert_called_once()
        assert monitor._auto_hover_champion.call_args.args[0] == "Darius"

    def test_case_insensitive_comparison_still_catches_the_ban(self, capsys):
        """_get_display_name and the recommendation can differ in case
        (LCU display name vs. DB champion name) -- the guard must not miss
        a match because of it."""
        monitor = self._make_monitor(top_recommendation="darius")
        advisor = BanAdvisor(monitor)
        state = DraftState(phase="BAN_PICK", ally_bans=[1], enemy_bans=[])

        advisor.handle_auto_ban_hover(state)

        monitor._auto_hover_champion.assert_not_called()
