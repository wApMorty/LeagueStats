"""État de partie → variables de la win chance (SPEC-20 §4.1, tâche 41).

Fonctions pures : la timeline LCU (`frames` d'une image par minute + événements
`CHAMPION_KILL`, `BUILDING_KILL`, `ELITE_MONSTER_KILL`) est rejouée dans l'ordre et
chaque état est une différence bleu − rouge. Le même dictionnaire pourra être
construit depuis la Live Client API (phase 5).
"""

import math
from typing import Iterator, Optional

from ..config_winprob import winprob_config as cfg

BLUE, RED = 100, 200

# Variables du modèle ; `gold` est calculé en plus mais hors modèle (absent de la
# Live Client API), pour mesurer ce que coûte son exclusion (SPEC-20 §4.1).
FEATURES = (
    "time_min",
    "kills",
    "towers",
    "inhibitors",
    "dragons",
    "soul",
    "herald",
    "grubs",
    "baron",
    "elder",
    "level",
    "cs",
    "dead",
    "dead_s",
)


def _respawn_s(level: int, t_s: float) -> float:
    """Temps de réapparition : base par niveau, majoré après 15 min."""
    base = cfg.RESPAWN_BASE_S[min(max(level, 1), 18) - 1]
    m = t_s / 60
    if m <= 15:
        tif = 0.0
    elif m <= 30:
        tif = math.ceil(2 * (m - 15)) * 0.00425
    elif m <= 45:
        tif = 0.1275 + math.ceil(2 * (m - 30)) * 0.003
    else:
        tif = 0.1725 + math.ceil(2 * (min(m, 55) - 45)) * 0.0145
    return base * (1 + tif)


def _other(team: int) -> int:
    return RED if team == BLUE else BLUE


class _Replay:
    """Compteurs cumulés par équipe, mis à jour événement par événement."""

    def __init__(self, teams: dict):
        self.teams = teams
        self.count = {
            t: dict.fromkeys(("kills", "towers", "inhibitors", "dragons", "herald", "grubs"), 0)
            for t in (BLUE, RED)
        }
        self.baron_t = {BLUE: None, RED: None}
        self.elder_t = {BLUE: None, RED: None}
        self.deaths = {}  # participantId -> (instant de la mort en ms, réapparition en s)
        self.level = dict.fromkeys(teams, 1)
        self.cs = dict.fromkeys(teams, 0)
        self.gold = dict.fromkeys(teams, 0)

    def frame(self, frame: dict) -> None:
        for key, pf in frame["participantFrames"].items():
            pid = int(key)
            if pid in self.teams:
                self.level[pid] = pf["level"]
                self.cs[pid] = pf["minionsKilled"] + pf["jungleMinionsKilled"]
                self.gold[pid] = pf["totalGold"]

    def event(self, e: dict) -> bool:
        """Applique l'événement ; False s'il n'est pas de ceux que le modèle suit."""
        kind, ts = e["type"], e["timestamp"]
        if kind == "CHAMPION_KILL" and e["victimId"] in self.teams:
            victim = e["victimId"]
            self.count[_other(self.teams[victim])]["kills"] += 1
            self.deaths[victim] = (ts, _respawn_s(self.level[victim], ts / 1000))
        elif kind == "BUILDING_KILL":
            # `teamId` est le propriétaire du bâtiment détruit.
            key = {"TOWER_BUILDING": "towers", "INHIBITOR_BUILDING": "inhibitors"}.get(
                e["buildingType"]
            )
            if key is None or e["teamId"] not in (BLUE, RED):
                return False
            self.count[_other(e["teamId"])][key] += 1
        elif kind == "ELITE_MONSTER_KILL" and e["killerId"] in self.teams:
            team, mob = self.teams[e["killerId"]], e["monsterType"]
            if mob == "DRAGON" and e["monsterSubType"] == "ELDER_DRAGON":
                self.elder_t[team] = ts
            elif mob == "DRAGON":
                self.count[team]["dragons"] += 1
            elif mob == "BARON_NASHOR":
                self.baron_t[team] = ts
            elif mob in ("RIFTHERALD", "HORDE"):
                self.count[team]["herald" if mob == "RIFTHERALD" else "grubs"] += 1
            else:
                return False
        else:
            return False
        return True

    def state(self, t_ms: float) -> dict:
        def active(started, buff_s):
            return {
                t: started[t] is not None and 0 <= t_ms - started[t] <= buff_s * 1000
                for t in started
            }

        def by_team(values: dict) -> dict:
            return {t: sum(v for p, v in values.items() if self.teams[p] == t) for t in (BLUE, RED)}

        c = self.count
        baron, elder = active(self.baron_t, cfg.BARON_BUFF_S), active(
            self.elder_t, cfg.ELDER_BUFF_S
        )
        lvl, cs, gold = by_team(self.level), by_team(self.cs), by_team(self.gold)
        left = {p: (d + r * 1000 - t_ms) / 1000 for p, (d, r) in self.deaths.items()}
        dead = by_team({p: 1 for p, s in left.items() if s > 0})
        dead_s = by_team({p: s for p, s in left.items() if s > 0})
        soul = {t: int(c[t]["dragons"] >= cfg.SOUL_DRAGONS) for t in (BLUE, RED)}
        state = {"time_min": t_ms / 60000, "soul": soul[BLUE] - soul[RED]}
        for name, a, b in (
            ("baron", baron[BLUE], baron[RED]),
            ("elder", elder[BLUE], elder[RED]),
            ("level", lvl[BLUE], lvl[RED]),
            ("cs", cs[BLUE], cs[RED]),
            ("gold", gold[BLUE], gold[RED]),
            ("dead", dead[BLUE], dead[RED]),
            ("dead_s", dead_s[BLUE], dead_s[RED]),
        ):
            state[name] = a - b
        for name in ("kills", "towers", "inhibitors", "dragons", "herald", "grubs"):
            state[name] = c[BLUE][name] - c[RED][name]
        return state


def walk(game: dict, timeline: dict) -> Iterator[tuple]:
    """Rejoue une partie : `(t_ms, événement ou None, état)`.

    Un état après chaque événement suivi (événement donné) et un par image
    (événement None). Les événements d'une image utilisent le niveau et les CS de
    l'image précédente.
    """
    teams = {p["participantId"]: p["teamId"] for p in game["participants"]}
    replay = _Replay(teams)
    for frame in timeline["frames"]:
        for e in frame["events"]:
            if replay.event(e):
                yield e["timestamp"], e, replay.state(e["timestamp"])
        replay.frame(frame)
        yield frame["timestamp"], None, replay.state(frame["timestamp"])


def frame_states(game: dict, timeline: dict) -> list:
    """Un état par image (une par minute) : les lignes d'entraînement du modèle."""
    return [state for _, event, state in walk(game, timeline) if event is None]


def to_vector(state: dict) -> list:
    return [state[name] for name in FEATURES]


def blue_win(game: dict) -> Optional[bool]:
    """Étiquette de la partie, None si l'issue est inconnue."""
    for team in game.get("teams", []):
        if team.get("teamId") == BLUE and team.get("win") in ("Win", "Fail"):
            return team["win"] == "Win"
    return None
