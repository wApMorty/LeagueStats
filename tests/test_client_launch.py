"""Fermeture gardée de la fenêtre du client (SPEC-37 tâche 185).

Pas de vraie fenêtre, pas de serveur, pas de pipeline : un faux job et un `confirm` simulé, et pour
le câblage un faux module `webview`.
"""

import sys
import types

from src.client import window
from src.client.launch import close_guard
from src.config_client import client_config


class FauxJob:
    """`UpdateJob` réduit à `running` et `cancel`, qui enregistre ses appels."""

    def __init__(self, running: bool) -> None:
        self.running = running
        self.cancels = []

    def cancel(self, timeout: float) -> bool:
        self.cancels.append(timeout)
        return True


class FauxConfirm:
    """`confirm` qui répond `answer` et enregistre ses appels."""

    def __init__(self, answer: bool) -> None:
        self.answer = answer
        self.calls = []

    def __call__(self, title: str, message: str) -> bool:
        self.calls.append((title, message))
        return self.answer


def test_job_a_larret_ferme_sans_demander():
    job, confirm = FauxJob(running=False), FauxConfirm(answer=False)
    guard = close_guard(job, client_config.DONNEES_CLOSE_TIMEOUT_S)
    assert guard(confirm) is True
    assert confirm.calls == [] and job.cancels == []


def test_job_en_cours_refuse_la_fermeture_sans_arreter():
    job, confirm = FauxJob(running=True), FauxConfirm(answer=False)
    guard = close_guard(job, client_config.DONNEES_CLOSE_TIMEOUT_S)
    assert guard(confirm) is False
    assert len(confirm.calls) == 1 and job.cancels == []


def test_job_en_cours_confirme_arrete_avec_le_delai():
    job, confirm = FauxJob(running=True), FauxConfirm(answer=True)
    guard = close_guard(job, client_config.DONNEES_CLOSE_TIMEOUT_S)
    assert guard(confirm) is True
    assert job.cancels == [client_config.DONNEES_CLOSE_TIMEOUT_S]


def test_cablage_dans_la_fenetre_et_garde_en_echec(monkeypatch, capsys):
    """`window.run` branche la garde sur `events.closing` ; une garde en échec ferme (ALERTE)."""

    class Evenement:
        def __init__(self) -> None:
            self.handlers = []

        def __iadd__(self, handler):
            self.handlers.append(handler)
            return self

    class FauxFenetre:
        def __init__(self) -> None:
            self.events = types.SimpleNamespace(closing=Evenement())
            self.create_confirmation_dialog = FauxConfirm(answer=False)

    module = types.ModuleType("webview")
    module.fenetres = []

    def create_window(title, url, **kwargs):
        module.fenetres.append(FauxFenetre())
        return module.fenetres[-1]

    module.create_window = create_window
    module.start = lambda: None
    monkeypatch.setitem(sys.modules, "webview", module)

    recus = []

    def garde(confirm):
        recus.append(confirm)
        return confirm("titre", "message")

    assert window.run("http://127.0.0.1:1", garde) is True
    (handler,) = module.fenetres[0].events.closing.handlers
    assert handler() is False  # « non » du dialogue annule la fermeture
    assert recus == [module.fenetres[0].create_confirmation_dialog]
    assert module.fenetres[0].create_confirmation_dialog.calls == [("titre", "message")]
    assert capsys.readouterr().out == ""

    def garde_cassee(confirm):
        raise RuntimeError("dialogue indisponible")

    module.fenetres.clear()
    assert window.run("http://127.0.0.1:1", garde_cassee) is True
    (handler,) = module.fenetres[0].events.closing.handlers
    assert handler() is True  # best-effort : la fenêtre se ferme
    assert "[ALERTE]" in capsys.readouterr().out
