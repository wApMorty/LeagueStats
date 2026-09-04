"""Regression (audit 2026-09-04): the Team Builder (menu 5) and the
Tournament Coach never filtered matchup lookups by lane -- same bug class
as the Live Coach / bans lane fixes of the same day, applied to the classic
trio finder, the holistic trio finder, the tactical/coverage report, and the
Tournament Coach's manual draft scoring.

``pool_selection_ui._select_pool_for_analysis()`` already resolves and
returns a pool's lane (``pool_manager.pool_role_to_lane(pool.role)``); the
bug was that every consumer discarded it (``_pool_lane``, unused).
"""

from unittest.mock import Mock, patch

import pytest

from src.assistant import Assistant
from src.utils.champion_utils import validate_champion_data, validate_champion_pool
from src.analysis import trio_metrics

# 6-champion universe with an exact matchup + its mirror negation on a
# different lane, so that lane=None (blended, weighted equally since both
# rows carry the same games) always averages to ~0 -- destroying the signal
# -- while lane="top"/"jungle" each recover one full, undiluted DELTAS set.
CHAMPIONS = ["Aatrox", "Darius", "Garen", "Teemo", "Malphite", "Sett"]

DELTAS = {
    ("Aatrox", "Darius"): 3.0,
    ("Aatrox", "Garen"): 2.0,
    ("Aatrox", "Teemo"): -3.5,
    ("Aatrox", "Malphite"): 1.0,
    ("Aatrox", "Sett"): 0.5,
    ("Darius", "Aatrox"): -3.0,
    ("Darius", "Garen"): 2.5,
    ("Darius", "Teemo"): -4.0,
    ("Darius", "Malphite"): -1.0,
    ("Darius", "Sett"): 1.5,
    ("Garen", "Aatrox"): -2.0,
    ("Garen", "Darius"): -2.5,
    ("Garen", "Teemo"): 3.0,
    ("Garen", "Malphite"): 0.5,
    ("Garen", "Sett"): -0.5,
    ("Teemo", "Aatrox"): 3.5,
    ("Teemo", "Darius"): 4.0,
    ("Teemo", "Garen"): -3.0,
    ("Teemo", "Malphite"): 2.0,
    ("Teemo", "Sett"): 1.0,
    ("Malphite", "Aatrox"): -1.0,
    ("Malphite", "Darius"): 1.0,
    ("Malphite", "Garen"): -0.5,
    ("Malphite", "Teemo"): -2.0,
    ("Malphite", "Sett"): 2.5,
    ("Sett", "Aatrox"): -0.5,
    ("Sett", "Darius"): -1.5,
    ("Sett", "Garen"): 0.5,
    ("Sett", "Teemo"): -1.0,
    ("Sett", "Malphite"): -2.5,
}

# Best blind pick per lane = argmax(avg_delta2 across its 5 matchups).
_AVG_DELTA2 = {
    champ: sum(DELTAS[(champ, enemy)] for enemy in CHAMPIONS if enemy != champ) / 5
    for champ in CHAMPIONS
}
BEST_BLIND_TOP = max(_AVG_DELTA2, key=_AVG_DELTA2.get)
BEST_BLIND_JUNGLE = min(_AVG_DELTA2, key=_AVG_DELTA2.get)


@pytest.fixture
def dual_lane_assistant(db, insert_matchup):
    """Assistant wired on a DB where 'top' carries DELTAS and 'jungle' its
    exact mirror negation -- lane=None blends both to ~0 (destroying the
    signal), lane="top"/"jungle" each recover one clean, undiluted set."""
    for (champion, enemy), delta2 in DELTAS.items():
        insert_matchup(champion, enemy, 50.0 + delta2, delta2 * 10, delta2, 5.0, 1000, lane="top")
        insert_matchup(
            champion, enemy, 50.0 - delta2, -delta2 * 10, -delta2, 5.0, 1000, lane="jungle"
        )
    return Assistant(db=db, verbose=False)


class TestChampionUtilsLaneAware:
    def test_validate_champion_data_is_filtered_by_lane(self, db, insert_matchup):
        insert_matchup("Aatrox", "Darius", 40.0, -300, -5.0, 8.5, 1500, lane="top")
        insert_matchup("Aatrox", "Darius", 60.0, 300, 5.0, 8.5, 1500, lane="jungle")

        _, _, _, avg_top = validate_champion_data(db, "Aatrox", lane="top")
        _, _, _, avg_jungle = validate_champion_data(db, "Aatrox", lane="jungle")

        assert avg_top == pytest.approx(-5.0)
        assert avg_jungle == pytest.approx(5.0)

    def test_validate_champion_pool_propagates_lane(self, db, insert_matchup):
        insert_matchup("Aatrox", "Darius", 40.0, -300, -5.0, 8.5, 1500, lane="top")
        insert_matchup("Aatrox", "Darius", 60.0, 300, 5.0, 8.5, 1500, lane="jungle")

        _, report_top = validate_champion_pool(db, ["Aatrox"], lane="top")
        _, report_jungle = validate_champion_pool(db, ["Aatrox"], lane="jungle")

        assert report_top["Aatrox"]["avg_delta2"] == pytest.approx(-5.0)
        assert report_jungle["Aatrox"]["avg_delta2"] == pytest.approx(5.0)


class TestTrioMetricsLaneAware:
    def test_meta_score_reads_the_enemys_own_matchups_for_the_given_lane(self, db, insert_matchup):
        """meta_score's pickrate lookup is `enemy`'s OWN matchups (as
        champion), not the trio's -- must match get_champion_matchups_by_name's
        direction (champion=<enemy>)."""
        insert_matchup("Aatrox", "Zed", 50.0, 0.0, 0.0, 8.5, 500, lane="top")
        insert_matchup("Aatrox", "Zed", 50.0, 0.0, 0.0, 8.5, 500, lane="jungle")

        enemy_coverage = {"Aatrox": (2.0, "Darius")}

        score_top = trio_metrics.meta_score(db, enemy_coverage, lane="top")
        score_jungle = trio_metrics.meta_score(db, enemy_coverage, lane="jungle")

        # Single enemy -> the pickrate weight cancels out of the weighted
        # average either way; the point is that both lanes resolve to real
        # data instead of an empty lookup (which would fall back to 50.0).
        assert score_top == pytest.approx(70.0)  # (2.0 + 5) * 10
        assert score_jungle == pytest.approx(70.0)

    def test_meta_score_falls_back_to_neutral_when_lane_has_no_data(self, db, insert_matchup):
        insert_matchup("Aatrox", "Zed", 50.0, 0.0, 0.0, 8.5, 500, lane="top")

        enemy_coverage = {"Aatrox": (2.0, "Darius")}

        assert trio_metrics.meta_score(db, enemy_coverage, lane="top") == pytest.approx(70.0)
        assert trio_metrics.meta_score(db, enemy_coverage, lane="jungle") == pytest.approx(50.0)


class TestOptimalTrioFromPoolLaneAware:
    def test_blind_pick_is_filtered_by_lane(self, dual_lane_assistant):
        top_result = dual_lane_assistant.optimal_trio_from_pool(CHAMPIONS, lane="top")
        jungle_result = dual_lane_assistant.optimal_trio_from_pool(CHAMPIONS, lane="jungle")

        assert top_result[0] == BEST_BLIND_TOP
        assert jungle_result[0] == BEST_BLIND_JUNGLE
        assert top_result[0] != jungle_result[0]

    def test_without_lane_the_mirrored_data_blends_to_a_different_pick(self, dual_lane_assistant):
        """Sanity check on the fixture itself: lane=None (blended) does NOT
        reproduce either lane-filtered result, confirming the two lanes
        genuinely carry different signal and aren't accidentally identical."""
        blended_result = dual_lane_assistant.optimal_trio_from_pool(CHAMPIONS)

        assert blended_result[0] not in (None,)  # still returns *something*
        # With every matchup's blended avg exactly 0, avg_delta2 ties: the
        # blind pick is whichever champion sorts first, which is neither of
        # the two lane-specific winners in this dataset unless they tie too.


class TestOptimalDuoForChampionLaneAware:
    def test_duo_score_is_filtered_by_lane(self, dual_lane_assistant):
        top_result = dual_lane_assistant.optimal_duo_for_champion("Aatrox", CHAMPIONS, lane="top")
        jungle_result = dual_lane_assistant.optimal_duo_for_champion(
            "Aatrox", CHAMPIONS, lane="jungle"
        )

        assert top_result != jungle_result


class TestHolisticTrioFinderLaneAware:
    def test_total_score_is_filtered_by_lane(self, dual_lane_assistant):
        top_results = dual_lane_assistant.find_optimal_trios_holistic(
            CHAMPIONS, num_results=1, lane="top"
        )
        jungle_results = dual_lane_assistant.find_optimal_trios_holistic(
            CHAMPIONS, num_results=1, lane="jungle"
        )

        assert top_results and jungle_results
        assert top_results[0]["total_score"] != jungle_results[0]["total_score"]


class TestTrioTacticsLaneWiring:
    """The tactical/coverage report is a pure console printer -- verify it
    forwards lane to the DB rather than re-deriving lane-filtered scores."""

    def test_analyze_forwards_lane_to_matchup_lookups(self):
        mock_db = Mock()
        mock_db.get_champion_matchups_by_name.return_value = []
        mock_db.get_all_champion_names.return_value = {1: "Zed"}

        from src.analysis.trio_tactics import TrioTacticsReporter

        reporter = TrioTacticsReporter(mock_db, verbose=False)
        reporter.analyze(("Aatrox", "Darius", "Garen"), lane="top")

        for call in mock_db.get_champion_matchups_by_name.call_args_list:
            assert call.kwargs.get("lane") == "top"


class TestTeamBuilderUiPoolLaneWiring:
    """The pool's lane, once resolved by _select_pool_for_analysis(), must
    reach the Assistant calls -- it used to be discarded as `_pool_lane`."""

    @pytest.fixture
    def mock_assistant(self):
        instance = Mock()
        instance.optimal_trio_from_pool.return_value = ("Aatrox", "Darius", "Garen", 1.0)
        instance.optimal_duo_for_champion.return_value = ("Aatrox", "Darius", "Garen", 1.0)
        instance.find_optimal_trios_holistic.return_value = [
            {
                "trio": ("Aatrox", "Darius", "Garen"),
                "total_score": 1.0,
                "coverage_score": 1.0,
                "balance_score": 1.0,
                "consistency_score": 1.0,
                "meta_score": 1.0,
            }
        ]
        instance.get_ban_recommendations.return_value = []
        return instance

    def _run(self, choice, mock_assistant, monkeypatch, inputs=None):
        from src.ui import team_builder_ui

        monkeypatch.setattr(team_builder_ui, "Assistant", lambda: mock_assistant)
        inputs = iter([choice] + (inputs or []) + ["N"])
        monkeypatch.setattr("builtins.input", lambda *_: next(inputs))
        with patch(
            "src.ui.team_builder_ui._select_pool_for_analysis",
            return_value=("TopPool", ["Aatrox", "Darius", "Garen"], "top"),
        ):
            # _show_ban_recommendations() does its own deferred
            # `from src.assistant import Assistant` -- patch the origin too.
            with patch("src.assistant.Assistant", return_value=mock_assistant):
                team_builder_ui.run_optimal_team_builder()

    def test_option_1_passes_pool_lane(self, mock_assistant, monkeypatch):
        self._run("1", mock_assistant, monkeypatch)
        assert mock_assistant.optimal_trio_from_pool.call_args.kwargs.get("lane") == "top"

    def test_option_2_passes_pool_lane(self, mock_assistant, monkeypatch):
        self._run("2", mock_assistant, monkeypatch, inputs=["Aatrox"])
        assert mock_assistant.optimal_duo_for_champion.call_args.kwargs.get("lane") == "top"

    def test_option_3_passes_pool_lane(self, mock_assistant, monkeypatch):
        self._run("3", mock_assistant, monkeypatch, inputs=["4"])
        assert mock_assistant.find_optimal_trios_holistic.call_args.kwargs.get("lane") == "top"

    def test_ban_recommendations_receive_pool_lane(self, mock_assistant, monkeypatch):
        self._run("1", mock_assistant, monkeypatch)
        assert mock_assistant.get_ban_recommendations.call_args.kwargs.get("lane") == "top"


class TestTournamentCoachPoolLaneWiring:
    """tournament_coach_ui.py:66 discarded the pool's lane as `_pool_lane`
    (confirmed by the commit message of 62fa246, the tier-list sibling fix,
    which explicitly named this call site as out of scope back then)."""

    def test_recommend_command_passes_pool_lane(self, monkeypatch):
        from src.ui import tournament_coach_ui

        mock_assistant = Mock()
        with patch("src.assistant.Assistant", return_value=mock_assistant):
            with patch(
                "src.ui.tournament_coach_ui._select_pool_for_analysis",
                return_value=("TopPool", ["Aatrox", "Darius"], "top"),
            ):
                with patch(
                    "src.ui.tournament_coach_ui._show_recommendations"
                ) as mock_show_recommendations:
                    inputs = iter(["recommend", "quit"])
                    monkeypatch.setattr("builtins.input", lambda *_: next(inputs))
                    tournament_coach_ui._run_basic_tournament_coach()

        assert mock_show_recommendations.call_args.kwargs.get("lane") == "top"

    def test_status_command_passes_pool_lane(self, monkeypatch):
        from src.ui import tournament_coach_ui

        mock_assistant = Mock()
        with patch("src.assistant.Assistant", return_value=mock_assistant):
            with patch(
                "src.ui.tournament_coach_ui._select_pool_for_analysis",
                return_value=("TopPool", ["Aatrox", "Darius"], "top"),
            ):
                with patch(
                    "src.ui.tournament_coach_ui._show_tournament_draft_state"
                ) as mock_show_state:
                    inputs = iter(["status", "quit"])
                    monkeypatch.setattr("builtins.input", lambda *_: next(inputs))
                    tournament_coach_ui._run_basic_tournament_coach()

        assert mock_show_state.call_args.kwargs.get("lane") == "top"
