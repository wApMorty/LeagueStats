"""Régression (2026-10-09, SPEC-28) : une timeline abandonnée parce que la draft commençait
(`LCUClient.yield_if` rend `None`, `last_status_code` reste `None`) était rangée comme « absente » pour
toujours, la partie étant alors considérée comme lue.

Points couverts :
1. Capture : la partie n'est pas insérée sans timeline, elle l'est au passage suivant, timeline comprise.
2. Collecte : la partie n'est pas marquée lue sans timeline, elle l'est au passage suivant.
3. Une timeline vraiment absente (404 : `last_status_code` posé) reste rangée sans timeline.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.coaching.capture import GameCapture
from src.winprob.crawl import Crawler
from tests.test_coaching_capture import GAME, TIMELINE, _match, _rows
from tests.test_winprob_crawl import Clock, FakeLCU, _capture_own_game, _drain, _game, _entry


def _capture(db, lcu):
    return GameCapture(SimpleNamespace(lcu=lcu, assistant=SimpleNamespace(db=db), verbose=False))


def _capture_lcu(timeline, status):
    lcu = Mock()
    lcu.get_recent_matches.return_value = [_match()]
    lcu.get_game_detail.return_value = GAME
    lcu.get_game_timeline.return_value = timeline
    lcu.get_end_of_game_block.return_value = None
    lcu.last_status_code = status
    return lcu


def test_capture_retries_a_timeline_abandoned_for_the_draft(db):
    lcu = _capture_lcu(None, None)  # requête abandonnée : pas de réponse
    capture = _capture(db, lcu)

    assert capture.capture_recent() == 0
    assert _rows(db, "SELECT COUNT(*) FROM game_records") == [(0,)]

    lcu.get_game_timeline.return_value, lcu.last_status_code = TIMELINE, 200
    assert capture.capture_recent() == 1
    assert json.loads(_rows(db, "SELECT raw_timeline FROM game_records")[0][0]) == TIMELINE


def test_capture_still_stores_a_timeline_the_client_does_not_have(db):
    capture = _capture(db, _capture_lcu(None, 404))

    assert capture.capture_recent() == 1


class _YieldingLCU(FakeLCU):
    """La première lecture de timeline est abandonnée, comme par `yield_if`."""

    def __init__(self):
        super().__init__()
        self.yielding = True
        self._silent = False

    def get_game_timeline(self, game_id):
        if self.yielding:
            self._silent = True
            return None
        self._silent = False
        return super().get_game_timeline(game_id)

    @property
    def last_status_code(self):
        return None if self._silent else self.status


def test_crawl_retries_a_timeline_abandoned_for_the_draft(db, tmp_path):
    lcu, clock = _YieldingLCU(), Clock()
    crawler = Crawler(
        SimpleNamespace(lcu=lcu, assistant=SimpleNamespace(db=db), verbose=True),
        path=tmp_path / "crawl.db",
        clock=clock,
    )
    _capture_own_game(db)
    crawler.seed()
    lcu.histories = {"a": [_entry(10)], "b": []}
    lcu.games = {10: _game(10, ["a", "x"])}
    unread = "SELECT COUNT(*) FROM crawl_games WHERE game_id = 10 AND read_utc IS NULL"

    _drain(crawler, clock)
    assert crawler._db().execute(unread).fetchone() == (1,)

    lcu.yielding = False
    _drain(crawler, clock)
    assert crawler._db().execute(unread).fetchone() == (0,)
