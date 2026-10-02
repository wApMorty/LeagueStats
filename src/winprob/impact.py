"""Impact de chaque événement sur la win chance, attribué aux joueurs (SPEC-20 §5, tâche 43).

ΔP = P juste après − P juste avant (même instant, compteurs mis à jour), orienté du point
de vue de l'équipe concernée. Conventions (à revoir sur données) :

- kill : la victime porte la baisse de son équipe ; tueur et assistants se partagent la hausse ;
- bâtiment, monstre épique : l'équipe qui marque porte ΔP, réparti entre tueur, assistants et
  coéquipiers présents (position à l'image la plus proche, rayon `WINPROB_PRESENCE_RADIUS`) ;
- la variation entre deux événements (temps, farm, niveaux) n'est **pas attribuée** : elle est
  renvoyée en résidu par équipe. # ponytail: à répartir au prorata des CS/XP face à l'adversaire
  de lane si le résidu pèse trop à l'usage (~0,2 de P en moyenne par partie, mesuré le 2026-10-02).
"""

import math
from typing import Dict, List, Optional

from ..config_winprob import winprob_config as cfg
from .model import WinModel
from .state import BLUE, RED, _other, transitions

_MONSTERS = {"BARON_NASHOR": "baron", "RIFTHERALD": "herald", "HORDE": "grubs"}
_BUILDINGS = {"TOWER_BUILDING": "tower", "INHIBITOR_BUILDING": "inhibitor"}


def event_kind(e: dict) -> str:
    """Nom court de l'événement suivi : kill, tower, inhibitor, dragon, elder, baron, herald, grubs."""
    if e["type"] == "CHAMPION_KILL":
        return "kill"
    if e["type"] == "BUILDING_KILL":
        return _BUILDINGS[e["buildingType"]]
    if e["monsterType"] == "DRAGON":
        return "elder" if e["monsterSubType"] == "ELDER_DRAGON" else "dragon"
    return _MONSTERS[e["monsterType"]]


def scoring_team(e: dict, teams: Dict[int, int]) -> Optional[int]:
    """Équipe qui marque : l'autre que le propriétaire d'un bâtiment, l'équipe du tueur d'un monstre."""
    if e["type"] == "BUILDING_KILL":
        return _other(e["teamId"])
    return teams.get(e["killerId"])


def _present(timeline: dict, e: dict, team_players: List[int]) -> List[int]:
    """Coéquipiers à moins de `WINPROB_PRESENCE_RADIUS` de l'événement, à l'image la plus proche."""
    position = e.get("position")
    if not position:
        return []
    frame = min(timeline["frames"], key=lambda f: abs(f["timestamp"] - e["timestamp"]))
    near = []
    for pid in team_players:
        at = frame["participantFrames"].get(str(pid), {}).get("position")
        if (
            at
            and math.hypot(at["x"] - position["x"], at["y"] - position["y"])
            <= cfg.WINPROB_PRESENCE_RADIUS
        ):
            near.append(pid)
    return near


def impacts(model: WinModel, game: dict, timeline: dict) -> dict:
    """Impacts de la partie : `rows` (une ligne par joueur et événement), `teams` (par équipe :
    attribué, total et résidu non attribué, en probabilité)."""
    teams = {p["participantId"]: p["teamId"] for p in game["participants"]}
    rows: List[dict] = []
    start = end = None
    for e, before, after in transitions(game, timeline):
        p_before, p_after = model.predict(before), model.predict(after)
        start = p_before if start is None else start
        end = p_after
        kind, ts = event_kind(e), e["timestamp"]

        def give(pid: int, team: int, share: float) -> None:
            delta = p_after - p_before
            rows.append(
                {
                    "participant_id": pid,
                    "event_time_ms": ts,
                    "event_type": kind,
                    "delta_p": share * (delta if team == BLUE else -delta),
                }
            )

        assists = [a for a in e.get("assistingParticipantIds", []) if a in teams]
        killer = [e["killerId"]] if e["killerId"] in teams else []
        if kind == "kill":
            victim = e["victimId"]
            give(victim, teams[victim], 1.0)
            gainers = [p for p in killer + assists if teams[p] != teams[victim]]
            team = _other(teams[victim])
        else:
            team = scoring_team(e, teams)
            if team is None:
                continue
            mates = [p for p, t in teams.items() if t == team]
            gainers = sorted(set(killer + assists + _present(timeline, e, mates)) & set(mates))
        for pid in gainers:
            give(pid, team, 1 / len(gainers))
    return {"rows": rows, "teams": _team_summary(rows, teams, start, end)}


def _team_summary(rows: List[dict], teams: Dict[int, int], start, end) -> dict:
    """Par équipe : attribué, variation totale de P (début → fin des événements) et résidu."""
    if start is None:
        return {}
    summary = {}
    for team, sign in ((BLUE, 1), (RED, -1)):
        attributed = sum(r["delta_p"] for r in rows if teams[r["participant_id"]] == team)
        total = sign * (end - start)
        summary[team] = {
            "attributed": attributed,
            "total": total,
            "unattributed": total - attributed,
        }
    return summary
