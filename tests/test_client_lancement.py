"""Lancement du client (SPEC-21 tâche 55) : `--client`, option 7 du menu, Live Coach en fil."""

import sys

import pytest

import lol_coach
from src.client import launch
from src.client.bus import EventBus
from src.config_client import client_config
from src.draft.commands import CommandListener
from src.user_prefs import UserPrefs


class FauxLCU:
    def __init__(self, *_, **__):
        self.credentials = None

    def find_lcu_credentials(self):
        return object()


class FauxMoniteur:
    """`DraftMonitor` réduit à ce que le fil du Live Coach appelle."""

    instances = []
    connexions = []  # une valeur de retour de `start_monitoring` par appel

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.lcu = FauxLCU()
        self.started = 0
        self.stopped = False
        FauxMoniteur.instances.append(self)

    def start_monitoring(self):
        self.started += 1
        return FauxMoniteur.connexions.pop(0) if FauxMoniteur.connexions else None

    def stop_monitoring(self):
        self.stopped = True


@pytest.fixture(autouse=True)
def _faux_moniteur(monkeypatch):
    FauxMoniteur.instances = []
    FauxMoniteur.connexions = []
    monkeypatch.setattr(launch, "DraftMonitor", FauxMoniteur)
    monkeypatch.setattr(client_config, "LIVE_COACH_RETRY_S", 0.01)
    monkeypatch.setattr(launch, "load_user_prefs", lambda: None)
    monkeypatch.setattr(launch, "_saved_pool", lambda name: name)


# ---------- Live Coach en fil ----------


bus = EventBus()


def lancer_le_fil():
    coach = launch.LiveCoachThread(bus)
    coach.start()
    coach._thread.join(5)
    assert not coach._thread.is_alive()
    return coach


def test_le_fil_reprend_les_preferences_sans_console(monkeypatch):
    prefs = UserPrefs(
        auto_hover=True, auto_accept_queue=True, auto_ban_hover=False, pool_name="Ma pool"
    )
    monkeypatch.setattr(launch, "load_user_prefs", lambda: prefs)
    lancer_le_fil()
    (monitor,) = FauxMoniteur.instances
    assert monitor.kwargs == {
        "verbose": False,
        "auto_select_pool": False,
        "auto_hover": True,
        "auto_accept_queue": True,
        "auto_ban_hover": False,
        "preselected_pool_name": "Ma pool",
        "console_input": False,
        "bus": bus,
    }
    assert monitor.started == 1


def test_sans_pool_memorisee_la_pool_par_defaut_sans_question(monkeypatch):
    monkeypatch.setattr(launch, "_saved_pool", lambda name: None)
    lancer_le_fil()
    kwargs = FauxMoniteur.instances[0].kwargs
    assert kwargs["auto_select_pool"] is True and kwargs["preselected_pool_name"] is None


def test_attend_le_client_lol_puis_demarre(capsys, monkeypatch):
    credentials = iter([None, None, object()])
    monkeypatch.setattr(FauxLCU, "find_lcu_credentials", lambda self: next(credentials))
    lancer_le_fil()
    assert FauxMoniteur.instances[0].started == 1
    assert capsys.readouterr().out.count("en attente du client") == 1  # annoncé une seule fois


def test_reessaie_quand_la_connexion_echoue():
    FauxMoniteur.connexions = [False, False, None]
    lancer_le_fil()
    assert FauxMoniteur.instances[0].started == 3


def test_une_exception_du_moniteur_s_annonce_sans_remonter(capsys, monkeypatch):
    def casse(**_):
        raise RuntimeError("base verrouillée")

    monkeypatch.setattr(launch, "DraftMonitor", casse)
    lancer_le_fil()
    assert "[ALERTE] Live Coach arrêté : base verrouillée" in capsys.readouterr().out


def test_stop_interrompt_l_attente_et_arrete_le_moniteur(monkeypatch):
    monkeypatch.setattr(client_config, "LIVE_COACH_RETRY_S", 30.0)
    monkeypatch.setattr(FauxLCU, "find_lcu_credentials", lambda self: None)
    coach = launch.LiveCoachThread(bus)
    coach.start()
    while not FauxMoniteur.instances:
        coach._thread.join(0.01)
    coach.stop()
    assert not coach._thread.is_alive()
    assert FauxMoniteur.instances[0].stopped


def test_pas_d_ecoute_de_la_console_quand_le_moniteur_n_en_veut_pas():
    moniteur = type("M", (), {"console_input": False, "_command_listener_thread": None})()
    CommandListener(moniteur).start()
    assert moniteur._command_listener_thread is None


# ---------- run_client ----------


class Journal:
    def __init__(self):
        self.events = []

    def __call__(self, name, result=None):
        def call(*args, **kwargs):
            self.events.append(name)
            return result

        return call


@pytest.fixture
def journal(monkeypatch):
    log = Journal()
    monkeypatch.setattr(launch, "check_dependencies", lambda: True)
    monkeypatch.setattr(launch, "check_database", lambda: True)
    monkeypatch.setattr(launch.server, "start", log("serveur", "http://127.0.0.1:1"))
    monkeypatch.setattr(launch.server, "stop", log("serveur arrêté"))
    monkeypatch.setattr(launch.window, "run", log("fenêtre", True))
    monkeypatch.setattr(launch, "LCUClient", FauxLCU)
    monkeypatch.setattr(launch.LiveCoachThread, "start", log("coach"))
    monkeypatch.setattr(launch.LiveCoachThread, "stop", log("coach arrêté"))
    monkeypatch.setattr(launch.LcuEvents, "start", log("événements"))
    monkeypatch.setattr(launch.LcuEvents, "stop", log("événements arrêtés"))
    return log


def test_run_client_demarre_tout_puis_arrete_tout(journal):
    assert launch.run_client() is True
    assert journal.events == [
        "serveur",
        "événements",
        "coach",
        "fenêtre",
        "coach arrêté",
        "événements arrêtés",
        "serveur arrêté",
    ]


def test_run_client_sans_serveur_n_ouvre_rien(journal, monkeypatch):
    monkeypatch.setattr(launch.server, "start", journal("serveur", None))
    assert launch.run_client() is False
    assert journal.events == ["serveur"]


def test_run_client_sans_base_ne_demarre_rien(journal, monkeypatch):
    monkeypatch.setattr(launch, "check_database", lambda: False)
    assert launch.run_client() is False
    assert journal.events == []


def test_run_client_arrete_tout_meme_si_la_fenetre_leve(journal, monkeypatch):
    def casse(url):
        raise RuntimeError("webview")

    monkeypatch.setattr(launch.window, "run", casse)
    with pytest.raises(RuntimeError):
        launch.run_client()
    assert journal.events[-3:] == ["coach arrêté", "événements arrêtés", "serveur arrêté"]


def test_run_client_reste_en_vie_quand_la_page_s_ouvre_dans_le_navigateur(journal, monkeypatch):
    monkeypatch.setattr(launch.window, "run", journal("fenêtre", False))
    monkeypatch.setattr(launch, "_wait_for_interrupt", journal("attente"))
    assert launch.run_client() is True
    assert "attente" in journal.events and journal.events[-1] == "serveur arrêté"


# ---------- lol_coach.py ----------


def appels_du_client(monkeypatch):
    appels = []
    monkeypatch.setattr(launch, "run_client", lambda verbose=False: appels.append(verbose))
    return appels


def test_option_client_lance_la_fenetre_sans_menu(monkeypatch):
    appels = appels_du_client(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["lol_coach.py", "--client", "-v"])
    monkeypatch.setattr("builtins.input", lambda *_: pytest.fail("le menu ne doit pas s'afficher"))
    lol_coach.main()
    assert appels == [True]


def test_menu_7_ouvre_le_client_et_8_quitte(monkeypatch):
    appels = appels_du_client(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["lol_coach.py", "--no-banner", "--no-clear"])
    choix = iter(["7", "8"])
    monkeypatch.setattr(lol_coach, "print_main_menu", lambda: next(choix))
    lol_coach.main()
    assert appels == [False]
