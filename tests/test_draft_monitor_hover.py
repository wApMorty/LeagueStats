"""Characterization tests for the initial-hover path of ``DraftMonitor``
(SPEC TODO E10 safety net).

Scope:
- ``_do_initial_hover``
- ``_get_best_champion_from_pool``

Every fallback of ``_get_best_champion_from_pool`` returns ``current_pool[0]``,
so the fixture pool is deliberately ordered so that the fallback champion is
NOT the best-scoring one — otherwise the tests could not tell the two apart.
"""

from unittest.mock import Mock, patch

import pytest

from src.config_constants import draft_config
from src.draft_monitor import DraftMonitor

POOL = ["Aatrox", "Darius", "Garen"]
CHAMPION_IDS = {1: "Aatrox", 2: "Darius", 3: "Garen"}


@pytest.fixture
def monitor():
    """DraftMonitor with mocked Assistant/LCUClient and a silent console."""
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            monitor = DraftMonitor(verbose=False, auto_hover=True)
    monitor.current_pool = list(POOL)
    monitor.champion_id_to_name = dict(CHAMPION_IDS)
    return monitor


def matchups(total_games):
    """One fake matchup carrying the whole game count."""
    return [Mock(games=total_games)]


class TestDoInitialHover:
    """``_do_initial_hover()``."""

    def test_nominal_flow(self, monitor, capsys):
        """Clears the console, announces the blind pick, hovers, shows bans."""
        with patch("src.draft_monitor.clear_console") as clear:
            with patch.object(monitor, "_get_best_champion_from_pool", return_value="Darius"):
                with patch.object(monitor, "_auto_hover_champion") as hover:
                    with patch.object(monitor, "_show_ban_recommendations_draft") as bans:
                        # Act
                        monitor._do_initial_hover()

        # Assert
        clear.assert_called_once_with()
        hover.assert_called_once_with("Darius", "Meilleur blind pick")
        bans.assert_called_once_with()
        assert monitor.last_recommendation == "Darius"

        out = capsys.readouterr().out
        assert "[INITIAL] Champion select démarré" in out
        assert "[PICK] MEILLEUR BLIND PICK DE VOTRE POOL :" in out
        assert "  [OK] Darius" in out
        assert "[INFO] En attente du début du draft..." in out

    def test_empty_pool_returns_early(self, monitor, capsys):
        """No pool -> no scoring, no hover, no ban recommendations."""
        monitor.current_pool = []

        with patch("src.draft_monitor.clear_console"):
            with patch.object(monitor, "_get_best_champion_from_pool") as best:
                with patch.object(monitor, "_auto_hover_champion") as hover:
                    with patch.object(monitor, "_show_ban_recommendations_draft") as bans:
                        monitor._do_initial_hover()

        best.assert_not_called()
        hover.assert_not_called()
        bans.assert_not_called()
        assert monitor.last_recommendation is None

        out = capsys.readouterr().out
        assert "[INITIAL] Champion select démarré" in out
        assert "MEILLEUR BLIND PICK" not in out

    def test_empty_pool_warning_is_verbose_only(self, monitor, capsys):
        monitor.current_pool = []
        monitor.verbose = True

        with patch("src.draft_monitor.clear_console"):
            monitor._do_initial_hover()

        assert "[ALERTE] [INITIAL-HOVER] Aucun champion dans la pool" in capsys.readouterr().out

    def test_dependency_failure_is_swallowed(self, monitor, capsys):
        """A raising dependency must never break champion select."""
        with patch("src.draft_monitor.clear_console"):
            with patch.object(
                monitor, "_get_best_champion_from_pool", side_effect=Exception("scorer down")
            ):
                with patch.object(monitor, "_show_ban_recommendations_draft") as bans:
                    # Act: must not raise
                    monitor._do_initial_hover()

        bans.assert_not_called()
        assert monitor.last_recommendation is None
        # Silent by default (verbose=False)
        assert "[INITIAL-HOVER] Erreur" not in capsys.readouterr().out

    def test_dependency_failure_message_is_verbose_only(self, monitor, capsys):
        monitor.verbose = True

        with patch("src.draft_monitor.clear_console"):
            with patch.object(
                monitor, "_get_best_champion_from_pool", side_effect=Exception("scorer down")
            ):
                monitor._do_initial_hover()

        out = capsys.readouterr().out
        assert "[ALERTE] [INITIAL-HOVER] Erreur lors du hover initial: scorer down" in out

    def test_hover_failure_still_shows_ban_recommendations(self, monitor):
        """``_auto_hover_champion`` swallows its own errors, so the flow goes on."""
        with patch("src.draft_monitor.clear_console"):
            with patch.object(monitor, "_get_best_champion_from_pool", return_value="Darius"):
                with patch.object(monitor, "_auto_hover_champion", return_value=False):
                    with patch.object(monitor, "_show_ban_recommendations_draft") as bans:
                        monitor._do_initial_hover()

        bans.assert_called_once_with()
        assert monitor.last_recommendation == "Darius"


class TestGetBestChampionFromPool:
    """``_get_best_champion_from_pool()``."""

    def test_returns_the_highest_scoring_champion(self, monitor):
        """Scores are sorted descending; Garen wins over the pool's first entry."""
        monitor.assistant.get_matchups_for_draft.return_value = matchups(1000)
        monitor.assistant.score_against_team.side_effect = [1.0, 2.0, 5.0]

        assert monitor._get_best_champion_from_pool() == "Garen"

    def test_scores_are_computed_as_blind_picks(self, monitor):
        """Blind pick = scored against an EMPTY enemy team."""
        monitor.assistant.get_matchups_for_draft.return_value = matchups(1000)
        monitor.assistant.score_against_team.return_value = 1.0

        monitor._get_best_champion_from_pool()

        for call in monitor.assistant.score_against_team.call_args_list:
            assert call.args[1] == []

    def test_unknown_champion_names_fall_back_to_first_of_pool(self, monitor):
        """No name matches the id mapping -> no id -> ``current_pool[0]``."""
        monitor.champion_id_to_name = {}

        assert monitor._get_best_champion_from_pool() == "Aatrox"
        monitor.assistant.get_matchups_for_draft.assert_not_called()

    def test_name_matching_is_case_insensitive(self, monitor):
        monitor.champion_id_to_name = {1: "AATROX", 2: "darius", 3: "GaReN"}
        monitor.assistant.get_matchups_for_draft.return_value = matchups(1000)
        monitor.assistant.score_against_team.side_effect = [1.0, 9.0, 2.0]

        assert monitor._get_best_champion_from_pool() == "darius"

    def test_no_matchup_data_falls_back_to_first_of_pool(self, monitor):
        monitor.assistant.get_matchups_for_draft.return_value = []

        assert monitor._get_best_champion_from_pool() == "Aatrox"
        monitor.assistant.score_against_team.assert_not_called()

    def test_champions_below_min_games_are_skipped(self, monitor):
        """Only champions with >= MIN_CHAMPION_GAMES total games get scored."""
        monitor.assistant.get_matchups_for_draft.side_effect = [
            matchups(draft_config.MIN_CHAMPION_GAMES - 1),  # Aatrox: too thin
            matchups(draft_config.MIN_CHAMPION_GAMES),  # Darius: exactly at the bar
            matchups(draft_config.MIN_CHAMPION_GAMES - 1),  # Garen: too thin
        ]
        monitor.assistant.score_against_team.return_value = 0.5

        assert monitor._get_best_champion_from_pool() == "Darius"
        assert monitor.assistant.score_against_team.call_count == 1

    def test_all_champions_below_min_games_fall_back_to_first_of_pool(self, monitor):
        monitor.assistant.get_matchups_for_draft.return_value = matchups(10)

        assert monitor._get_best_champion_from_pool() == "Aatrox"

    def test_dependency_exception_falls_back_to_first_of_pool(self, monitor):
        monitor.assistant.get_matchups_for_draft.side_effect = Exception("db down")

        assert monitor._get_best_champion_from_pool() == "Aatrox"

    def test_scoring_exception_falls_back_to_first_of_pool(self, monitor):
        monitor.assistant.get_matchups_for_draft.return_value = matchups(1000)
        monitor.assistant.score_against_team.side_effect = Exception("scorer down")

        assert monitor._get_best_champion_from_pool() == "Aatrox"

    def test_verbose_reports_the_selected_champion(self, monitor, capsys):
        monitor.verbose = True
        monitor.assistant.get_matchups_for_draft.return_value = matchups(1000)
        monitor.assistant.score_against_team.side_effect = [1.0, 2.0, 5.0]

        monitor._get_best_champion_from_pool()

        out = capsys.readouterr().out
        assert "[OK] [INITIAL-HOVER] Meilleur de la pool : Garen (+5.00% d'avantage)" in out

    def test_verbose_reports_the_failure(self, monitor, capsys):
        monitor.verbose = True
        monitor.assistant.get_matchups_for_draft.side_effect = Exception("db down")

        monitor._get_best_champion_from_pool()

        out = capsys.readouterr().out
        assert "[ALERTE] [INITIAL-HOVER] Erreur d'obtention du meilleur champion: db down" in out
