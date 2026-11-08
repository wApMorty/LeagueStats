"""Régression client : déplacée à la souris, la fenêtre ne revient pas à sa tuile sous Komorebi.

Symptôme (@pj35, 2026-11-08) : le client tuilé par Komorebi reste là où on le lâche, puis saute à sa
tuile au clic suivant.

Cause racine : le glisser de pywebview (`pywebview-drag-region`) déplace la fenêtre par une suite de
`move()` depuis le JS. Windows n'ouvre pas sa boucle de déplacement : aucun `MoveResizeStart/End`,
que Komorebi attend pour replacer ou échanger la fenêtre.

Correctif : un appui sur la barre de titre appelle `WindowApi.drag`, qui lance la boucle native
(`WM_NCLBUTTONDOWN` + `HTCAPTION`) sur le fil de la fenêtre.

Prévention : la barre n'est plus une zone de glisser pywebview, `shell.js` appelle `drag()` et
`drag()` envoie le bon message sur le fil UI.
"""

import ctypes
import sys
import types
from pathlib import Path

from src.client import window

CLIENT_DIR = Path(__file__).resolve().parents[2] / "src" / "client"


def test_la_barre_de_titre_n_est_plus_un_glisser_pywebview():
    base = (CLIENT_DIR / "templates" / "base.html").read_text(encoding="utf-8")
    assert 'id="titlebar-drag"' in base
    assert "pywebview-drag-region" not in base
    assert "api.drag()" in (CLIENT_DIR / "static" / "shell.js").read_text(encoding="utf-8")


def test_drag_lance_la_boucle_native_sur_le_fil_de_la_fenetre(monkeypatch):
    calls = []

    class Hwnd:
        def ToInt32(self):
            return 4242

    class Form:
        Handle = Hwnd()

        def Invoke(self, fn):
            calls.append("invoke")
            fn()

    class Generic:
        def __getitem__(self, _):
            return lambda fn: fn

    monkeypatch.setitem(sys.modules, "System", types.SimpleNamespace(Func=Generic(), Type=object))
    user32 = types.SimpleNamespace(
        ReleaseCapture=lambda: calls.append("release"),
        SendMessageW=lambda *args: calls.append(("send", *args)),
    )
    monkeypatch.setattr(ctypes, "windll", types.SimpleNamespace(user32=user32), raising=False)
    api = window.WindowApi()
    api._window = types.SimpleNamespace(native=Form())
    api.drag()
    assert calls == ["invoke", "release", ("send", 4242, 0xA1, 2, 0)]
