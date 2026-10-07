"""Régression SPEC-25 : les LP et l'écran de fin n'étaient plus capturés depuis le 2026-10-05.

Symptôme : `rank_snapshots` sans `lp_delta` ni `game_id`, `game_records` sans `raw_eog`, pour toutes
les parties classées depuis le 2026-10-05 17:42 UTC (11 parties) ; le reste de la capture marchait.

Cause racine : `eog-stats-block` et `current-lp-change-notification` ne répondent que pendant
l'écran de fin (relevé du 2026-10-07 : de `PreEndOfGame` à la sortie d'`EndOfGame`, puis `null`) et
n'étaient lus que par la boucle du monitor, une fois par `POST_GAME_RETRY_INTERVAL`. La boucle
mettant 2 à 5 s par tour, un écran quitté par « Rejouer » passait entre deux lectures.

Correctif : `PostGameWatcher` lit les deux endpoints chaque seconde, avec son propre client LCU,
dès l'entrée en fin de partie du `PhaseTracker`, et les met de côté en mémoire ; la boucle du
monitor écrit ensuite en base ce qui a été mis de côté.

Prévention : ce test sert l'écran de fin pendant la fenêtre seulement, quand la boucle (qui n'a pas
tourné) ne lit rien, puis fait passer la boucle une fois la fenêtre fermée.
"""

import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.draft_monitor import DraftMonitor
from src.lcu_client import LCUClient

FIXTURES = Path(__file__).parent.parent / "fixtures" / "spike_gameplay"
GAME_ID = 7998195590


def _fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def wait_for(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_les_lp_et_l_ecran_de_fin_sont_captures_quand_la_boucle_arrive_trop_tard(db):
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            monitor = DraftMonitor(verbose=False)
    monitor.assistant = SimpleNamespace(db=db)
    capture = monitor.game_capture
    capture.analyze = capture.impact = lambda live: None  # hors sujet ici
    lcu = monitor.lcu  # celui de la boucle : l'écran de fin est déjà quitté quand elle passe
    lcu.get_recent_matches.return_value = []
    lcu.get_game_detail.return_value = _fixture(f"{GAME_ID}_game.json")
    lcu.get_game_timeline.return_value = _fixture(f"{GAME_ID}_timeline.json")
    lcu.get_end_of_game_block.return_value = None
    lcu.get_lp_change_notification.return_value = {}

    window = {"open": True}  # l'écran de fin : servi pendant la fenêtre seulement
    block, note = _fixture("eog_stats_block.json"), _fixture("current-lp-change-notification.json")
    with (
        patch.object(LCUClient, "find_lcu_credentials", return_value=object()),
        patch.object(
            LCUClient,
            "get_end_of_game_block",
            side_effect=lambda: block if window["open"] else None,
        ),
        patch.object(
            LCUClient,
            "get_lp_change_notification",
            side_effect=lambda: note if window["open"] else {},
        ),
    ):
        monitor.post_game_watcher.start()
        monitor.phase_tracker.observe("PreEndOfGame")  # événement du client LoL
        # la boucle, elle, met 5 s à passer : le fil a lu l'écran de fin et la notification
        wait_for(lambda: capture._eog_by_game and capture._lp_by_game)
        window["open"] = False  # « Rejouer » : l'écran de fin disparaît
        monitor.phase_tracker.observe("None")
        capture.on_post_game()  # un tour de boucle de plus de 3 s après la fin de la fenêtre
    monitor.post_game_watcher.stop()

    cursor = db.connection.cursor()
    cursor.execute("SELECT lp_delta, game_id FROM rank_snapshots")
    assert cursor.fetchall() == [(19, GAME_ID)]
    cursor.execute("SELECT raw_eog IS NOT NULL FROM game_records")
    assert cursor.fetchall() == [(1,)]
