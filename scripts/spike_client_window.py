"""Spike SPEC-21 tâche 48 : fenêtre pywebview sans bordure servie par uvicorn.

    python scripts/spike_client_window.py            # fenêtre à manipuler à la main
    python scripts/spike_client_window.py --auto     # mesures automatiques, JSON dans --out

Mesure, sans rien dépendre du reste du produit : le délai jusqu'à la première image, les temps
d'image de deux scènes d'animation (cartes en transform/opacity, tracé SVG), le coût d'un
aller-retour JS -> Python (qui décide d'un redimensionnement fluide par poignées HTML) et le
comportement Windows d'une fenêtre sans bordure (style, zones de redimensionnement, agrandissement
face à la barre des tâches). Empaquetable seul avec PyInstaller (voir docs/specs/SPEC-21 §8).
"""

import argparse
import ctypes
import json
import os
import socket
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

import psutil
import uvicorn
import webview
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

TITLE = "LeagueStats spike"
SIZE = (1280, 800)
MIN_SIZE = (960, 600)
AUTO_TIMEOUT_S = 40
SCREENSHOT_DELAY_S = 1.5

# Constantes Win32 (winuser.h).
GWL_STYLE = -16
WM_NCHITTEST = 0x84
STYLE_FLAGS = {
    "caption": 0xC00000,
    "thickframe": 0x40000,
    "sysmenu": 0x80000,
    "minimizebox": 0x20000,
    "maximizebox": 0x10000,
}
HIT_NAMES = {1: "client", 2: "caption", 10: "left", 11: "right", 12: "top", 13: "topleft",
             14: "topright", 15: "bottom", 16: "bottomleft", 17: "bottomright", 18: "border"}  # fmt: skip
MONITOR_DEFAULTTONEAREST = 2


def asset_dir() -> Path:
    """Dossier du gabarit : `_MEIPASS` dans l'exe (démontre `datas`), `scripts/` sinon."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent))


class Api:
    """Exposée à la page ; `_window` (souligné) échappe à l'introspection de pywebview."""

    _window = None
    _saved = None

    def minimize(self) -> None:
        self._window.minimize()

    def toggle_maximize(self) -> None:
        """Agrandir = remplir la zone utile (barre des tâches exclue), pas `maximize()`."""
        if self._saved is None:
            self._saved = fit_work_area(self._window)
        else:
            x, y, w, h = self._saved
            self._saved = None
            self._window.resize(w, h)
            self._window.move(x, y)

    def close(self) -> None:
        self._window.destroy()

    def ping(self) -> int:
        return 1

    def resize_to(self, width: float, height: float) -> None:
        self._window.resize(max(MIN_SIZE[0], int(width)), max(MIN_SIZE[1], int(height)))


def make_app(state: dict) -> FastAPI:
    app = FastAPI()
    page = (asset_dir() / "spike_client_page.html").read_text(encoding="utf-8")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return page

    @app.post("/ready")
    def ready() -> dict:
        state.setdefault("ready_epoch", time.time())
        return {}

    @app.post("/metrics")
    async def metrics(request: Request) -> dict:
        state["metrics"] = await request.json()
        state["metrics_done"].set()
        return {}

    return app


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_server(app: FastAPI, port: int) -> uvicorn.Server:
    # log_config=None : sans console (exe fenêtré), sys.stdout est None et le logging d'uvicorn plante.
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", log_config=None)
    )
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.01)
    return server


def win32():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.IsZoomed.argtypes = [wintypes.HWND]
    user32.GetForegroundWindow.restype = wintypes.HWND
    return user32


def rect_of(user32, hwnd) -> dict:
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return {"left": r.left, "top": r.top, "right": r.right, "bottom": r.bottom,
            "width": r.right - r.left, "height": r.bottom - r.top}  # fmt: skip


def work_area(user32, hwnd) -> dict:
    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                    ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]  # fmt: skip

    info = MONITORINFO()
    info.cbSize = ctypes.sizeof(MONITORINFO)
    monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    user32.GetMonitorInfoW(monitor, ctypes.byref(info))
    w, m = info.rcWork, info.rcMonitor
    return {
        "work": [w.left, w.top, w.right, w.bottom],
        "monitor": [m.left, m.top, m.right, m.bottom],
    }


def hit_test(user32, hwnd, x: int, y: int) -> str:
    lparam = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
    code = user32.SendMessageW(hwnd, WM_NCHITTEST, 0, lparam)
    return HIT_NAMES.get(code, str(code))


def screenshot(rect: dict, path: Path) -> None:
    from PIL import ImageGrab

    margin = 40  # déborde pour voir ombre et coins
    box = (
        rect["left"] - margin,
        rect["top"] - margin,
        rect["right"] + margin,
        rect["bottom"] + margin,
    )
    ImageGrab.grab(bbox=box, all_screens=True).save(path)


def fit_work_area(window) -> tuple:
    """Place la fenêtre sur la zone utile de son écran ; renvoie l'ancienne (x, y, l, h)."""
    user32 = win32()
    hwnd = user32.FindWindowW(None, TITLE)
    before = rect_of(user32, hwnd)
    left, top, right, bottom = work_area(user32, hwnd)["work"]
    window.resize(right - left, bottom - top)
    window.move(left, top)
    return before["left"], before["top"], before["width"], before["height"]


def drag(user32, x: int, y: int, dx: int, dy: int, steps: int = 20) -> None:
    """Glissement réel de la souris (bouton gauche) : valide zone de déplacement et poignées."""
    user32.SetCursorPos(x, y)
    time.sleep(0.2)
    user32.mouse_event(0x2, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTDOWN
    for i in range(1, steps + 1):
        user32.SetCursorPos(x + dx * i // steps, y + dy * i // steps)
        time.sleep(0.02)
    user32.mouse_event(0x4, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
    time.sleep(0.3)


def probe_window(window, out: dict, shot: Path) -> None:
    """Comportement Windows de la fenêtre sans bordure, mesuré sur la fenêtre réelle."""
    user32 = win32()
    hwnd = user32.FindWindowW(None, TITLE)
    if not hwnd:
        out["window_error"] = "fenêtre introuvable"
        return
    style = user32.GetWindowLongW(hwnd, GWL_STYLE) & 0xFFFFFFFF
    out["style"] = {name: bool(style & flag) for name, flag in STYLE_FLAGS.items()}
    rect = rect_of(user32, hwnd)
    out["rect_initial"] = rect
    cx, cy = (rect["left"] + rect["right"]) // 2, (rect["top"] + rect["bottom"]) // 2
    points = {
        "left": (rect["left"] + 2, cy), "right": (rect["right"] - 3, cy),
        "top": (cx, rect["top"] + 2), "bottom": (cx, rect["bottom"] - 3),
        "bottomright": (rect["right"] - 3, rect["bottom"] - 3),
        "titlebar": (cx, rect["top"] + 15), "center": (cx, cy),
    }  # fmt: skip
    out["hit_test"] = {name: hit_test(user32, hwnd, *p) for name, p in points.items()}

    window.resize(1000, 700)
    time.sleep(0.4)
    out["after_resize_1000x700"] = rect_of(user32, hwnd)
    window.move(120, 90)
    time.sleep(0.4)
    out["after_move_120_90"] = rect_of(user32, hwnd)

    window.maximize()
    time.sleep(0.8)
    out["maximized"] = {"rect": rect_of(user32, hwnd), "zoomed": bool(user32.IsZoomed(hwnd)),
                        **work_area(user32, hwnd)}  # fmt: skip
    window.restore()
    time.sleep(0.5)
    out["restored"] = rect_of(user32, hwnd)

    # Agrandir par la zone utile (ce que fera le bouton de la barre de titre).
    window.resize(*SIZE)
    window.move(120, 90)
    time.sleep(0.4)
    window.evaluate_js("pywebview.api.toggle_maximize()")
    time.sleep(0.8)
    out["maximize_work_area"] = {"rect": rect_of(user32, hwnd), **work_area(user32, hwnd)}
    window.evaluate_js("pywebview.api.toggle_maximize()")
    time.sleep(0.8)
    out["maximize_work_area_restored"] = rect_of(user32, hwnd)

    # Glissements réels : barre de titre (déplacement) puis poignée d'angle (redimensionnement).
    window.resize(*SIZE)
    window.move(120, 90)
    time.sleep(0.5)
    r = rect_of(user32, hwnd)
    drag(user32, r["left"] + 400, r["top"] + 15, 150, 100)
    out["drag_titlebar_+150_+100"] = {"before": r, "after": rect_of(user32, hwnd)}
    r = rect_of(user32, hwnd)
    drag(user32, r["right"] - 4, r["bottom"] - 4, 100, 60)
    out["drag_corner_+100_+60"] = {"before": r, "after": rect_of(user32, hwnd)}
    window.resize(*SIZE)
    window.move(120, 90)
    time.sleep(0.5)

    # Ancrage Windows (Win + Flèche gauche), seulement si la fenêtre a le focus : sinon on ne
    # touche à rien, la touche irait à une autre application.
    if user32.GetForegroundWindow() == hwnd:
        before = rect_of(user32, hwnd)
        for vk, up in ((0x5B, 0), (0x25, 0), (0x25, 2), (0x5B, 2)):  # Win, Gauche, relâchés
            user32.keybd_event(vk, 0, up, 0)
        time.sleep(1.0)
        out["snap_win_left"] = {"before": before, "after": rect_of(user32, hwnd)}
        window.resize(*SIZE)
        window.move(120, 90)
    else:
        out["snap_win_left"] = "fenêtre sans le focus, non testé"
    time.sleep(SCREENSHOT_DELAY_S)
    screenshot(rect_of(user32, hwnd), shot)


def run_auto(window, state: dict, out_path: Path, launch_epoch: float | None) -> None:
    result = {"python": sys.version.split()[0], "frozen": bool(getattr(sys, "frozen", False)),
              "pid": os.getpid()}  # fmt: skip
    started = time.time()
    try:
        while not state.get("ready_epoch") and time.time() - started < AUTO_TIMEOUT_S:
            time.sleep(0.05)
        if launch_epoch and state.get("ready_epoch"):
            result["startup_s"] = round(state["ready_epoch"] - launch_epoch, 3)
        if state.get("ready_epoch"):
            result["since_process_start_s"] = round(
                state["ready_epoch"] - psutil.Process().create_time(), 3
            )
        state["metrics_done"].wait(AUTO_TIMEOUT_S)  # les scènes tournent pendant ce temps
        result["page"] = state.get("metrics")
        probe_window(window, result, out_path.with_suffix(".png"))
    except Exception as exc:  # le spike doit toujours écrire son résultat
        result["error"] = repr(exc)
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    window.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--auto", action="store_true", help="mesures automatiques puis sortie")
    parser.add_argument("--out", default="spike_result.json", help="JSON de résultat (--auto)")
    parser.add_argument("--standard", action="store_true", help="fenêtre standard (repli)")
    args = parser.parse_args()
    if os.environ.get("SPIKE_LOG"):  # exe fenêtré : sans console, les erreurs vont dans un fichier
        import logging

        logging.basicConfig(filename=os.environ["SPIKE_LOG"], level=logging.INFO)

    state = {"metrics_done": threading.Event()}
    port = free_port()
    start_server(make_app(state), port)
    api = Api()
    window = webview.create_window(
        TITLE,
        f"http://127.0.0.1:{port}/",
        js_api=api,
        width=SIZE[0],
        height=SIZE[1],
        min_size=MIN_SIZE,
        frameless=not args.standard,
        easy_drag=False,
        background_color="#0b0d12",
    )
    api._window = window
    launch = os.environ.get("SPIKE_LAUNCH_EPOCH")
    if args.auto:
        webview.start(run_auto, (window, state, Path(args.out), float(launch) if launch else None))
    else:
        webview.start()


if __name__ == "__main__":
    main()
