"""Tests de la capture SPEC-19 phase 1 (src/coaching/capture.py, ranked.py).

Hermétiques : LCU simulé, réponses tirées des fixtures anonymisées du spike du
2026-09-28 (tests/fixtures/spike_gameplay/), base temporaire.
"""

import json
import sqlite3
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
        lcu.get_lp_change_notification.return_value = _fixture(
            "current-lp-change-notification.json"
        )

        assert ranked.snapshot_after_game(lcu, db) is True
        assert ranked.snapshot_after_game(lcu, db) is False
        assert _rows(db, "SELECT queue, lp, lp_delta, game_id FROM rank_snapshots") == [
            ("RANKED_SOLO_5x5", 38, 19, GAME_ID)
        ]
        assert "+19 LP" in capsys.readouterr().out

    def test_no_notification_outside_the_post_game(self, db, lcu):
        lcu.get_lp_change_notification.return_value = {}

        assert ranked.snapshot_after_game(lcu, db) is False
        assert _rows(db, "SELECT COUNT(*) FROM rank_snapshots") == [(0,)]
