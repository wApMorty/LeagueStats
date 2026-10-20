"""Régression : lancé par `python lol_coach.py`, la barre des tâches montrait le logo Python.

Symptôme : la fenêtre du client avait l'icône LeagueStats (Alt+Tab), mais son bouton dans la barre
des tâches gardait le logo de `python.exe` (signalé par @pj35, 2026-10-20).
Cause racine : Windows regroupe les fenêtres par AppUserModelID ; sans identifiant propre, le
processus hérite de celui de `python.exe`, dont l'icône l'emporte sur celle de la fenêtre.
Correctif : `window._open` pose `client_config.APP_USER_MODEL_ID` avant de créer la fenêtre
(best-effort : un échec n'empêche pas l'ouverture).
Prévention : ce test vérifie que l'identifiant est posé avant `create_window`.
"""

import sys
import types

from src.client import window
from src.config_client import client_config


def test_identifiant_d_application_pose_avant_la_fenetre(monkeypatch):
    calls = []
    shell32 = types.SimpleNamespace(
        SetCurrentProcessExplicitAppUserModelID=lambda app_id: calls.append(("aumid", app_id))
    )
    monkeypatch.setattr(window.ctypes, "windll", types.SimpleNamespace(shell32=shell32), False)

    module = types.ModuleType("webview")
    module.windows = []
    module.create_window = (
        lambda *args, **kwargs: calls.append(("window",)) or types.SimpleNamespace()
    )
    module.start = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "webview", module)

    assert window.run("http://127.0.0.1:1") is True
    assert calls[:2] == [("aumid", client_config.APP_USER_MODEL_ID), ("window",)]
