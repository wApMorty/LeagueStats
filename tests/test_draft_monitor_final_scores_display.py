"""Characterization tests for the FULL console output of
``DraftMonitor._calculate_final_scores`` (SPEC TODO E10 safety net).

``tests/test_predictions_log.py`` already covers the prediction-logging side
effect of this method. This file complements it by pinning the rendered team
tables, the sorting, the strength markers and the draft verdict — i.e. what
the user actually sees at the end of a draft.

The 5v5 draft below is fully deterministic: matchup scores are injected per
champion, and every synergy pair is worth +0.25.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor
from src.models import Matchup

ALLY_IDS = [1, 2, 3, 4, 5]
ENEMY_IDS = [6, 7, 8, 9, 10]

NAMES = {
    1: "Ally1",
    2: "Ally2",
    3: "Ally3",
    4: "Ally4",
    5: "Ally5",
    6: "Enemy6",
    7: "Enemy7",
    8: "Enemy8",
    9: "Enemy9",
    10: "Enemy10",
}

# Matchup score injected per champion name.
MATCHUP_SCORES = {
    "Ally1": 3.0,
    "Ally2": 1.5,
    "Ally3": 0.0,
    "Ally4": -1.5,
    "Ally5": -3.0,
    "Enemy6": 2.5,
    "Enemy7": 1.0,
    "Enemy8": -0.5,
    "Enemy9": -2.0,
    "Enemy10": -4.0,
}

# Each champion has 4 team-mates * 0.25 = +1.00 synergy, so with the default
# synergy_weight of 0.5 the total is simply matchup + 1.0.
SYNERGY_PER_PAIR = 0.25


@pytest.fixture
def monitor():
    """DraftMonitor wired on a deterministic, fully mocked Assistant."""
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            monitor = DraftMonitor(verbose=False, auto_hover=False)

    monitor.champion_id_to_name = dict(NAMES)

    monitor.assistant.get_matchups_for_draft.side_effect = lambda name, lane=None: [
        Matchup("Dummy", 50.0, 0.0, 0.0, 5.0, 1000)
    ]
    monitor.assistant.score_against_team.side_effect = lambda matchups, enemies, name, lane=None, enemy_lanes=None, player_lane=None: MATCHUP_SCORES[
        name
    ]
    monitor.assistant.db.get_synergy_delta2.return_value = SYNERGY_PER_PAIR
    # Ally team 55.0% vs enemy team 52.0% (first call = ally, second = enemy)
    monitor.assistant._calculate_team_winrate.side_effect = [
        {"team_winrate": 55.0},
        {"team_winrate": 52.0},
    ]
    monitor.assistant.db.insert_prediction.return_value = 7
    return monitor


@pytest.fixture
def output(monitor, capsys):
    """Run the analysis once and return the captured stdout."""
    with patch("src.draft.final_analysis.clear_console"):
        monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS, ally_lanes={1: "top"})
    return capsys.readouterr().out


class TestFinalScoresHeader:
    """Header and team composition block."""

    def test_header_block(self, output):
        assert "ANALYSE FINALE DU DRAFT - Scores individuels des champions" in output
        assert "=" * 80 in output

    def test_final_composition(self, output):
        assert "[TEAMS] COMPOSITION FINALE :" in output
        assert "  Équipe alliée :  Ally1 | Ally2 | Ally3 | Ally4 | Ally5" in output
        assert "  Équipe ennemie : Enemy6 | Enemy7 | Enemy8 | Enemy9 | Enemy10" in output

    def test_performance_section_title(self, output):
        assert "ANALYSE DE PERFORMANCE D'ÉQUIPE :" in output


class TestFinalScoresAllyTable:
    """The ally table: header, rows, sorting and strength markers."""

    def test_table_header(self, output):
        assert "VOTRE ÉQUIPE :" in output
        assert "  Champion        | Matchup | Synergy | Total" in output
        assert "  ----------------+---------+---------+-------" in output

    def test_rows_are_rendered_with_markers(self, output):
        """total = matchup + synergy (synergy_weight 0.5 -> both weights = 1)."""
        assert "  Ally1           | [++]  +3.0 | [+]  +1.0 | [++]  +4.0" in output
        assert "  Ally2           | [+]  +1.5 | [+]  +1.0 | [++]  +2.5" in output
        assert "  Ally3           | [~]  +0.0 | [+]  +1.0 | [+]  +1.0" in output
        assert "  Ally4           | [-]  -1.5 | [+]  +1.0 | [~]  -0.5" in output
        assert "  Ally5           | [--]  -3.0 | [+]  +1.0 | [-]  -2.0" in output

    def test_rows_are_sorted_by_total_descending(self, output):
        positions = [output.index(f"  Ally{i}           |") for i in range(1, 6)]
        assert positions == sorted(positions)


class TestFinalScoresEnemyTable:
    """The enemy table mirrors the ally one."""

    def test_table_header(self, output):
        assert "ÉQUIPE ENNEMIE :" in output

    def test_rows_are_rendered_with_markers(self, output):
        assert "  Enemy6          | [++]  +2.5 | [+]  +1.0 | [++]  +3.5" in output
        assert "  Enemy7          | [+]  +1.0 | [+]  +1.0 | [++]  +2.0" in output
        assert "  Enemy8          | [~]  -0.5 | [+]  +1.0 | [~]  +0.5" in output
        assert "  Enemy9          | [-]  -2.0 | [+]  +1.0 | [~]  -1.0" in output
        assert "  Enemy10         | [--]  -4.0 | [+]  +1.0 | [--]  -3.0" in output

    def test_rows_are_sorted_by_total_descending(self, output):
        positions = [output.index(f"  Enemy{i}") for i in (6, 7, 8, 9, 10)]
        assert positions == sorted(positions)


class TestFinalScoresComparison:
    """Team comparison, normalization and verdict."""

    def test_team_totals_and_winrates(self, output):
        """Ally total = 4.0 + 2.5 + 1.0 - 0.5 - 2.0 = +5.00,
        enemy total = 3.5 + 2.0 + 0.5 - 1.0 - 3.0 = +2.00."""
        assert "COMPARAISON DU DRAFT :" in output
        assert "  Votre équipe : +5.00% d'avantage total → 55.00% de winrate d'équipe" in output
        assert "  Équipe ennemie : +2.00% d'avantage total → 52.00% de winrate d'équipe" in output

    def test_normalized_expectation(self, output):
        """55 / (55 + 52) = 51.40% ; 52 / 107 = 48.60%."""
        assert "  Matchup attendu (normalisé) : 51.40% vs 48.60%" in output

    def test_verdict_bracket(self, output):
        """draft_diff = 51.4019 - 48.5981 = +2.80 -> the [2.5, 5.0) bracket."""
        assert "  Évaluation : Bon avantage de draft (+2.80% d'écart total)" in output

    def test_winrates_are_computed_from_total_scores(self, monitor):
        """Individual winrates fed to the team model are 50 + total_score."""
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS)

        ally_call, enemy_call = monitor.assistant._calculate_team_winrate.call_args_list
        assert sorted(ally_call.args[0]) == [48.0, 49.5, 51.0, 52.5, 54.0]
        assert sorted(enemy_call.args[0]) == [47.0, 49.0, 50.5, 52.0, 53.5]

    def test_prediction_is_logged_with_the_normalized_probability(self, monitor):
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS, ally_lanes={1: "top"})

        kwargs = monitor.assistant.db.insert_prediction.call_args.kwargs
        assert kwargs["ally_champions"] == ALLY_IDS
        assert kwargs["enemy_champions"] == ENEMY_IDS
        assert kwargs["ally_lanes"] == {1: "top"}
        assert kwargs["predicted_probability"] == pytest.approx(0.514018, abs=1e-5)
        assert monitor._last_prediction_id == 7


class TestFinalScoresDegradedCases:
    """Empty picks, missing data, and the resulting fallbacks."""

    def test_empty_picks_stop_after_the_header(self, monitor, capsys):
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores([], ENEMY_IDS)

        out = capsys.readouterr().out
        assert "[INFO] Draft incomplet - aucune analyse finale disponible" in out
        assert "COMPARAISON DU DRAFT" not in out

    def test_champion_without_enough_games_is_marked_insufficient(self, monitor, capsys):
        """< 500 total games -> the row shows "Données insuffisantes"."""

        def thin_data(name, lane=None):
            games = 10 if name == "Ally3" else 1000
            return [Matchup("Dummy", 50.0, 0.0, 0.0, 5.0, games)]

        monitor.assistant.get_matchups_for_draft.side_effect = thin_data

        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS)

        out = capsys.readouterr().out
        assert "  Ally3           | Données insuffisantes" in out
        # It is sorted last (sort key -999 when the matchup score is None)
        assert out.index("Ally3           | Données") > out.index("Ally5           |")

    def test_scoring_exception_is_marked_insufficient_too(self, monitor, capsys):
        """A raising scorer produces the very same "insufficient" row."""

        def flaky(matchups, enemies, name, lane=None, enemy_lanes=None, player_lane=None):
            if name == "Ally2":
                raise RuntimeError("scorer down")
            return MATCHUP_SCORES[name]

        monitor.assistant.score_against_team.side_effect = flaky

        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS)

        out = capsys.readouterr().out
        assert "  Ally2           | Données insuffisantes" in out

    def test_no_valid_ally_data_falls_back_to_neutral(self, monitor, capsys):
        monitor.assistant.get_matchups_for_draft.side_effect = lambda name, lane=None: (
            [] if name.startswith("Ally") else [Matchup("Dummy", 50.0, 0.0, 0.0, 5.0, 1000)]
        )
        monitor.assistant._calculate_team_winrate.side_effect = [{"team_winrate": 52.0}]

        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS)

        out = capsys.readouterr().out
        assert "  Votre équipe : Aucune donnée valide" in out
        assert "  Équipe ennemie : +2.00% d'avantage total" in out

    def test_no_valid_data_at_all_is_a_neutral_draft(self, monitor, capsys):
        """Both teams at the default 50.0 skip the normalization block."""
        monitor.assistant.get_matchups_for_draft.side_effect = lambda name, lane=None: []

        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS)

        out = capsys.readouterr().out
        assert "  Votre équipe : Aucune donnée valide" in out
        assert "  Équipe ennemie : Aucune donnée valide" in out
        assert "Matchup attendu (normalisé)" not in out
        assert "  Évaluation : Draft équilibré (+0.00% de différence)" in out

    def test_unknown_champion_id_uses_the_placeholder_name(self, monitor, capsys):
        monitor.champion_id_to_name = {}

        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores([1], [6])

        out = capsys.readouterr().out
        assert "  Équipe alliée :  Champion1" in out
        assert "  Équipe ennemie : Champion6" in out


class TestFinalScoresLaneAwareness:
    """Regression: the end-of-draft screen blended every lane a champion has
    ever played into one score (same bug class as fix #46, one screen
    further -- audit 2026-09-04). ``ally_lanes`` is actually
    ``state.inferred_roles``, covering both teams despite its name."""

    ROLE_MAP = {
        1: "top",
        2: "jungle",
        3: "middle",
        4: "bottom",
        5: "support",
        6: "top",
        7: "jungle",
        8: "middle",
        9: "bottom",
        10: "support",
    }

    def test_matchups_are_fetched_per_champion_own_lane(self, monitor):
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS, ally_lanes=self.ROLE_MAP)

        lane_by_champion = {
            call.args[0]: call.kwargs.get("lane")
            for call in monitor.assistant.get_matchups_for_draft.call_args_list
        }
        assert lane_by_champion == {
            "Ally1": "top",
            "Ally2": "jungle",
            "Ally3": "middle",
            "Ally4": "bottom",
            "Ally5": "support",
            "Enemy6": "top",
            "Enemy7": "jungle",
            "Enemy8": "middle",
            "Enemy9": "bottom",
            "Enemy10": "support",
        }

    def test_score_against_team_receives_own_lane_and_opposing_lane_map(self, monitor):
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS, ally_lanes=self.ROLE_MAP)

        kwargs_by_champion = {
            call.args[2]: call.kwargs
            for call in monitor.assistant.score_against_team.call_args_list
        }

        assert kwargs_by_champion["Ally1"]["lane"] == "top"
        assert kwargs_by_champion["Ally1"]["player_lane"] == "top"
        assert kwargs_by_champion["Ally1"]["enemy_lanes"] == {
            "Enemy6": "top",
            "Enemy7": "jungle",
            "Enemy8": "middle",
            "Enemy9": "bottom",
            "Enemy10": "support",
        }

        assert kwargs_by_champion["Enemy6"]["lane"] == "top"
        assert kwargs_by_champion["Enemy6"]["player_lane"] == "top"
        assert kwargs_by_champion["Enemy6"]["enemy_lanes"] == {
            "Ally1": "top",
            "Ally2": "jungle",
            "Ally3": "middle",
            "Ally4": "bottom",
            "Ally5": "support",
        }

    def test_synergy_score_is_filtered_to_own_lane(self, monitor):
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS, ally_lanes=self.ROLE_MAP)

        lanes_used = {
            call.kwargs.get("lane")
            for call in monitor.assistant.db.get_synergy_delta2.call_args_list
        }
        assert lanes_used == {"top", "jungle", "middle", "bottom", "support"}

    def test_missing_lane_info_preserves_unfiltered_behaviour(self, monitor):
        """No ally_lanes at all -> lane=None everywhere, identical to the
        pre-fix behaviour (backward compatible default)."""
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS)

        assert all(
            call.kwargs.get("lane") is None
            for call in monitor.assistant.get_matchups_for_draft.call_args_list
        )
        assert all(
            not call.kwargs.get("enemy_lanes")
            for call in monitor.assistant.score_against_team.call_args_list
        )
