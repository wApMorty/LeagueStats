"""Tests de l'éclaireur des joueurs en partie (SPEC-33 §4.8, src/winprob/scout.py).

Hermétiques : LCU simulé, exécuteur synchrone (sauf le test de garde), `crawl.db` temporaire, partie de
la fixture `spike_gameplay/7998195590` et modèle à poids fixes.
"""

import json
import sqlite3
import threading
import time
from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.config_winprob import winprob_config as cfg
from src.winprob.crawl import Crawler, unpack
from src.winprob.model import INPUTS, WinModel
from src.winprob.scout import Scout

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))
PUUIDS = [i["player"]["puuid"] for i in GAME["participantIdentities"]]


def _model():
    """Modèle jouet (copie locale de tests/test_winprob_impact.py::_model)."""
    d = 2 * len(INPUTS)
    weights = [0.0] * (d + 1)
    weights[INPUTS.index("kills")] = 0.5
    weights[INPUTS.index("towers")] = 0.5
    return WinModel(INPUTS, [0.0] * d, [1.0] * d, weights)


def _entry(game_id, created, queue=420):
    """Une entrée brute d'historique LCU (un seul participant : le joueur)."""
    return {
        "gameId": game_id,
        "gameCreation": created,
        "gameDuration": 1800,
        "queueId": queue,
        "participants": [
            {
                "championId": 103,
                "stats": {
                    "win": True,
                    "kills": 3,
                    "deaths": 1,
                    "assists": 4,
                    "totalMinionsKilled": 150,
                    "neutralMinionsKilled": 10,
                },
            }
        ],
    }


def _history(*game_ids):
    """Historique brut, le plus récent d'abord."""
    return {"games": {"games": [_entry(g, 10_000 - i) for i, g in enumerate(game_ids)]}}


class FakeLCU:
    """Historiques bruts par puuid, la partie de la fixture pour tout `game_id` ; statut par requête."""

    def __init__(self):
        self.histories = {}
        self.status = {}  # (type, clé) -> statut forcé ; 200 sinon
        self.raises = set()
        self.requests = []
        self._local = threading.local()

    def _answer(self, label, value):
        self.requests.append(label)
        if label in self.raises:
            raise RuntimeError("boom")
        self._local.code = self.status.get(label, self.status.get(label[0], 200))
        return value if self._local.code == 200 else None

    def get_player_history(self, puuid):
        return self._answer(("history", puuid), self.histories.get(puuid))

    def get_game_detail(self, game_id):
        return self._answer(("detail", game_id), {**GAME, "gameId": game_id})

    def get_game_timeline(self, game_id):
        return self._answer(("timeline", game_id), TIMELINE)

    @property
    def last_status_code(self):
        return getattr(self._local, "code", None)


class SyncExecutor:
    """Exécute chaque tâche à la soumission ; la récolte a lieu au `step()` suivant."""

    def submit(self, fn, *args):
        future = Future()
        try:
            future.set_result(fn(*args))
        except Exception as error:  # pylint: disable=broad-exception-caught
            future.set_exception(error)
        return future

    def shutdown(self, wait=True, cancel_futures=False):
        pass


class PendingExecutor:
    """Garde toutes les tâches en vol."""

    def __init__(self):
        self.submitted = []

    def submit(self, fn, *args):
        self.submitted.append(args)
        return Future()

    def shutdown(self, wait=True, cancel_futures=False):
        pass


class Bus:
    def __init__(self):
        self.published = []

    def publish(self, topic, payload):
        self.published.append((topic, payload))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def lcu():
    return FakeLCU()


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def monitor():
    return SimpleNamespace(
        lcu=SimpleNamespace(credentials=None),
        bus=Bus(),
        phase_tracker=SimpleNamespace(kind="idle", phase="InProgress"),
    )


@pytest.fixture
def crawler(monitor, clock, tmp_path):
    return Crawler(monitor, path=tmp_path / "crawl.db", clock=clock)


def _scout(monitor, crawler, lcu, clock, executor=None, fetch=lambda: None):
    scout = Scout(monitor, crawler, executor=executor or SyncExecutor(), clock=clock, fetch=fetch)
    scout.lcu = lcu
    monitor.scout = scout
    return scout


def _players(puuids):
    return [{"puuid": p, "champion_id": 103, "team": 100} for p in puuids]


def _drain(scout, clock, steps=30):
    for _ in range(steps):
        scout.step()
        clock.t += cfg.SCOUT_TICK_S


@pytest.fixture(autouse=True)
def model():
    with patch("src.winprob.scout.load_model", return_value=_model()):
        yield


def test_games_go_by_rank_after_all_histories(monitor, crawler, lcu, clock):
    players = PUUIDS[:3]
    lcu.histories = {
        p: _history(*(100 * i + r for r in range(3))) for i, p in enumerate(players, 1)
    }
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(players))
    _drain(scout, clock)

    kinds = [kind for kind, _ in lcu.requests]
    assert kinds[:3] == ["history"] * 3  # aucune partie avant les trois historiques
    details = [key for kind, key in lcu.requests if kind == "detail"]
    assert details == [100, 200, 300, 101, 201, 301, 102, 202, 302]
    window = scout.snapshot()[players[0]]["windows"][5]
    assert window["n"] == 3 and window["impact_n"] == 3
    assert not scout.active


def test_a_game_shared_by_two_players_is_read_once(monitor, crawler, lcu, clock):
    lcu.histories = {PUUIDS[0]: _history(7), PUUIDS[1]: _history(7)}
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(PUUIDS[:2]))
    _drain(scout, clock)
    assert lcu.requests.count(("detail", 7)) == 1
    assert all(scout.snapshot()[p]["windows"][5]["impact_n"] == 1 for p in PUUIDS[:2])


def test_a_game_already_in_crawl_db_costs_no_request(monitor, crawler, lcu, clock):
    from src.winprob.crawl import store_game

    store_game(crawler._db(), {**GAME, "gameId": 55}, TIMELINE, 1)
    crawler._db().commit()
    lcu.histories = {PUUIDS[0]: _history(55)}
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(PUUIDS[:1]))
    _drain(scout, clock)
    assert [kind for kind, _ in lcu.requests] == ["history"]
    assert scout.snapshot()[PUUIDS[0]]["windows"][10]["impact"] is not None
    assert scout.stats()["cache_hits"] == 1


def test_read_games_are_stored_like_the_crawler_and_players_marked_visited(
    monitor, crawler, lcu, clock
):
    lcu.histories = {p: _history(9) for p in PUUIDS}
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(PUUIDS))
    _drain(scout, clock)

    db = crawler._db()
    depth, read_utc, raw = db.execute(
        "SELECT depth, read_utc, raw FROM crawl_games WHERE game_id = 9"
    ).fetchone()
    assert depth == 1 and read_utc
    packed = unpack(raw)
    assert packed["game"]["gameId"] == 9
    assert packed["timeline"] == TIMELINE
    assert "gameName" not in json.dumps(packed["game"]["participantIdentities"])
    visited = db.execute(
        "SELECT COUNT(*) FROM crawl_frontier WHERE visited_utc IS NOT NULL"
    ).fetchone()[0]
    assert visited == 10


def test_429_stops_submissions_keeps_forms_and_pauses_the_crawl(
    monitor, crawler, lcu, clock, capsys
):
    games = list(range(1, cfg.SCOUT_WORKERS + 5))  # plus de parties que de workers
    lcu.histories = {PUUIDS[0]: _history(*games)}
    lcu.status = {"detail": 429}
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(PUUIDS[:1]))
    _drain(scout, clock)

    details = [key for kind, key in lcu.requests if kind == "detail"]
    assert details == games[: cfg.SCOUT_WORKERS]  # celles en vol, plus aucune soumission ensuite
    assert scout.snapshot()[PUUIDS[0]]["windows"][10]["n"] == 10  # la forme brute reste
    assert crawler._next_at > clock.t + cfg.CRAWL_BACKOFF_S - 10  # la collecte attend
    out = capsys.readouterr().out
    assert out.count("[ALERTE]") == 1 and "10 impacts en — s" in out
    assert not scout.active


def test_a_worker_exception_never_leaves_step(monitor, crawler, lcu, clock):
    lcu.histories = {PUUIDS[0]: _history(1, 2), PUUIDS[1]: _history(3)}
    lcu.raises = {("history", PUUIDS[1]), ("detail", 1)}
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(PUUIDS[:2]))
    _drain(scout, clock)  # ne lève pas

    snapshot = scout.snapshot()
    assert snapshot[PUUIDS[1]]["failed"] is True
    assert snapshot[PUUIDS[0]]["failed"] is False
    assert snapshot[PUUIDS[0]]["windows"][5]["impact_n"] == 1  # la 2 malgré l'échec de la 1
    assert not scout.active


def test_no_sqlite_access_outside_the_coordinator_thread(monitor, crawler, lcu):
    """Garde (SPEC-33 test 7) : un vrai pool, et chaque accès SQLite noté avec son fil."""
    lcu.histories = {p: _history(1, 2) for p in PUUIDS[:4]}
    threads, real_connect = [], sqlite3.connect

    def guarded(*args, **kwargs):
        threads.append(threading.current_thread().name)
        return real_connect(*args, **kwargs)

    with patch("src.winprob.crawl.sqlite3.connect", side_effect=guarded):
        crawler._db().set_trace_callback(lambda _: threads.append(threading.current_thread().name))
        scout = Scout(monitor, crawler, fetch=lambda: None)
        scout.lcu = lcu
        scout.start(_players(PUUIDS[:4]))
        deadline = time.monotonic() + 10
        while scout.active and time.monotonic() < deadline:
            scout.step()
            time.sleep(0.01)
    assert not scout.active
    assert threads and set(threads) == {threading.current_thread().name}


def test_the_crawl_is_paused_while_the_scout_is_active(monitor, crawler, lcu, clock):
    lcu.histories = {PUUIDS[0]: _history(1)}
    scout = _scout(monitor, crawler, lcu, clock)
    assert not crawler._paused()
    scout.start(_players(PUUIDS[:1]))
    assert crawler._paused()
    _drain(scout, clock)
    assert not scout.active and not crawler._paused()

    scout.start(_players(PUUIDS[1:2]))
    assert crawler._paused()
    scout.stop()
    assert not crawler._paused()


def test_in_game_no_more_than_the_in_game_workers_are_in_flight(monitor, crawler, lcu, clock):
    executor = PendingExecutor()
    scout = _scout(
        monitor, crawler, lcu, clock, executor, fetch=lambda: {"gameData": {"gameTime": 3.0}}
    )
    scout.start(_players(PUUIDS))
    _drain(scout, clock, steps=5)
    assert len(executor.submitted) == cfg.SCOUT_IN_GAME_WORKERS
    assert scout.stats()["loading_s"] == 0.0


def test_loading_screen_uses_all_workers(monitor, crawler, lcu, clock):
    executor = PendingExecutor()
    scout = _scout(monitor, crawler, lcu, clock, executor)
    scout.start(_players(PUUIDS))
    _drain(scout, clock, steps=5)
    assert len(executor.submitted) == cfg.SCOUT_WORKERS


def test_players_is_published_only_when_something_changed(monitor, crawler, lcu, clock):
    lcu.histories = {PUUIDS[0]: _history(1)}
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(PUUIDS[:1]))
    scout.step()  # soumissions seules : rien de neuf
    assert monitor.bus.published == []
    scout.step()  # l'historique revient
    assert monitor.bus.published[-1][0] == "players"
    assert monitor.bus.published[-1][1][PUUIDS[0]]["ready"] is True
    _drain(scout, clock)
    count = len(monitor.bus.published)
    _drain(scout, clock, steps=3)  # fini : plus rien
    assert len(monitor.bus.published) == count


def test_start_twice_for_the_same_players_does_nothing(monitor, crawler, lcu, clock):
    lcu.histories = {PUUIDS[0]: _history(1)}
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(PUUIDS[:1]))
    _drain(scout, clock)
    scout.start(_players(PUUIDS[:1]))
    _drain(scout, clock)
    assert lcu.requests.count(("history", PUUIDS[0])) == 1


def test_the_data_line_is_printed_once_at_the_end(monitor, crawler, lcu, clock, capsys):
    lcu.histories = {PUUIDS[0]: _history(1)}
    scout = _scout(monitor, crawler, lcu, clock)
    scout.start(_players(PUUIDS[:1]))
    _drain(scout, clock)
    scout.stop()
    out = capsys.readouterr().out
    assert out.count("[DATA] Éclaireur : formes en") == 1
    assert "3 requêtes, 0 % du cache" in out  # historique, puis détail et timeline


class TestLifecycle:
    """Test 11 : lancé une fois par partie en `InProgress`, jamais en draft, arrêté au reset."""

    @pytest.fixture
    def live_monitor(self):
        from unittest.mock import Mock

        from src.draft_monitor import DraftMonitor

        with patch("src.draft_monitor.Assistant", return_value=Mock()):
            with patch("src.draft_monitor.LCUClient", return_value=Mock()):
                monitor = DraftMonitor(verbose=False, auto_hover=False)
        monitor.scout = Mock(armed=False)
        monitor.reality = Mock()
        monitor.bus = Mock()
        monitor.lcu.is_in_ready_check.return_value = False
        return monitor

    @staticmethod
    def _session(missing=0):
        teams = {
            key: [{"puuid": f"{side}{i}", "championId": i} for i in range(5)]
            for key, side in (("teamOne", "a"), ("teamTwo", "b"))
        }
        for player in teams["teamTwo"][:missing]:
            player["puuid"] = ""
        return {"phase": "InProgress", "gameData": teams}

    def _tick(self, monitor, phase):
        monitor.phase_tracker = SimpleNamespace(
            phase=phase, kind="draft" if phase == "ChampSelect" else "game", draft_episode=0
        )
        monitor._draft_episode = 0
        monitor.lifecycle.monitor_loop()

    def test_in_progress_starts_the_scout_with_the_ten_players(self, live_monitor):
        live_monitor.lcu.get_gameflow_session.return_value = self._session()
        self._tick(live_monitor, "InProgress")
        (players,), _ = live_monitor.scout.start.call_args
        assert len(players) == 10
        assert players[0] == {"puuid": "a0", "champion_id": 0, "team": 100}
        assert players[-1] == {"puuid": "b4", "champion_id": 4, "team": 200}

    def test_once_armed_the_session_is_not_read_again(self, live_monitor):
        live_monitor.scout.armed = True
        self._tick(live_monitor, "InProgress")
        live_monitor.lcu.get_gameflow_session.assert_not_called()
        live_monitor.scout.start.assert_not_called()

    def test_an_incomplete_session_is_retried_without_error(self, live_monitor, capsys):
        live_monitor.lcu.get_gameflow_session.return_value = self._session(missing=1)
        self._tick(live_monitor, "InProgress")
        live_monitor.lcu.get_gameflow_session.return_value = None
        self._tick(live_monitor, "InProgress")
        live_monitor.scout.start.assert_not_called()
        assert capsys.readouterr().out.count("[INFO] Éclaireur : gameData") == 1

    def test_never_started_during_the_draft(self, live_monitor):
        live_monitor.lcu.get_gameflow_session.return_value = self._session()
        live_monitor.lcu.get_champion_select_session.return_value = None
        self._tick(live_monitor, "ChampSelect")
        live_monitor.scout.start.assert_not_called()

    def test_reset_stops_the_scout_and_clears_players(self, live_monitor):
        live_monitor.lifecycle.reset_for_next_game()
        live_monitor.scout.stop.assert_called_once_with()
        live_monitor.bus.publish.assert_any_call("players", None)
