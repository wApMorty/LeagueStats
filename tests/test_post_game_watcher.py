"""SPEC-25 tâche 115 : `PostGameWatcher` lit l'écran de fin chaque seconde, le temps de la phase.

Faux suiveur de phase et faux client LCU : rien ne touche le vrai client ni une base.
"""

import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.config_constants import draft_config
from src.coaching.post_game_watcher import PostGameWatcher


class FakeTracker:
    def __init__(self):
        self.kind = "game"
        self.callbacks = []

    def subscribe(self, callback):
        self.callbacks.append(callback)

    def enter(self, kind):
        self.kind = kind
        for callback in self.callbacks:
            callback(None, "x", kind)


def wait_for(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(draft_config, "PHASE_POST_POLL_S", 0.01)
    tracker, capture, lcu = FakeTracker(), Mock(), Mock()
    watcher = PostGameWatcher(tracker, capture, make_lcu=lambda: lcu)
    return SimpleNamespace(tracker=tracker, capture=capture, lcu=lcu, watcher=watcher)


def test_lit_avec_son_propre_client_tant_que_la_phase_dure_puis_une_derniere_fois(setup):
    setup.watcher.start()
    setup.tracker.enter("post")
    assert wait_for(lambda: setup.capture.read_transients.call_count >= 3)
    setup.capture.read_transients.assert_called_with(setup.lcu)  # son client, pas celui du coach
    assert setup.lcu.credentials is setup.lcu.find_lcu_credentials.return_value

    setup.tracker.kind = "idle"  # « Rejouer »
    assert wait_for(lambda: not setup.watcher._thread.is_alive())
    reads = setup.capture.read_transients.call_count
    time.sleep(0.05)
    assert setup.capture.read_transients.call_count == reads


def test_une_seule_lecture_a_la_fois_pour_trois_phases_de_fin(setup):
    setup.watcher.start()
    for _ in range(3):  # WaitingForStats, PreEndOfGame, EndOfGame
        setup.tracker.enter("post")
    assert wait_for(lambda: setup.capture.read_transients.call_count >= 1)
    assert setup.lcu.find_lcu_credentials.call_count == 1
    setup.watcher.stop()


def test_ne_lit_rien_hors_fin_de_partie_ni_tant_qu_il_n_est_pas_arme(setup):
    setup.tracker.enter("post")  # pas armé : mode hors ligne, tests
    setup.watcher.start()
    setup.tracker.enter("draft")
    setup.tracker.enter("game")
    time.sleep(0.05)
    setup.capture.read_transients.assert_not_called()


def test_une_erreur_de_lecture_n_atteint_personne(setup):
    setup.capture.read_transients.side_effect = RuntimeError("boum")
    setup.watcher.start()
    setup.tracker.enter("post")  # ne lève pas
    assert wait_for(lambda: not setup.watcher._thread.is_alive())


def test_un_tracker_reste_bloque_sur_post_est_borne_par_la_fenetre(setup, monkeypatch):
    monkeypatch.setattr(draft_config, "POST_GAME_RETRY_WINDOW", 0.05)
    setup.watcher.start()
    setup.tracker.enter("post")  # le suiveur ne sortira jamais de `post`
    assert wait_for(lambda: not setup.watcher._thread.is_alive())


def test_les_identifiants_sont_cherches_avant_l_ecran_de_fin(setup):
    setup.watcher.start()  # client LoL ouvert
    setup.tracker.enter("game")  # une partie dure : le temps de les rafraîchir
    searches = setup.lcu.find_lcu_credentials.call_count
    setup.tracker.enter("post")
    assert wait_for(lambda: setup.capture.read_transients.call_count >= 1)
    assert setup.lcu.find_lcu_credentials.call_count == searches  # rien à chercher à l'écran de fin
    setup.watcher.stop()
