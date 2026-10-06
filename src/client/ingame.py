"""État de la partie en cours pour l'écran « En partie » (SPEC-24 §4.9, tâche 107).

Un fil daemon du serveur du client lit la Live Client API (port 2999) pendant la partie, calcule la
win chance avec le même suiveur que l'overlay de SPEC-20 (`overlay.Tracker` : même état, même
résultat) et publie sur le bus, sujet `ingame`, l'un de ces états :

- `{"state": "idle"}` : hors partie, une seule fois ;
- `{"state": "live", game_time, p, delta, series, objectives, me}` : en partie ;
- `{"state": "ended", ...}` : la partie vient de finir, la série est gardée jusqu'à la suivante.

Best-effort : aucune exception ne sort du fil (une erreur s'annonce une fois en `[INFO]`). Lecture
seule : l'écran ne commande rien dans le jeu.
"""

import threading
from typing import Any, Callable, Dict, List, Optional

from ..config_client import client_config
from ..winprob import live
from ..winprob.model import WinModel
from ..winprob.overlay import Tracker
from ..winprob.train import model_path

TOPIC = "ingame"
IN_PROGRESS = "InProgress"

# Événements de la Live Client API marqués sur la courbe : nom -> famille.
OBJECTIVES = {
    "DragonKill": "dragon",
    "HeraldKill": "herald",
    "BaronKill": "baron",
    "TurretKilled": "turret",
    "InhibKilled": "inhibitor",
}
_STRUCTURE_OWNER = {"TOrder": "ORDER", "TChaos": "CHAOS", "T1": "ORDER", "T2": "CHAOS"}


def _load_model() -> Optional[WinModel]:
    """Le modèle de win chance entraîné, None s'il n'existe pas (l'écran dit comment l'entraîner)."""
    try:
        path = model_path()
        return WinModel.from_json(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError, KeyError):
        return None


def _my_player(data: dict) -> Optional[dict]:
    """Le joueur d'`activePlayer` dans `allPlayers`, comme `overlay.Tracker` (None : spectateur)."""
    active = data.get("activePlayer", {})
    mine = {active.get("summonerName"), active.get("riotId"), active.get("riotIdGameName")}
    return next((p for p in data["allPlayers"] if mine & set(live.player_names(p))), None)


def me_of(data: dict) -> Optional[dict]:
    """Ce que l'écran affiche de moi : champion, équipe, poste, niveau, or, objets, compétences."""
    player = _my_player(data)
    if player is None:
        return None
    active = data["activePlayer"]
    return {
        "champion": player.get("championName"),
        "team": player["team"],
        "position": player.get("position"),
        "level": player.get("level"),
        "gold": active.get("currentGold"),
        # None quand l'API ne sert pas `items` (« achats indisponibles ») ; [] : rien d'acheté.
        "items": (
            None
            if "items" not in player
            else [
                {
                    "id": item.get("itemID"),
                    "name": item.get("displayName"),
                    "slot": item.get("slot"),
                    "count": item.get("count", 1),
                    "price": item.get("price"),
                }
                for item in player["items"]
            ]
        ),
        "abilities": {
            key: ability.get("abilityLevel")
            for key, ability in (active.get("abilities") or {}).items()
            if key != "Passive"
        },
    }


def objectives_of(data: dict) -> List[Dict[str, Any]]:
    """Dragons, Héraut, Nashor, tours et inhibiteurs pris : `{t, kind, team}` (`team` : ORDER ou CHAOS)."""
    teams = {name: p["team"] for p in data["allPlayers"] for name in live.player_names(p)}
    found = []
    for event in data["events"]["Events"]:
        kind = OBJECTIVES.get(event.get("EventName"))
        if kind is None:
            continue
        team = teams.get(event.get("KillerName", ""))
        if team is None:  # tour ou inhibiteur tombé sans joueur : le camp opposé à son propriétaire
            struct = str(event.get("TurretKilled") or event.get("InhibKilled") or "")
            owner = next((v for k, v in _STRUCTURE_OWNER.items() if f"_{k}_" in struct), None)
            team = {"ORDER": "CHAOS", "CHAOS": "ORDER"}.get(owner)
        found.append({"t": event["EventTime"], "kind": kind, "team": team})
    return found


class LiveGame:
    """Lit la partie en cours et publie son état ; `tick()` fait un tour, `start()` en fait un fil."""

    def __init__(
        self,
        bus: Any,
        get_phase: Callable[[], Optional[str]],
        fetch: Callable[[], Optional[dict]] = live.fetch,
        model: Optional[WinModel] = None,
    ) -> None:
        self._bus = bus
        self._get_phase = get_phase
        self._fetch = fetch
        self._model = model
        self._model_tried = model is not None
        self._tracker: Optional[Tracker] = None
        self.series: List[List[float]] = []  # [temps de jeu en s, win chance 0 à 1]
        self._seen = False  # une partie a été lue depuis le dernier « idle »
        self._misses = 0
        self._last_time: Optional[float] = None
        self._last_state: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_payload: Dict[str, Any] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---------- un tour ----------

    def tick(self) -> float:
        """Lit et publie ; renvoie les secondes à attendre avant le prochain tour. Ne lève jamais."""
        try:
            return self._tick()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            message = f"{type(exc).__name__}: {exc}"
            if message != self._last_error:
                self._last_error = message
                print(f"[INFO] Écran « En partie » : lecture impossible ({message})")
            return client_config.INGAME_POLL_S

    def _tick(self) -> float:
        if self._get_phase() != IN_PROGRESS:
            self._leave_game()
            return client_config.INGAME_IDLE_POLL_S
        data = self._fetch()
        if data is None:
            self._misses += 1
            if self._seen and self._misses >= client_config.INGAME_GRACE_POLLS:
                self._end()
            return client_config.INGAME_POLL_S
        self._misses, self._seen = 0, True
        self._read(data)
        return client_config.INGAME_POLL_S

    def _publish(self, state: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self._last_state = state
        self._bus.publish(TOPIC, {"state": state, **(payload or {})})

    def _leave_game(self) -> None:
        """Hors partie : la partie qui vient de finir passe en « ended », sinon « idle » (une fois)."""
        if self._seen:
            self._end()
        elif self._last_state is None:
            self._publish("idle")

    def _end(self) -> None:
        """La série et la dernière lecture sont gardées jusqu'à la partie suivante."""
        self._seen = False
        if self._last_state != "ended":
            self._publish("ended", {**self._last_payload, "series": [list(p) for p in self.series]})

    def _read(self, data: dict) -> None:
        game_time = float(data["gameData"]["gameTime"])
        if self._last_time is not None and game_time < self._last_time - 1:
            self.series, self._tracker = [], None  # une autre partie
        self._last_time = game_time
        p = delta = None
        model = self._model_for_game()
        if model is not None:
            if self._tracker is None:
                self._tracker = Tracker(model)
            result = self._tracker.update(data)
            p, delta = result["p"], result["delta"]
            sample = client_config.INGAME_SAMPLE_S
            if not self.series or game_time - self.series[-1][0] >= sample:
                self.series.append([game_time, p])
                del self.series[: -client_config.INGAME_MAX_POINTS]
        self._last_payload = {
            "game_time": game_time,
            "p": p,
            "delta": delta,
            "objectives": objectives_of(data),
            "me": me_of(data),
        }
        self._publish(
            "live", {**self._last_payload, "series": [list(point) for point in self.series]}
        )

    def _model_for_game(self) -> Optional[WinModel]:
        if not self._model_tried:
            self._model, self._model_tried = _load_model(), True
        return self._model

    # ---------- le fil ----------

    def start(self) -> None:
        """Lance le fil (une seule fois)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="ingame", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self._stop.wait(self.tick())

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(client_config.SERVER_STOP_TIMEOUT_S)
