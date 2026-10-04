"""Fenêtre `pywebview` sans bordure du client (SPEC-21 §2, §4.2, §8).

Barre de titre, boutons et poignées sont dessinés en HTML (`static/shell.js`) ; ce module en
fournit les gestes. Deux écarts relevés par le spike (§8) y sont traités : « Agrandir » remplit la
zone utile de l'écran (`maximize()` recouvrirait la barre des tâches) et le redimensionnement par
les bords gauche et haut passe par `resize(fix_point=...)`, un seul `SetWindowPos` : pas de saut.
"""

import ctypes
import sys
import webbrowser
from ctypes import wintypes
from typing import Optional, Tuple

from ..config_client import client_config

Rect = Tuple[int, int, int, int]  # x, y, largeur, hauteur

_MONITOR_DEFAULTTONEAREST = 2
_BASE_DPI = 96


def scaled(rect: Rect, scale: float) -> Rect:
    """Rectangle en pixels physiques → logiques (ceux de `resize()` et `move()`)."""
    return tuple(round(value / scale) for value in rect)  # type: ignore[return-value]


def _screen_state(title: str) -> Optional[Tuple[Rect, Rect, float]]:
    """(fenêtre, zone utile de son écran, échelle DPI), en pixels physiques ; None hors Windows."""
    if sys.platform != "win32":
        return None
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.GetDpiForWindow.restype = wintypes.UINT
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    hwnd = user32.FindWindowW(None, title)
    if not hwnd:
        return None

    class MonitorInfo(ctypes.Structure):  # pylint: disable=too-few-public-methods
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    window, info = wintypes.RECT(), MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    user32.GetWindowRect(hwnd, ctypes.byref(window))
    user32.GetMonitorInfoW(
        user32.MonitorFromWindow(hwnd, _MONITOR_DEFAULTTONEAREST), ctypes.byref(info)
    )
    work = info.rcWork
    return (
        (window.left, window.top, window.right - window.left, window.bottom - window.top),
        (work.left, work.top, work.right - work.left, work.bottom - work.top),
        (user32.GetDpiForWindow(hwnd) or _BASE_DPI) / _BASE_DPI,
    )


class WindowApi:
    """Exposée à la page (`pywebview.api`) ; `_window` et `_saved` échappent à l'introspection."""

    def __init__(self, frameless: bool = True) -> None:
        self._window = None
        self._saved: Optional[Rect] = None
        self._frameless = frameless

    def frameless(self) -> bool:
        """La page dessine-t-elle elle-même le cadre ? (faux en repli : fenêtre standard)"""
        return self._frameless

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> None:
        """Agrandir = remplir la zone utile de l'écran ; rappelé, revient à la taille d'avant."""
        if self._saved is not None:
            x, y, width, height = self._saved
            self._saved = None
            self._window.resize(width, height)
            self._window.move(x, y)
            return
        state = _screen_state(client_config.WINDOW_TITLE)
        if state is None:  # hors Windows : l'agrandissement natif
            self._window.maximize()
            return
        window, work, scale = state
        self._saved = scaled(window, scale)
        x, y, width, height = scaled(work, scale)
        self._window.resize(width, height)
        self._window.move(x, y)

    def close(self) -> None:
        self._window.destroy()

    def resize(self, width: float, height: float, fix_east: bool, fix_south: bool) -> None:
        """Taille voulue, bord opposé à la poignée tenu fixe (est pour la gauche, sud pour le haut)."""
        from webview.window import FixPoint  # pylint: disable=import-outside-toplevel

        fix_point = (FixPoint.EAST if fix_east else FixPoint.WEST) | (
            FixPoint.SOUTH if fix_south else FixPoint.NORTH
        )
        min_width, min_height = client_config.WINDOW_MIN_SIZE
        self._window.resize(max(min_width, int(width)), max(min_height, int(height)), fix_point)


def _open(url: str, frameless: bool) -> None:
    import webview  # pylint: disable=import-outside-toplevel

    api = WindowApi(frameless)
    api._window = webview.create_window(
        client_config.WINDOW_TITLE,
        url,
        js_api=api,
        width=client_config.WINDOW_SIZE[0],
        height=client_config.WINDOW_SIZE[1],
        min_size=client_config.WINDOW_MIN_SIZE,
        frameless=frameless,
        easy_drag=False,
        background_color=client_config.WINDOW_BACKGROUND,
    )
    webview.start()


def run(url: str) -> bool:
    """Ouvre la fenêtre sur `url` et rend la main à sa fermeture (fil principal, bloquant).

    Repli : fenêtre standard, puis navigateur par défaut (la page masque alors son cadre). Renvoie
    False si la fenêtre n'a pas pu s'ouvrir ; ne lève jamais d'exception.
    """
    for frameless in (True, False):
        try:
            _open(url, frameless)
            return True
        except Exception as exc:  # pylint: disable=broad-exception-caught
            kind = "sans bordure" if frameless else "standard"
            print(f"[ALERTE] Fenêtre {kind} indisponible : {exc}")
            _forget_windows()
    print(f"[ALERTE] Ouverture dans le navigateur : {url}")
    webbrowser.open(url)
    return False


def _forget_windows() -> None:
    """Oublie la fenêtre de l'essai raté, pour que l'essai suivant n'en rouvre pas deux."""
    try:
        import webview  # pylint: disable=import-outside-toplevel

        webview.windows.clear()
    except Exception:  # pylint: disable=broad-exception-caught
        pass
