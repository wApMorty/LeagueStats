"""Régression (2026-10-11) : la collecte SPEC-20 tournait dans la boucle monofil du Live Coach. Une
requête LCU lente (3 à 17 s la timeline d'un inconnu, `py-spy` : `get_game_timeline`) ou une purge de
`crawl.db` retardait la lecture de la file trouvée et de la draft, qui restait invisible dans la GUI.

La boucle ne doit plus jamais exécuter `crawler.step` : la collecte a son fil (`Crawler.start`).
"""

from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor


@pytest.mark.parametrize("phase", ["Lobby", "Matchmaking", "InProgress", "EndOfGame"])
def test_the_loop_does_not_run_the_collection(phase):
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            monitor = DraftMonitor(verbose=False, auto_hover=False)
    monitor.crawler = Mock()
    monitor.lcu.get_gameflow_session.return_value = {"phase": phase}

    monitor._monitor_loop()

    monitor.crawler.step.assert_not_called()
