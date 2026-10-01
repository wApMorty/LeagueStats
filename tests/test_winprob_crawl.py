"""Tests de la collecte SPEC-20 phase 1 (src/winprob/crawl.py).

Hermétiques : LCU simulé, `crawl.db` et base de parties temporaires.
"""

import json
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from src.lcu_client import LCUClient, LCUCredentials
from src.winprob.crawl import Crawler, unpack

NOW_MS = int(time.time() * 1000)
HOUR = 3600 * 1000


def _game(game_id, puuids, version="16.19.1", created=NOW_MS, blue_win=True):
    return {
        "gameId": game_id,
        "gameCreation": created,
        "gameDuration": 1500,
        "gameVersion": version,
        "queueId": 420,
        "participants": [{"participantId": i + 1} for i in range(len(puuids))],
        "participantIdentities": [
            {"participantId": i + 1, "player": {"puuid": p, "gameName": "secret"}}
            for i, p in enumerate(puuids)
        ],
        "teams": [
            {"teamId": 100, "win": "Win" if blue_win else "Fail"},
            {"teamId": 200, "win": "Fail" if blue_win else "Win"},
        ],
    }


def _entry(game_id, created=NOW_MS, queue_id=420):
    return {"game_id": game_id, "game_creation_ms": created, "queue_id": queue_id}


class FakeLCU:
    """Historique par puuid, détails par partie ; `last_status_code` comme le vrai client."""

    def __init__(self):
        self.histories = {}
        self.games = {}
        self.status = 200
        self.requests = []

    def _answer(self, label, value):
        self.requests.append(label)
        return value if self.status == 200 else None

    def get_player_games(self, puuid):
        return self._answer(("history", puuid), self.histories.get(puuid))

    def get_game_detail(self, game_id):
        return self._answer(("detail", game_id), self.games.get(game_id))

    def get_game_timeline(self, game_id):
        return self._answer(("timeline", game_id), {"frames": [{"timestamp": 0}]})

    @property
    def last_status_code(self):
        return self.status


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
def crawler(db, lcu, clock, tmp_path):
    monitor = SimpleNamespace(lcu=lcu, assistant=SimpleNamespace(db=db), verbose=True)
    return Crawler(monitor, path=tmp_path / "crawl.db", clock=clock)


def _capture_own_game(db, game_id=1, puuids=("me", "a", "b")):
    game = _game(game_id, list(puuids))
    db.insert_game_record(
        game_id=game_id,
        queue_id=420,
        game_creation_utc="2026-10-01 20:00:00",
        duration_s=1500,
        player_participant_id=1,
        raw_game=json.dumps(game),
        raw_timeline=None,
        raw_eog=None,
    )


def _drain(crawler, clock, steps=50):
    for _ in range(steps):
        crawler.step()
        clock.t += 10


def _rows(crawler, sql):
    return crawler._db().execute(sql).fetchall()


class TestSeed:
    def test_players_of_my_games_enter_the_frontier_at_depth_1_and_I_do_not(self, crawler, db):
        _capture_own_game(db)
        crawler.seed()
        assert _rows(
            crawler, "SELECT puuid, depth, visited_utc IS NULL FROM crawl_frontier ORDER BY puuid"
        ) == [
            ("a", 1, 1),
            ("b", 1, 1),
            ("me", 0, 0),
        ]

    def test_a_visited_player_returns_to_the_queue_after_a_newer_game_of_mine(
        self, crawler, db, lcu, clock
    ):
        _capture_own_game(db, 1)
        crawler.seed()
        lcu.histories = {"a": [], "b": []}
        _drain(crawler, clock)
        assert _rows(crawler, "SELECT COUNT(*) FROM crawl_frontier WHERE visited_utc IS NULL") == [
            (0,)
        ]

        game = _game(2, ["me", "a", "c"], created=NOW_MS + HOUR)
        db.insert_game_record(
            game_id=2,
            queue_id=420,
            game_creation_utc="2026-10-01 23:00:00",
            duration_s=1500,
            player_participant_id=1,
            raw_game=json.dumps(game),
            raw_timeline=None,
            raw_eog=None,
        )
        crawler.seed()
        todo = {
            r[0]
            for r in _rows(crawler, "SELECT puuid FROM crawl_frontier WHERE visited_utc IS NULL")
        }
        assert todo == {"a", "c"}  # b n'était pas dans la nouvelle partie


class TestCrawl:
    def test_history_then_games_then_depth_2_players(self, crawler, db, lcu, clock):
        _capture_own_game(db)
        crawler.seed()
        lcu.histories = {"a": [_entry(10), _entry(11, queue_id=450)], "b": [], "x": [], "y": []}
        lcu.games = {10: _game(10, ["a", "x", "y"], blue_win=False)}
        _drain(crawler, clock)

        games = _rows(
            crawler,
            "SELECT game_id, game_version, blue_win, depth, length(raw) > 0 FROM crawl_games",
        )
        assert games == [(10, "16.19.1", 0, 1, 1)]  # la 450 est ignorée
        depths = dict(_rows(crawler, "SELECT puuid, depth FROM crawl_frontier"))
        assert depths == {"me": 0, "a": 1, "b": 1, "x": 2, "y": 2}
        assert ("history", "x") in lcu.requests  # les joueurs de profondeur 2 sont visités

    def test_depth_2_games_do_not_add_depth_3_players(self, crawler, db, lcu, clock):
        _capture_own_game(db)
        crawler.seed()
        lcu.histories = {"a": [_entry(10)], "b": [], "x": [_entry(20)], "y": []}
        lcu.games = {10: _game(10, ["a", "x", "y"]), 20: _game(20, ["x", "z"])}
        _drain(crawler, clock)
        assert "z" not in dict(_rows(crawler, "SELECT puuid, depth FROM crawl_frontier"))

    def test_raw_is_compressed_without_identities_except_puuid(self, crawler, db, lcu, clock):
        _capture_own_game(db)
        crawler.seed()
        lcu.histories = {"a": [_entry(10)], "b": []}
        lcu.games = {10: _game(10, ["a", "x"])}
        _drain(crawler, clock)
        (raw,) = _rows(crawler, "SELECT raw FROM crawl_games WHERE game_id = 10")[0]
        packed = unpack(raw)
        assert packed["game"]["participantIdentities"][0] == {
            "participantId": 1,
            "player": {"puuid": "a"},
        }
        assert "secret" not in json.dumps(packed)
        assert packed["timeline"] == {"frames": [{"timestamp": 0}]}

    def test_a_game_already_stored_is_not_read_twice(self, crawler, db, lcu, clock):
        _capture_own_game(db)
        crawler.seed()
        lcu.histories = {"a": [_entry(10)], "b": [_entry(10)]}
        lcu.games = {10: _game(10, ["a", "b"])}
        _drain(crawler, clock)
        assert lcu.requests.count(("detail", 10)) == 1

    def test_games_older_than_the_age_window_are_not_collected(self, crawler, db, lcu, clock):
        _capture_own_game(db)
        crawler.seed()
        old = NOW_MS - 365 * 24 * HOUR
        lcu.histories = {"a": [_entry(10, created=old)], "b": []}
        _drain(crawler, clock)
        assert _rows(crawler, "SELECT COUNT(*) FROM crawl_games") == [(0,)]

    def test_an_unavailable_game_is_marked_and_not_retried(self, crawler, db, lcu, clock):
        _capture_own_game(db)
        crawler.seed()
        lcu.histories = {"a": [_entry(10)], "b": []}
        lcu.games = {}  # détail 404
        _drain(crawler, clock)
        lcu.status = 200
        assert lcu.requests.count(("detail", 10)) == 1
        assert _rows(crawler, "SELECT length(raw) FROM crawl_games") == [(0,)]


class TestRateAndPause:
    def test_step_respects_the_request_interval(self, crawler, db, lcu, clock):
        _capture_own_game(db)
        crawler.seed()
        lcu.histories = {"a": [], "b": []}
        crawler.step()
        crawler.step()  # même instant : sans effet
        assert len(lcu.requests) == 1
        clock.t += 1.0
        crawler.step()
        assert len(lcu.requests) == 2

    def test_429_pauses_the_crawl_then_resumes_without_losing_the_player(
        self, crawler, db, lcu, clock, capsys
    ):
        _capture_own_game(db)
        crawler.seed()
        lcu.histories = {"a": [], "b": []}
        lcu.status = 429
        crawler.step()
        assert "429" in capsys.readouterr().out
        lcu.status = 200
        clock.t += 60
        crawler.step()
        assert len(lcu.requests) == 1  # toujours en pause
        clock.t += 900
        crawler.step()
        assert len(lcu.requests) == 2
        assert _rows(
            crawler, "SELECT COUNT(*) FROM crawl_frontier WHERE visited_utc IS NOT NULL"
        ) == [(2,)]

    def test_unreachable_client_changes_nothing(self, crawler, db, lcu, clock):
        _capture_own_game(db)
        crawler.seed()
        lcu.status = None  # pas de réponse HTTP
        _drain(crawler, clock, steps=5)
        assert _rows(crawler, "SELECT COUNT(*) FROM crawl_frontier WHERE visited_utc IS NULL") == [
            (2,)
        ]

    def test_an_error_never_propagates(self, crawler, lcu, clock):
        lcu.get_player_games = Mock(side_effect=RuntimeError("boom"))
        crawler._db().execute(
            "INSERT INTO crawl_frontier (puuid, depth, priority, discovered_utc) VALUES ('a', 1, 1, 'x')"
        )
        crawler.step()  # ne lève pas


class TestPurge:
    def test_only_the_latest_patches_are_kept(self, crawler, db):
        conn = crawler._db()
        for i, version in enumerate(["16.16.1", "16.17.1", "16.18.1", "16.19.1", "16.19.2"]):
            conn.execute(
                "INSERT INTO crawl_games (game_id, game_version, game_creation_utc, depth, raw) "
                "VALUES (?, ?, datetime('now'), 1, x'01')",
                (i, version),
            )
        crawler._purge()
        kept = {r[0] for r in _rows(crawler, "SELECT game_version FROM crawl_games")}
        assert kept == {"16.17.1", "16.18.1", "16.19.1", "16.19.2"}  # 3 patchs : 16.17 à 16.19


class TestLCUClientStatus:
    """Le client distingue un 429 d'un 404 (SPEC-20 §11.1)."""

    def _client(self):
        client = LCUClient()
        client.credentials = LCUCredentials(port=1, password="p", base_url="https://x")
        return client

    @pytest.mark.parametrize("status", [404, 429, 500])
    def test_status_code_is_exposed_on_failure(self, status):
        client = self._client()
        with patch.object(client.session, "get", return_value=Mock(status_code=status)):
            assert client._make_request("/x") is None
        assert client.last_status_code == status

    def test_status_code_is_none_without_a_response(self):
        import requests

        client = self._client()
        client.last_status_code = 429
        with patch.object(client.session, "get", side_effect=requests.ConnectionError):
            client._make_request("/x")
        assert client.last_status_code is None

    def test_get_player_games_reads_any_players_history(self):
        client = self._client()
        payload = {"games": {"games": [{"gameId": 5, "gameCreation": 7, "queueId": 420}, {"x": 1}]}}
        with patch.object(client, "_make_request", return_value=payload) as request:
            assert client.get_player_games("abc") == [_entry(5, created=7)]
        assert "/products/lol/abc/matches?begIndex=0&endIndex=19" in request.call_args[0][0]


class TestLifecycleWiring:
    """Une unité de collecte par tick, ni en draft ni pendant le ready check."""

    @pytest.fixture
    def monitor(self):
        from src.draft_monitor import DraftMonitor

        with patch("src.draft_monitor.Assistant", return_value=Mock()):
            with patch("src.draft_monitor.LCUClient", return_value=Mock()):
                monitor = DraftMonitor(verbose=False, auto_hover=False)
        monitor.crawler = Mock()
        monitor.lcu.is_in_ready_check.return_value = False
        return monitor

    @pytest.mark.parametrize(
        "phase, steps", [("Lobby", 1), ("InProgress", 1), ("ReadyCheck", 0), ("ChampSelect", 0)]
    )
    def test_step_runs_outside_draft_and_ready_check(self, monitor, phase, steps):
        monitor.lcu.get_gameflow_session.return_value = {"phase": phase}
        monitor.lcu.is_in_champion_select.return_value = phase == "ChampSelect"
        monitor.lcu.get_champion_select_session.return_value = None
        monitor._monitor_loop()
        assert monitor.crawler.step.call_count == steps

    def test_post_game_pass_reseeds_the_queue(self, monitor):
        monitor._post_game_until = time.time() + 60
        monitor._next_post_game_attempt = 0.0
        monitor.game_capture = Mock()
        monitor._resolve_pending_outcomes = Mock()
        monitor.lifecycle.retry_post_game()
        monitor.crawler.seed.assert_called_once_with()


class TestProgress:
    def test_progress_line_counts_games_and_players(self, crawler, db, lcu, clock, capsys):
        _capture_own_game(db)
        crawler.seed()
        lcu.histories = {"a": [_entry(10), _entry(11)], "b": []}
        lcu.games = {10: _game(10, ["a", "x"])}  # 11 : détail indisponible
        _drain(crawler, clock, steps=4)  # a, b, 10, 11 : x (profondeur 2) reste en attente
        crawler.report()
        assert (
            "[DATA] Collecte : 1 parties lues (+1 en 24 h), 0 à lire, 1 joueurs en attente"
            in capsys.readouterr().out
        )

    def test_report_prints_once_when_the_post_game_window_opens(self):
        from src.draft_monitor import DraftMonitor

        with patch("src.draft_monitor.Assistant", return_value=Mock()):
            with patch("src.draft_monitor.LCUClient", return_value=Mock()):
                monitor = DraftMonitor(verbose=False, auto_hover=False)
        monitor.crawler = Mock()
        monitor.lcu.is_in_ready_check.return_value = False
        monitor.lcu.is_in_champion_select.return_value = False
        monitor.lcu.get_gameflow_session.return_value = {"phase": "EndOfGame"}
        for _ in range(3):  # trois ticks dans la même phase de fin de partie
            monitor._monitor_loop()
        monitor.crawler.report.assert_called_once_with()


class TestSchemaMigration:
    def test_a_crawl_db_created_before_read_utc_keeps_working(self, db, lcu, clock, tmp_path):
        import sqlite3

        path = tmp_path / "crawl.db"
        old = sqlite3.connect(path)
        old.executescript(
            "CREATE TABLE crawl_games (game_id INTEGER PRIMARY KEY, queue_id INTEGER, "
            "game_version TEXT, game_creation_utc TEXT NOT NULL, duration_s INTEGER, "
            "blue_win INTEGER, depth INTEGER NOT NULL, raw BLOB);"
            "INSERT INTO crawl_games (game_id, game_creation_utc, depth, raw) "
            "VALUES (1, '2026-10-01 20:00:00', 1, x'01'), (2, '2026-10-01 20:00:00', 1, NULL);"
        )
        old.commit()
        old.close()
        monitor = SimpleNamespace(lcu=lcu, assistant=SimpleNamespace(db=db), verbose=True)
        crawler = Crawler(monitor, path=path, clock=clock)
        lcu.games = {2: _game(2, ["a"])}
        crawler.step()
        assert "2 parties lues (+2 en 24 h), 0 à lire" in crawler.progress()
