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
