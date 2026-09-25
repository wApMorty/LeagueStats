"""Régression 2026-09-25 : « UNIQUE constraint failed: predictions.game_id »
répété après chaque partie.

Une même draft enregistrée deux fois (prédictions #85 et #86, 25 s d'écart)
laissait le doublon en attente. Sa seule partie candidate était déjà prise
par l'autre prédiction : à chaque passage d'OutcomeTracker (trois phases de
fin de partie), il la retentait et heurtait l'index unique sur game_id.
"""

from tests.test_outcome_tracker import (
    FULL_MATCH_PARTICIPANTS,
    _fake_monitor,
    _insert_prediction,
    _match,
    _outcome_and_game_id,
)
from src.draft.outcome_tracker import OutcomeTracker


def test_duplicate_of_a_labelled_prediction_never_retries_its_game(db, capsys):
    duplicate_id = _insert_prediction(db)
    labelled_id = _insert_prediction(db)
    db.update_prediction_outcome(labelled_id, 1, game_id=7994346984)
    monitor = _fake_monitor(db)
    monitor.lcu.get_recent_matches.return_value = [_match(7994346984)]
    monitor.lcu.get_match_participants.return_value = FULL_MATCH_PARTICIPANTS

    resolved = OutcomeTracker(monitor).resolve_pending()

    assert resolved == 0
    assert _outcome_and_game_id(db, duplicate_id) == (None, None)
    assert "UNIQUE constraint failed" not in capsys.readouterr().out
    monitor.lcu.get_match_participants.assert_not_called()
