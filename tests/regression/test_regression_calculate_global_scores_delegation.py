"""Regression test for bug: AttributeError in calculate_global_scores().

Bug Report:
-----------
Date: 2026-08-25
Reporter: User (@pj35)
Symptom: [ERROR] Aatrox: 'Assistant' object has no attribute '_filter_valid_matchups'
Reproduced on every champion at the end of parsing (calculate_global_scores loop
catches and prints the exception per champion instead of raising, so scoring
silently fails for the whole roster).

Root Cause:
-----------
- Assistant.calculate_global_scores() (src/assistant.py) called
  self._filter_valid_matchups(matchups) and self.avg_delta2(matchups) directly
  on the Assistant instance.
- Both methods actually live on ChampionScorer (src/analysis/scoring.py), which
  Assistant already holds as self.scorer since the Sprint 1 modular refactor.
- The two direct calls were dead references left over from before the
  refactor (or dropped during the "Supprimer le code mort" cleanup) and were
  never updated to delegate through self.scorer.

Fix:
----
- self._filter_valid_matchups(matchups) -> self.scorer.filter_valid_matchups(matchups)
- self.avg_delta2(matchups) -> self.scorer.avg_delta2(matchups)

Prevention:
-----------
This test drives calculate_global_scores() with a mocked Database returning a
single champion with matchup data, and asserts the champion is actually scored
(no AttributeError swallowed by the per-champion try/except).
"""

from unittest.mock import Mock

from src.assistant import Assistant
from src.models import Matchup


def _make_matchup(
    enemy_name="Zed", winrate=52.0, delta1=10.0, delta2=15.0, pickrate=20.0, games=500
):
    return Matchup(enemy_name, winrate, delta1, delta2, pickrate, games)


def test_calculate_global_scores_does_not_raise_attribute_error():
    """calculate_global_scores() must score champions, not swallow AttributeError.

    Before fix: self._filter_valid_matchups / self.avg_delta2 did not exist on
    Assistant, so every champion raised AttributeError inside the per-champion
    try/except and calculate_global_scores() silently scored 0 champions.
    """
    mock_db = Mock()
    mock_db.connect.return_value = None
    mock_db.get_all_champion_names.return_value = {1: "Aatrox"}
    mock_db.get_champion_matchups_by_name.return_value = [_make_matchup()]
    mock_db.get_champion_id.return_value = 1
    mock_db.save_champion_scores.return_value = None

    assistant = Assistant(db=mock_db, verbose=False)

    champions_scored = assistant.calculate_global_scores()

    assert champions_scored == 1, (
        "calculate_global_scores() should score the champion; a regression to "
        "self._filter_valid_matchups()/self.avg_delta2() raises AttributeError "
        "which is caught per-champion and silently skips scoring."
    )
    mock_db.save_champion_scores.assert_called_once()


def test_assistant_delegates_filter_valid_matchups_and_avg_delta2_to_scorer():
    """Assistant must delegate to self.scorer, not call undefined methods on itself."""
    mock_db = Mock()
    mock_db.connect.return_value = None
    assistant = Assistant(db=mock_db, verbose=False)

    assert not hasattr(type(assistant), "_filter_valid_matchups"), (
        "Assistant must not redefine _filter_valid_matchups; it should delegate "
        "to self.scorer.filter_valid_matchups()"
    )
    assert not hasattr(type(assistant), "avg_delta2"), (
        "Assistant must not redefine avg_delta2; it should delegate to " "self.scorer.avg_delta2()"
    )

    matchups = [_make_matchup()]
    assert assistant.scorer.filter_valid_matchups(matchups) == matchups
    assert assistant.scorer.avg_delta2(matchups) > 0
