"""Tests for OutcomeTracker.resolve_pending (SPEC-08 §2.4).

Hermetic: LCUClient is mocked (get_recent_matches / get_match_participants),
the database is the real Database over the temp_db fixture (never
data/db.db). No real LCU client is contacted, per docs/specs/README.md and
SPEC-08 §5 -- the payload shapes these mocks return were verified against a
real client on 2026-09-05 and must not be re-derived from speculation.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.draft.outcome_tracker import OutcomeTracker

ALLY = [1, 2, 3, 4, 5]
ENEMY = [6, 7, 8, 9, 10]
PRED_CREATED_DT = datetime(2026, 9, 5, 10, 0, 0, tzinfo=timezone.utc)
PRED_CREATED = "2026-09-05 10:00:00"


def _fake_monitor(db):
    return SimpleNamespace(assistant=SimpleNamespace(db=db), lcu=Mock(), verbose=False)


def _insert_prediction(db, ally=ALLY, enemy=ENEMY, created_utc=PRED_CREATED, probability=0.5):
    cursor = db.connection.cursor()
    cursor.execute(
        "INSERT INTO predictions "
        "(created_utc, ally_champions, enemy_champions, predicted_probability, model_version) "
        "VALUES (?, ?, ?, ?, 'b7-v1')",
        (created_utc, ",".join(map(str, ally)), ",".join(map(str, enemy)), probability),
    )
    db.connection.commit()
    return cursor.lastrowid


def _outcome_and_game_id(db, prediction_id):
    cursor = db.connection.cursor()
    cursor.execute("SELECT outcome, game_id FROM predictions WHERE id = ?", (prediction_id,))
    return cursor.fetchone()


def _ms_after(minutes: float, base: datetime = PRED_CREATED_DT) -> int:
    return int((base + timedelta(minutes=minutes)).timestamp() * 1000)


def _match(game_id, minutes_after=30, win=True, team_id=100, base=PRED_CREATED_DT):
    return {
        "game_id": game_id,
        "game_creation_ms": _ms_after(minutes_after, base),
        "queue_id": 420,
        "win": win,
        "player_champion_id": 1,
        "team_id": team_id,
    }


FULL_MATCH_PARTICIPANTS = {100: list(ALLY), 200: list(ENEMY)}


class TestNominalMatch:
    def test_single_prediction_single_match_is_labelled(self, db, capsys):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(7412339812, win=True)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 1
        assert _outcome_and_game_id(db, prediction_id) == (1, 7412339812)
        out = capsys.readouterr().out
        assert "[OUTCOME] Partie 7412339812 -> victoire" in out
        assert f"prédiction #{prediction_id}" in out
        assert "50,0 %" in out

    def test_defeat_is_labelled_as_zero(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1, win=False)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 1
        assert _outcome_and_game_id(db, prediction_id) == (0, 1)


class TestTemporalFilter:
    def test_match_before_prediction_is_rejected(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1, minutes_after=-10)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        assert _outcome_and_game_id(db, prediction_id) == (None, None)
        monitor.lcu.get_match_participants.assert_not_called()

    def test_match_outside_six_hour_window_is_rejected(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1, minutes_after=7 * 60)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        assert _outcome_and_game_id(db, prediction_id) == (None, None)


class TestCompositionConfirmation:
    def test_three_of_five_allies_common_is_rejected(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = {
            100: [1, 2, 3, 98, 99],  # only 3 of ALLY in common
            200: list(ENEMY),
        }

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        assert _outcome_and_game_id(db, prediction_id) == (None, None)

    def test_four_of_five_allies_common_is_accepted(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = {
            100: [1, 2, 3, 4, 99],  # 4 of ALLY in common
            200: list(ENEMY),
        }

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 1
        assert _outcome_and_game_id(db, prediction_id)[1] == 1

    def test_matching_allies_but_mismatched_enemies_is_rejected(self, db):
        """Passe 2 checks both sides -- a full ally match alone is not enough."""
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = {
            100: list(ALLY),
            200: [6, 7, 97, 98, 99],  # only 2 of ENEMY in common
        }

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        assert _outcome_and_game_id(db, prediction_id) == (None, None)

    def test_missing_participant_detail_is_an_abstention(self, db):
        """get_match_participants returning {} must not label at a guess."""
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = {}

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        assert _outcome_and_game_id(db, prediction_id) == (None, None)


class TestAmbiguity:
    def test_two_candidate_matches_the_nearest_in_time_wins(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        far_match = _match(1, minutes_after=200)
        near_match = _match(2, minutes_after=15)
        monitor.lcu.get_recent_matches.return_value = [far_match, near_match]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 1
        assert _outcome_and_game_id(db, prediction_id)[1] == 2  # the near one

    def test_one_match_two_predictions_only_the_nearer_prediction_wins(self, db):
        far_prediction_id = _insert_prediction(db, created_utc="2026-09-05 08:00:00")
        near_prediction_id = _insert_prediction(db, created_utc="2026-09-05 10:00:00")
        monitor = _fake_monitor(db)
        # Created at 10:00, so this game (10:30) is 30 min after the near
        # prediction but 2h30 after the far one -- near wins either way.
        monitor.lcu.get_recent_matches.return_value = [_match(1, minutes_after=30)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 1
        assert _outcome_and_game_id(db, near_prediction_id)[1] == 1
        assert _outcome_and_game_id(db, far_prediction_id) == (None, None)


class TestIdempotence:
    def test_second_pass_resolves_nothing_more(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        first = OutcomeTracker(monitor).resolve_pending()
        second = OutcomeTracker(monitor).resolve_pending()

        assert first == 1
        assert second == 0
        assert _outcome_and_game_id(db, prediction_id)[1] == 1


class TestLcuUnavailable:
    def test_no_recent_matches_returns_zero_without_raising(self, db):
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = []

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        monitor.lcu.get_match_participants.assert_not_called()

    def test_no_pending_predictions_never_calls_the_lcu(self, db):
        monitor = _fake_monitor(db)

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        monitor.lcu.get_recent_matches.assert_not_called()

    def test_unexpected_exception_is_swallowed(self, db):
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.side_effect = Exception("LCU disconnected mid-call")

        resolved = OutcomeTracker(monitor).resolve_pending()  # must not raise

        assert resolved == 0


class TestParticipantsCallEconomy:
    def test_get_match_participants_only_called_for_temporally_retained_games(self, db):
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [
            _match(1, minutes_after=-5),  # before the prediction: rejected pass 1
            _match(2, minutes_after=30),  # within window: the only candidate
            _match(3, minutes_after=10 * 60),  # outside the 6h window: rejected pass 1
        ]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 1
        monitor.lcu.get_match_participants.assert_called_once_with(2)


class TestMalformedInputsAreAbstentions:
    """Defensive guards on data the spike says never happens in practice --
    still covered because 'best-effort, never raises' is a product
    invariant (SPEC-08 preamble), not just a happy-path promise."""

    def test_unparseable_created_utc_skips_that_prediction_only(self, db):
        cursor = db.connection.cursor()
        cursor.execute(
            "INSERT INTO predictions "
            "(created_utc, ally_champions, enemy_champions, predicted_probability, model_version) "
            "VALUES ('not-a-date', '1,2,3,4,5', '6,7,8,9,10', 0.5, 'b7-v1')"
        )
        db.connection.commit()
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()  # must not raise

        assert resolved == 0

    def test_match_missing_creation_timestamp_is_skipped(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        broken_match = _match(1)
        del broken_match["game_creation_ms"]
        monitor.lcu.get_recent_matches.return_value = [broken_match]

        resolved = OutcomeTracker(monitor).resolve_pending()  # must not raise

        assert resolved == 0
        assert _outcome_and_game_id(db, prediction_id) == (None, None)

    def test_participants_with_a_single_team_is_an_abstention(self, db):
        prediction_id = _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = {100: list(ALLY)}  # no team 200

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0
        assert _outcome_and_game_id(db, prediction_id) == (None, None)

    def test_db_update_failure_is_not_counted_and_does_not_raise(self, db):
        _insert_prediction(db)
        monitor = _fake_monitor(db)
        monitor.assistant.db = Mock(wraps=db)
        monitor.assistant.db.update_prediction_outcome.return_value = False
        monitor.lcu.get_recent_matches.return_value = [_match(1)]
        monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

        resolved = OutcomeTracker(monitor).resolve_pending()

        assert resolved == 0


class TestBackfillLimit:
    def test_bare_call_uses_the_configured_backfill_limit(self, db, monkeypatch):
        from src.config_constants import draft_config

        monkeypatch.setattr(draft_config, "OUTCOME_BACKFILL_LIMIT", 7)
        monitor = _fake_monitor(db)
        monitor.assistant.db = Mock(wraps=db)
        monitor.lcu.get_recent_matches.return_value = []

        OutcomeTracker(monitor).resolve_pending()  # no explicit limit

        monitor.assistant.db.get_pending_predictions.assert_called_once_with(7)

    def test_explicit_limit_overrides_config(self, db, monkeypatch):
        from src.config_constants import draft_config

        monkeypatch.setattr(draft_config, "OUTCOME_BACKFILL_LIMIT", 20)
        monitor = _fake_monitor(db)
        monitor.assistant.db = Mock(wraps=db)
        monitor.lcu.get_recent_matches.return_value = []

        OutcomeTracker(monitor).resolve_pending(limit=3)

        monitor.assistant.db.get_pending_predictions.assert_called_once_with(3)
