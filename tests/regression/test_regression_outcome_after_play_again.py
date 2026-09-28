"""Régression (2026-09-28) : le résultat de partie n'était jamais labellisé en
fin de partie, et « Rejouer » effaçait le terminal.

Cause : une seule tentative par phase de fin (WaitingForStats, PreEndOfGame,
EndOfGame), toutes en quelques secondes, alors que l'historique LCU n'a pas
encore la partie ; « Rejouer » passait en Lobby, dont le reset appelait
clear_console(). Constaté sur la prédiction #91 : restée en attente alors que
sa partie (7998099468) s'apparie sans problème quelques minutes plus tard.
"""

from unittest.mock import Mock, patch

import pytest

from src.config_constants import draft_config
from src.draft_monitor import DraftMonitor

INTERVAL = draft_config.OUTCOME_RETRY_INTERVAL


@pytest.fixture
def monitor():
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            m = DraftMonitor(verbose=False, auto_hover=False, auto_accept_queue=False)
    m.lcu.is_in_champion_select.return_value = False
    return m


def _tick(monitor, phase, now, resolved=0):
    monitor.lcu.get_gameflow_session.return_value = {"phase": phase}
    with (
        patch("src.draft.lifecycle.time.time", return_value=now),
        patch("src.draft.lifecycle.clear_console") as clear,
        patch.object(monitor, "_resolve_pending_outcomes", return_value=resolved) as resolve,
    ):
        monitor._monitor_loop()
    return resolve, clear


def test_history_lag_then_play_again_still_resolves_in_lobby(monitor):
    monitor.has_analyzed_final_draft = True
    _tick(monitor, "EndOfGame", 1000.0)  # historique pas encore à jour

    resolve, clear = _tick(monitor, "Lobby", 1000.0 + INTERVAL, resolved=1)

    resolve.assert_called_once_with()
    clear.assert_not_called()  # la sortie de fin de partie reste à l'écran
    assert monitor.has_analyzed_final_draft is False  # le reset a bien eu lieu


def test_success_closes_the_window(monitor):
    _tick(monitor, "EndOfGame", 1000.0, resolved=1)

    resolve, _ = _tick(monitor, "Lobby", 1000.0 + INTERVAL)

    resolve.assert_not_called()


def test_window_expires(monitor):
    _tick(monitor, "EndOfGame", 1000.0)

    resolve, _ = _tick(monitor, "Lobby", 1000.0 + draft_config.OUTCOME_RETRY_WINDOW)

    resolve.assert_not_called()


def test_end_of_game_screen_labels_without_waiting_for_the_history(db):
    """L'historique a ~5 min de retard (mesuré le 2026-09-28) : l'écran de fin
    suffit à labelliser, sans l'historique ni le détail de la partie."""
    from types import SimpleNamespace

    from src.config_constants import analysis_config
    from src.draft.outcome_tracker import OutcomeTracker

    cursor = db.connection.cursor()
    cursor.execute(
        "INSERT INTO predictions (created_utc, ally_champions, enemy_champions, "
        "predicted_probability, model_version) VALUES (?, ?, ?, ?, ?)",
        (
            "2026-09-28 21:22:44",
            "412,57,236,2,4",
            "141,117,804,45,240",
            0.5,
            analysis_config.MODEL_VERSION,
        ),
    )
    db.connection.commit()
    lcu = Mock()
    lcu.get_recent_matches.return_value = []  # historique pas encore à jour
    lcu.get_end_of_game_match.return_value = (
        {
            "game_id": 7998195590,
            "game_creation_ms": 1790630634230,
            "queue_id": None,
            "win": True,
            "player_champion_id": 2,
            "team_id": 100,
        },
        {100: [2, 57, 4, 236, 412], 200: [240, 141, 45, 804, 117]},
    )
    monitor = SimpleNamespace(assistant=SimpleNamespace(db=db), lcu=lcu, verbose=False)

    assert OutcomeTracker(monitor).resolve_pending() == 1
    lcu.get_match_participants.assert_not_called()
    cursor.execute("SELECT outcome, game_id FROM predictions")
    assert cursor.fetchone() == (1, 7998195590)
