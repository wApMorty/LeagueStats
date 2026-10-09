"""Régression (2026-10-09, SPEC-28) : la draft suivante restait muette quand la boucle ne voyait ni
`Lobby` ni `Matchmaking` entre deux parties (boucle occupée par l'après-partie, « Rejouer » puis file).

Cause : `has_analyzed_final_draft`, `last_draft_state`, `has_done_initial_hover` et le sujet `game` ne
se remettaient à zéro que sur un tour observé en `Lobby`/`Matchmaking`. Sinon `EndOfGame` puis
`ChampSelect` laissait `has_analyzed_final_draft` vrai : ni console, ni recommandation, ni snapshot.

Points couverts :
1. `EndOfGame` puis `ChampSelect` sans phase intermédiaire vue : la draft est traitée, l'analyse de la
   partie précédente est retirée de l'écran « En partie » (sujet `game` à `None`).
2. Esquive : `ChampSelect` partiel, `Matchmaking`, `ChampSelect` sans que la boucle voie
   `Matchmaking` : la seconde draft a son survol initial et un état neuf.
3. Une même draft qui continue (`ChampSelect` répété) ne se réarme pas.
4. Un client muet (tracker sans phase) puis revenu en pleine draft ne refait pas le survol initial.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft.final_analysis import TOPIC as GAME_TOPIC
from src.draft_monitor import DraftMonitor, DraftState

SESSION = {"timer": {"phase": "BAN_PICK"}}


@pytest.fixture
def monitor():
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            m = DraftMonitor(auto_hover=False, auto_accept_queue=False)
    m.bus = Mock()
    m.lcu.get_champion_select_session.return_value = SESSION
    m._parse_draft_state = Mock(side_effect=lambda _session: DraftState(phase="BAN_PICK"))
    m.loadout = Mock()
    m.recommender = Mock()
    return m


def _tick(monitor, handle):
    with patch.object(monitor, "_handle_draft_change", handle):
        monitor._monitor_loop()


def test_draft_after_an_unseen_lobby_is_handled(monitor):
    monitor.phase_tracker.observe("EndOfGame")
    monitor.has_analyzed_final_draft = True  # la partie précédente a été analysée
    handle = Mock()

    monitor.phase_tracker.observe("ChampSelect")  # Lobby et Matchmaking jamais vus par la boucle
    _tick(monitor, handle)

    handle.assert_called_once()
    assert monitor.has_analyzed_final_draft is False
    monitor.bus.publish.assert_any_call(GAME_TOPIC, None)


def test_dodge_without_a_seen_matchmaking_rearms_the_initial_hover(monitor):
    monitor.phase_tracker.observe("ChampSelect")
    seen = []
    handle = Mock(side_effect=lambda state: seen.append(monitor.has_done_initial_hover))
    _tick(monitor, handle)
    monitor.has_done_initial_hover = True  # le survol de la première draft a eu lieu

    monitor.phase_tracker.observe("Matchmaking")
    monitor.phase_tracker.observe("ChampSelect")
    _tick(monitor, handle)

    assert handle.call_count == 2
    assert seen[-1] is False  # la seconde draft repart de zéro


def test_same_draft_is_not_rearmed(monitor):
    monitor.phase_tracker.observe("Matchmaking")
    monitor.phase_tracker.observe("ChampSelect")
    handle = Mock()
    _tick(monitor, handle)
    monitor.has_done_initial_hover = True

    monitor.phase_tracker.observe("ChampSelect")
    _tick(monitor, handle)

    assert monitor.has_done_initial_hover is True
    handle.assert_called_once()


def test_tracker_gap_in_the_middle_of_a_draft_does_not_rearm(monitor):
    monitor.phase_tracker.observe("Matchmaking")
    monitor.phase_tracker.observe("ChampSelect")
    _tick(monitor, Mock())
    monitor.has_done_initial_hover = True

    monitor.phase_tracker.observe(None)  # une phase connue n'est pas effacée avant PHASE_STALE_S
    monitor.phase_tracker.observe("ChampSelect")
    _tick(monitor, Mock())

    assert monitor.has_done_initial_hover is True


def test_delay_of_each_draft_is_journaled_once(monitor):
    lines = []
    monitor.tick_timer.sink = lines.append
    monitor.phase_tracker.observe("Matchmaking")
    monitor.phase_tracker.observe("ChampSelect")

    _tick(monitor, Mock())
    _tick(monitor, Mock())

    assert len(lines) == 1
    assert lines[0].startswith("draft vue ") and lines[0].endswith("l'entrée en champ select")
