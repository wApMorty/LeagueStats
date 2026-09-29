"""Régression : le rapport du coach de gameplay arrivait pendant, voire après,
la partie suivante (remonté par @pj35 le 2026-09-30).

La capture attendait que la partie apparaisse dans la liste de l'historique
(~5 min de retard), alors que `games/{id}` et la timeline la servent dès
l'écran de fin : quand la fenêtre d'après-partie se fermait avant, la capture
et son rapport glissaient à la fenêtre de la partie suivante.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.coaching.capture import GameCapture

FIXTURES = Path(__file__).parent.parent / "fixtures" / "spike_gameplay"


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_end_of_game_screen_game_is_captured_before_the_history_lists_it(db):
    game = _fixture("7998195590_game.json")
    lcu = Mock()
    lcu.get_recent_matches.return_value = []  # la liste n'a pas encore la partie
    lcu.get_game_detail.return_value = game
    lcu.get_game_timeline.return_value = _fixture("7998195590_timeline.json")
    lcu.get_end_of_game_block.return_value = _fixture("eog_stats_block.json")
    capture = GameCapture(SimpleNamespace(lcu=lcu, assistant=SimpleNamespace(db=db), verbose=False))

    capture.remember_end_of_game()

    assert capture.capture_recent() == 1
    cursor = db.connection.cursor()
    cursor.execute("SELECT game_id, queue_id, player_participant_id, raw_eog FROM game_records")
    game_id, queue_id, participant_id, raw_eog = cursor.fetchone()
    assert (game_id, queue_id, participant_id) == (game["gameId"], 420, 1)
    assert raw_eog is not None
