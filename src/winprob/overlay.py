"""Overlay de win chance en jeu (SPEC-20 §6, tâche 47).

    python -m src.winprob.overlay      # à lancer avant ou pendant une partie

Fenêtre `tkinter` séparée, au premier plan, transparente et traversée par les clics
(`WS_EX_LAYERED | WS_EX_TRANSPARENT`) : aucune injection dans le processus du jeu. Le jeu
doit être en mode fenêtré sans bordure ; en plein écran exclusif, l'overlay est masqué.

`tkinter` exige le fil principal : la fenêtre y tourne, et un fil lit la Live Client API
toutes les secondes pour la lui passer par une `queue.Queue`. Best-effort : aucune erreur de
lecture n'arrête l'overlay.
"""

import ctypes
import queue
import threading
import time
from collections import deque
from typing import Deque, Optional, Tuple

from ..config_winprob import winprob_config as cfg
from . import live
from .model import WinModel
from .train import model_path

TRANSPARENT = "#010203"  # couleur rendue transparente par `-transparentcolor`
GWL_EXSTYLE = -20
WS_EX_LAYERED, WS_EX_TRANSPARENT, WS_EX_TOOLWINDOW = 0x80000, 0x20, 0x80


class Tracker:
    """Win chance de l'équipe du joueur, et sa variation sur la dernière minute."""

    def __init__(self, model: WinModel) -> None:
        self.model = model
        self.history: Deque[Tuple[float, float]] = deque()

    def update(self, data: dict) -> dict:
        state = live.state_from_live(data)
        p = self.model.predict(state)
        active = data.get("activePlayer", {})
        mine = {active.get("summonerName"), active.get("riotId"), active.get("riotIdGameName")}
        team = next(
            (
                live.TEAMS[player["team"]]
                for player in data["allPlayers"]
                if mine & set(live.player_names(player))
            ),
            live.BLUE,  # spectateur ou joueur introuvable : point de vue de l'équipe bleue
        )
        if team != live.BLUE:
            p = 1 - p
        now = data["gameData"]["gameTime"]
        self.history.append((now, p))
        while self.history[0][0] < now - cfg.OVERLAY_TREND_S:
            self.history.popleft()
        return {"p": p, "delta": p - self.history[0][1]}


def poll(tracker: Tracker, out: "queue.Queue", stop: threading.Event) -> None:
    """Lit la Live Client API ; None dans la file quand la partie est finie."""
    seen, misses = False, 0
    while not stop.is_set():
        data = live.fetch()
        if data is None:
            misses += 1
            if seen and misses >= cfg.OVERLAY_GRACE_POLLS:
                out.put(None)
                return
        else:
            misses, seen = 0, True
            try:
                out.put(tracker.update(data))
            except (KeyError, TypeError, ValueError):
                pass  # instantané incomplet (chargement, mode spectateur) : au suivant
        stop.wait(cfg.OVERLAY_POLL_S)


def text(payload: dict) -> str:
    return f"Win chance {payload['p']:.0%}  ({round(payload['delta'] * 100):+d} pts / min)"


class Overlay:
    def __init__(
        self, source: "queue.Queue", x: Optional[int] = None, y: Optional[int] = None
    ) -> None:
        import tkinter

        self.source = source
        self.root = tkinter.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        self.root.attributes("-transparentcolor", TRANSPARENT)
        self.root.geometry(
            f"+{cfg.OVERLAY_X if x is None else x}+{cfg.OVERLAY_Y if y is None else y}"
        )
        self.label = tkinter.Label(
            self.root,
            text="Win chance : en attente de la partie",
            fg="white",
            bg=TRANSPARENT,
            font=("Segoe UI", cfg.OVERLAY_FONT_SIZE, "bold"),
        )
        self.label.pack()
        self.root.update_idletasks()
        self._click_through()
        self.root.after(250, self.refresh)

    def _click_through(self) -> None:
        """Les clics traversent la fenêtre (Windows) ; sans effet ailleurs."""
        try:
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW
            )
        except (AttributeError, OSError):
            pass

    def refresh(self) -> None:
        """Vide la file (le dernier message l'emporte) puis se reprogramme."""
        payload, finished = None, False
        try:
            while True:
                item = self.source.get_nowait()
                finished, payload = item is None, item or payload
        except queue.Empty:
            pass
        if payload:
            self.label.config(text=text(payload))
        if finished:
            self.root.destroy()
        else:
            self.root.after(250, self.refresh)


def main() -> None:
    path = model_path()
    if not path.exists():
        raise SystemExit(
            f"Pas de modèle ({path}) : lancez `python -m src.winprob.retrain --force`."
        )
    print(
        "Overlay de win chance : le jeu doit être en mode fenêtré sans bordure (Ctrl+C pour quitter)."
    )
    messages, stop = queue.Queue(), threading.Event()
    tracker = Tracker(WinModel.from_json(path.read_text(encoding="utf-8")))
    threading.Thread(target=poll, args=(tracker, messages, stop), daemon=True).start()
    try:
        Overlay(messages).root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == "__main__":
    main()
