"""Tests de la capture SPEC-19 phase 1 (src/coaching/capture.py, ranked.py).

Hermétiques : LCU simulé, réponses tirées des fixtures anonymisées du spike du
2026-09-28 (tests/fixtures/spike_gameplay/), base temporaire.
"""

import json
import sqlite3
import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.coaching import ranked
from src.coaching.capture import GameCapture

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME_ID = 7998195590


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


GAME = _fixture(f"{GAME_ID}_game.json")
TIMELINE = _fixture(f"{GAME_ID}_timeline.json")


def _match(game_id=GAME_ID, queue_id=420, creation_ms=None):
    return {
        "game_id": game_id,
        "game_creation_ms": GAME["gameCreation"] if creation_ms is None else creation_ms,
        "queue_id": queue_id,
        "win": True,
        "player_champion_id": 2,
        "team_id": 100,
        "participant_id": 1,
    }


@pytest.fixture
def lcu():
    lcu = Mock()
    lcu.get_recent_matches.return_value = [_match(), _match(game_id=1, queue_id=450)]
    lcu.get_game_detail.return_value = GAME
    lcu.get_game_timeline.return_value = TIMELINE
    lcu.get_end_of_game_block.return_value = None
    return lcu


def _capture(db, lcu):
    return GameCapture(SimpleNamespace(lcu=lcu, assistant=SimpleNamespace(db=db), verbose=False))


def _rows(db, sql):
    cursor = db.connection.cursor()
    cursor.execute(sql)
    return cursor.fetchall()


class TestCaptureRecent:
    def test_ranked_game_is_stored_raw_and_other_queues_ignored(self, db, lcu, capsys):
        assert _capture(db, lcu).capture_recent() == 1

        rows = _rows(
            db,
            "SELECT game_id, queue_id, duration_s, player_participant_id, "
            "raw_game, raw_timeline, raw_eog FROM game_records",
        )
        assert len(rows) == 1
        game_id, queue_id, duration_s, participant_id, raw_game, raw_timeline, raw_eog = rows[0]
        assert (game_id, queue_id, duration_s, participant_id) == (GAME_ID, 420, 1488, 1)
        assert json.loads(raw_game) == GAME
        assert json.loads(raw_timeline) == TIMELINE
        assert raw_eog is None
        assert "1 partie(s) capturée(s)" in capsys.readouterr().out

    def test_second_pass_captures_nothing_and_fetches_nothing(self, db, lcu):
        capture = _capture(db, lcu)
        capture.capture_recent()
        lcu.get_game_detail.reset_mock()

        assert capture.capture_recent() == 0
        lcu.get_game_detail.assert_not_called()

    def test_end_of_game_screen_is_kept_without_its_secrets(self, db, lcu):
        block = _fixture("eog_stats_block.json")
        block["mucJwtDto"] = {"jwt": "secret"}
        block["multiUserChatPassword"] = "secret"
        lcu.get_end_of_game_block.return_value = block
        capture = _capture(db, lcu)

        capture.remember_end_of_game()
        lcu.get_end_of_game_block.return_value = None  # disparu à la draft suivante
        capture.capture_recent()

        raw_eog = json.loads(_rows(db, "SELECT raw_eog FROM game_records")[0][0])
        assert "mucJwtDto" not in raw_eog and "multiUserChatPassword" not in raw_eog
        assert raw_eog["teams"][0]["players"][0]["detectedTeamPosition"] == "TOP"

    def test_unranked_end_of_game_screen_is_not_kept(self, db, lcu):
        lcu.get_end_of_game_block.return_value = {"gameId": GAME_ID, "queueType": "ARAM"}
        capture = _capture(db, lcu)

        capture.remember_end_of_game()

        assert capture._eog_by_game == {}

    def test_missing_timeline_of_a_fresh_game_waits_for_the_next_pass(self, db, lcu):
        now_ms = int(time.time() * 1000)
        lcu.get_recent_matches.return_value = [_match(creation_ms=now_ms - 1_800_000)]
        lcu.get_game_timeline.return_value = None

        assert _capture(db, lcu).capture_recent() == 0

    def test_missing_timeline_of_an_old_game_is_stored_as_null(self, db, lcu):
        lcu.get_recent_matches.return_value = [
            _match(creation_ms=GAME["gameCreation"] - 86_400_000)
        ]
        lcu.get_game_timeline.return_value = None

        assert _capture(db, lcu).capture_recent() == 1
        assert _rows(db, "SELECT raw_timeline FROM game_records") == [(None,)]


class TestBestEffort:
    def test_unmigrated_database_warns_once_and_never_raises(self, lcu, capsys):
        db = Mock()
        db.get_captured_game_ids.side_effect = sqlite3.OperationalError(
            "no such table: game_records"
        )
        db.insert_rank_snapshot.side_effect = sqlite3.OperationalError(
            "no such table: rank_snapshots"
        )
        lcu.get_ranked_stats.return_value = _fixture("current-ranked-stats.json")
        lcu.get_lp_change_notification.return_value = {}
        capture = _capture(db, lcu)

        capture.on_startup()
        capture.on_post_game()

        assert capsys.readouterr().out.count("alembic upgrade head") == 1

    def test_lcu_failure_never_raises(self, db, lcu):
        lcu.get_recent_matches.side_effect = RuntimeError("client fermé")
        lcu.get_ranked_stats.side_effect = RuntimeError("client fermé")

        _capture(db, lcu).on_startup()  # ne lève pas


class TestRankSnapshots:
    def test_startup_snapshot_covers_ranked_queues_only(self, db, lcu):
        lcu.get_ranked_stats.return_value = _fixture("current-ranked-stats.json")

        assert ranked.snapshot_current(lcu, db) == 2
        assert _rows(
            db, "SELECT queue, tier, division, lp, lp_delta, game_id FROM rank_snapshots"
        ) == [
            ("RANKED_SOLO_5x5", "DIAMOND", "II", 38, None, None),
            ("RANKED_FLEX_SR", "EMERALD", "I", 75, None, None),
        ]

    def test_after_game_snapshot_carries_the_lp_delta_once(self, db, lcu, capsys):
        note = _fixture("current-lp-change-notification.json")

        assert ranked.snapshot_after_game(note, db) is True
        assert ranked.snapshot_after_game(note, db) is False
        assert _rows(db, "SELECT queue, lp, lp_delta, game_id FROM rank_snapshots") == [
            ("RANKED_SOLO_5x5", 38, 19, GAME_ID)
        ]
        assert "+19 LP" in capsys.readouterr().out

    @pytest.mark.parametrize(
        "note",
        [{}, None, {"gameId": 1, "queueType": "ARAM"}, {"queueType": "RANKED_SOLO_5x5"}],
    )
    def test_no_valid_notification_outside_the_post_game(self, note):
        assert ranked.valid_notification(note) is None


class TestTransientsOffLoop:
    """SPEC-25 tâche 115 : la lecture se sépare de l'écriture en base."""

    def test_notification_is_set_aside_then_written_without_the_lcu(self, db, lcu):
        lcu.get_lp_change_notification.return_value = _fixture(
            "current-lp-change-notification.json"
        )
        capture = _capture(db, lcu)

        capture.read_transients()  # fil de PostGameWatcher : aucune base
        assert _rows(db, "SELECT COUNT(*) FROM rank_snapshots") == [(0,)]
        lcu.get_lp_change_notification.return_value = {}  # l'écran de fin est quitté
        capture.on_post_game()  # fil du coach : écrit ce qui a été mis de côté

        assert _rows(db, "SELECT lp_delta, game_id FROM rank_snapshots") == [(19, GAME_ID)]
        assert capture._lp_by_game == {}

    def test_read_transients_uses_the_given_client(self, db, lcu):
        other = Mock()
        other.get_end_of_game_block.return_value = _fixture("eog_stats_block.json")
        other.get_lp_change_notification.return_value = _fixture(
            "current-lp-change-notification.json"
        )
        capture = _capture(db, lcu)

        capture.read_transients(other)

        lcu.get_lp_change_notification.assert_not_called()
        assert set(capture._lp_by_game) == {GAME_ID} and set(capture._eog_by_game) == {GAME_ID}

    def test_locked_database_replays_the_notification_on_the_next_pass(self, db, lcu, capsys):
        note = _fixture("current-lp-change-notification.json")
        lcu.get_lp_change_notification.return_value = note
        capture = _capture(db, lcu)
        real_insert = db.insert_rank_snapshot
        db.insert_rank_snapshot = Mock(side_effect=sqlite3.OperationalError("database is locked"))

        capture.on_post_game()
        assert GAME_ID in capture._lp_by_game  # gardée en mémoire
        assert "[ALERTE] Capture de partie : OperationalError: database is locked" in (
            capsys.readouterr().out
        )

        db.insert_rank_snapshot = real_insert
        lcu.get_lp_change_notification.return_value = {}
        capture.on_post_game()
        assert _rows(db, "SELECT lp_delta, game_id FROM rank_snapshots") == [(19, GAME_ID)]

    def test_two_threads_on_the_dictionaries(self, db, lcu):
        capture = _capture(db, lcu)
        errors = []

        def reader():
            try:
                for game_id in range(1, 400):
                    capture.read_transients(
                        Mock(
                            get_end_of_game_block=Mock(
                                return_value={"gameId": game_id, "queueType": "RANKED_SOLO_5x5"}
                            ),
                            get_lp_change_notification=Mock(
                                return_value={
                                    "gameId": game_id,
                                    "queueType": "RANKED_SOLO_5x5",
                                    "tier": "GOLD",
                                }
                            ),
                        )
                    )
            except Exception as exc:  # pragma: no cover - ne doit pas arriver
                errors.append(exc)

        thread = threading.Thread(target=reader)
        thread.start()
        while thread.is_alive():
            capture.write_lp_snapshots()
            lcu.get_recent_matches.return_value = []
            capture.capture_recent()
        capture.write_lp_snapshots()
        assert errors == []
        assert _rows(db, "SELECT COUNT(*) FROM rank_snapshots") == [(399,)]

    def test_each_distinct_error_is_shown_once_without_verbose(self, db, lcu, capsys):
        lcu.get_recent_matches.side_effect = RuntimeError("client fermé")
        capture = _capture(db, lcu)

        capture.on_post_game()
        capture.on_post_game()
        lcu.get_recent_matches.side_effect = ValueError("autre")
        capture.on_post_game()

        out = capsys.readouterr().out
        assert out.count("[ALERTE] Capture de partie : RuntimeError: client fermé") == 1
        assert out.count("[ALERTE] Capture de partie : ValueError: autre") == 1


class TestLpFromWebSocketEvent:
    """SPEC-25 tâche 117 : l'événement `/lol-ranked` porte la notification de LP (relevé du 2026-10-07)."""

    NOTE = json.loads(
        (
            Path(__file__).parent / "fixtures" / "lcu_endgame" / "lp_change_notification.json"
        ).read_text(encoding="utf-8")
    )
    EVENT = {"uri": ranked.LP_NOTIFICATION_URI, "eventType": "Update", "data": NOTE}

    def test_event_gives_the_same_snapshot_as_the_poll(self, db, lcu):
        lcu.get_lp_change_notification.return_value = self.NOTE
        polled, evented = _capture(db, lcu), _capture(db, lcu)

        polled.read_transients()
        evented.on_lcu_event(self.EVENT)

        assert evented._lp_by_game == polled._lp_by_game == {self.NOTE["gameId"]: self.NOTE}
        evented.write_lp_snapshots()
        assert _rows(
            db, "SELECT queue, tier, division, lp, lp_delta, game_id FROM rank_snapshots"
        ) == [("RANKED_SOLO_5x5", "DIAMOND", "II", 64, -20, 8006463758)]
        assert polled.write_lp_snapshots() is None  # même partie : une seule photo
        assert _rows(db, "SELECT COUNT(*) FROM rank_snapshots") == [(1,)]

    def test_screen_left_before_any_read_still_gives_the_lp(self, db, lcu):
        capture = _capture(db, lcu)  # le fil de lecture n'a rien vu : fenêtre plus courte que 1 s
        capture.on_lcu_event(self.EVENT)
        lcu.get_lp_change_notification.return_value = {}

        capture.on_post_game()

        assert _rows(db, "SELECT lp_delta, game_id FROM rank_snapshots") == [(-20, 8006463758)]

    @pytest.mark.parametrize(
        "event",
        [
            {"uri": ranked.LP_NOTIFICATION_URI, "eventType": "Update", "data": None},
            {"uri": ranked.LP_NOTIFICATION_URI, "eventType": "Delete", "data": {}},
            {"uri": "/lol-ranked/v1/ranked-stats/anon", "data": {"gameId": 1}},
            {"uri": ranked.LP_NOTIFICATION_URI, "data": {"gameId": 1, "queueType": "ARAM"}},
            {"uri": "/lol-chat/v1/me", "data": {}},
        ],
    )
    def test_other_events_are_ignored(self, db, lcu, event):
        capture = _capture(db, lcu)
        capture.on_lcu_event(event)
        assert capture._lp_by_game == {}
