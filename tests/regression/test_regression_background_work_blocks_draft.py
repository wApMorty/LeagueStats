"""Régression (2026-10-09, SPEC-28) : le travail d'après-partie retardait la lecture de la draft.

Cause : hors champ select, chaque tour de la boucle monofil enchaîne résolution des résultats, capture,
analyse et collecte, soit des requêtes LCU de 5 s au timeout, sans jamais regarder si la draft a
commencé. Un tour commencé en `Matchmaking` finissait des dizaines de secondes plus tard.

Points couverts :
1. Dès que le tracker passe en `draft` pendant un passage de `retry_post_game`, aucune requête LCU de la
   boucle n'est émise (au plus celle déjà en vol) : les suivantes rendent `None` tout de suite.
2. Le tour suivant lit la session de champ select (ces requêtes-là ne cèdent jamais).
3. `yield_if` est remis à `None` après le passage, même s'il lève.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor, DraftState
from src.lcu_client import LCUClient, LCUCredentials


class FakeLcu(LCUClient):
    """Vrai `LCUClient` (donc vrai `_make_request`) sur une session qui compte les requêtes."""

    def __init__(self, on_request):
        super().__init__()
        self.credentials = LCUCredentials(1, "x", "https://127.0.0.1:1")
        self.requests = []
        self._on_request = on_request
        self.session = Mock()
        self.session.get.side_effect = self._get

    def _get(self, url, **_kwargs):
        self.requests.append(url)
        self._on_request(len(self.requests))
        response = Mock(status_code=200, content=b"{}")
        response.json.return_value = {"phase": "ChampSelect"}
        return response


@pytest.fixture
def monitor():
    holder = {}
    lcu = FakeLcu(
        lambda n: holder["monitor"].phase_tracker.observe("ChampSelect") if n == 1 else None
    )
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=lcu):
            m = DraftMonitor(auto_hover=False, auto_accept_queue=False)
    holder["monitor"] = m
    m._parse_draft_state = Mock(return_value=DraftState(phase="BAN_PICK"))
    m.loadout, m.recommender, m.crawler = Mock(), Mock(), Mock()
    m.phase_tracker.observe("Matchmaking")
    m._post_game_until, m._next_post_game_attempt = float("inf"), 0.0
    return m


def _background_requests(monitor, count):
    """Un passage d'après-partie : `count` requêtes LCU à la suite."""

    def work():
        for _ in range(count):
            monitor.lcu.get_recent_matches()

    return work


def test_no_request_after_the_draft_starts_during_a_post_game_pass(monitor):
    monitor.lcu.get_recent_matches = lambda: monitor.lcu._make_request("/history")
    with patch.object(monitor, "_resolve_pending_outcomes", _background_requests(monitor, 6)):
        monitor._monitor_loop()

    assert len(monitor.lcu.requests) == 1  # la requête en vol, aucune ensuite
    assert monitor.lcu.yield_if is None


def test_next_tick_reads_the_draft(monitor):
    monitor.lcu.get_recent_matches = lambda: monitor.lcu._make_request("/history")
    with patch.object(monitor, "_resolve_pending_outcomes", _background_requests(monitor, 3)):
        monitor._monitor_loop()
    handle = Mock()

    with patch.object(monitor, "_handle_draft_change", handle):
        monitor._monitor_loop()

    handle.assert_called_once()
    assert monitor.lcu.requests[-1].endswith("/lol-champ-select/v1/session")


def test_yield_if_is_cleared_when_the_pass_raises(monitor):
    with patch.object(monitor, "_resolve_pending_outcomes", side_effect=RuntimeError("x")):
        monitor._monitor_loop()

    assert monitor.lcu.yield_if is None
