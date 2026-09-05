"""Tests for src/ui/tournament_display_ui.py's volume-of-data display.

SPEC-09 E5: the tournament coach screens showed an advantage score with no
indicator of how much data backed it, unlike the Live Coach
(recommendations.py, "· 91 696 games"). The matchups list was already
fetched right where the score is computed, so the games count is added
alongside it, same convention.
"""

from unittest.mock import Mock

from src.models import Matchup
from src.ui.tournament_display_ui import _analyze_complete_draft, _show_tournament_draft_state


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


def _assistant(games=91696, advantage=3.0):
    assistant = Mock()
    assistant.db.get_champion_matchups_by_name.return_value = _matchups(games)
    assistant.score_with_synergy.return_value = advantage
    assistant._calculate_team_winrate.return_value = {"team_winrate": 50.0 + advantage}
    return assistant


def test_draft_state_shows_games_volume_next_to_score(capsys):
    assistant = _assistant(games=91696)

    _show_tournament_draft_state(
        assistant,
        ally_team=["Ahri"],
        enemy_team=["Zed"],
        banned_champions=[],
        champion_pool=["Ahri"],
        lane="middle",
    )

    out = capsys.readouterr().out
    assert "91 696 games" in out


def test_draft_state_no_volume_line_without_enemy_team(capsys):
    """No enemy picked yet: unchanged behavior (name only, no score/volume)."""
    assistant = _assistant()

    _show_tournament_draft_state(
        assistant,
        ally_team=["Ahri"],
        enemy_team=[],
        banned_champions=[],
        champion_pool=["Ahri"],
        lane="middle",
    )

    out = capsys.readouterr().out
    assert "games" not in out


def test_final_analysis_shows_games_volume_for_both_teams(capsys):
    assistant = _assistant(games=1234)

    _analyze_complete_draft(assistant, ally_team=["Ahri"], enemy_team=["Zed"], lane="middle")

    out = capsys.readouterr().out
    assert out.count("1 234 games") == 2  # une fois par équipe


def test_final_analysis_missing_data_champion_has_no_volume_tag(capsys):
    """SPEC-09 principle carried over to E5: a champion with no matchups
    still shows 'Données insuffisantes', never a fabricated volume."""
    assistant = Mock()
    assistant.db.get_champion_matchups_by_name.return_value = []

    _analyze_complete_draft(assistant, ally_team=["Malphite"], enemy_team=["Zed"], lane="middle")

    out = capsys.readouterr().out
    assert "Données insuffisantes" in out
    assert "games" not in out
