"""Tests for src/ui/team_builder_ui.py's volume-of-data display (SPEC-09 E5).

The Team Builder's optimal-trio result showed a score with no indicator of
how much data backed each champion, unlike the Live Coach
(recommendations.py, "· 91 696 games"). _games_tag() adds the same tag,
best-effort (never raises, even if the lookup fails).
"""

from unittest.mock import Mock, patch

from src.models import Matchup
from src.ui.team_builder_ui import _games_tag, run_optimal_team_builder


def _matchups(games):
    return [
        Matchup(
            enemy_name="LeeSin",
            winrate=52.0,
            delta1=100.0,
            delta2=150.0,
            pickrate=5.0,
            games=games,
        )
    ]


class TestGamesTag:
    def test_formats_the_games_count(self):
        assistant = Mock()
        assistant.get_matchups_for_draft.return_value = _matchups(91696)

        assert _games_tag(assistant, "Ahri", "middle") == " · 91 696 games"
        assistant.get_matchups_for_draft.assert_called_once_with("Ahri", lane="middle")

    def test_no_matchups_returns_zero_games_not_a_crash(self):
        assistant = Mock()
        assistant.get_matchups_for_draft.return_value = []

        assert _games_tag(assistant, "Malphite", "middle") == " · 0 games"

    def test_lookup_failure_is_swallowed(self):
        """Best-effort: a broken dependency must not break the display."""
        assistant = Mock()
        assistant.get_matchups_for_draft.side_effect = Exception("db down")

        assert _games_tag(assistant, "Ahri", "middle") == ""


class TestRunOptimalTeamBuilderTrioDisplay:
    def test_optimal_trio_result_shows_games_volume(self, capsys):
        """Choice 1 (trio optimal) must show the games volume behind the
        blind pick and both counterpicks, same convention as the Live
        Coach."""
        assistant = Mock()
        assistant.optimal_trio_from_pool.return_value = ("Aatrox", "Darius", "Garen", 12.5)
        assistant.get_matchups_for_draft.return_value = _matchups(1000)
        assistant.get_ban_recommendations.return_value = []

        with (
            patch("src.ui.team_builder_ui.Assistant", return_value=assistant),
            patch(
                "src.ui.team_builder_ui._select_pool_for_analysis",
                return_value=("MyPool", ["Aatrox", "Darius", "Garen"], "middle"),
            ),
            patch("builtins.input", side_effect=["1", "n"]),
        ):
            run_optimal_team_builder()

        out = capsys.readouterr().out
        assert "Blind Pick : Aatrox · 1 000 games" in out
        assert "Counterpicks : Darius · 1 000 games, Garen · 1 000 games" in out
