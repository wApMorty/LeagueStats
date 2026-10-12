"""Impact de chaque événement sur la win chance, attribué aux joueurs (SPEC-20 §5, tâche 43).

ΔP = P juste après − P juste avant (même instant, compteurs mis à jour), orienté du point
de vue de l'équipe concernée. Conventions (à revoir sur données) :

- kill : la victime porte la baisse de son équipe ; tueur et assistants se partagent la hausse ;
- bâtiment, monstre épique : l'équipe qui marque porte ΔP, réparti entre tueur, assistants et
  coéquipiers présents (position à l'image la plus proche, rayon `WINPROB_PRESENCE_RADIUS`) ;
  l'équipe adverse porte la perte (`lost_<k>`, ΔP négatif) à parts égales entre ses joueurs
  absents (les cinq si aucun n'est absent) ;
- la variation entre deux événements est décomposée par joueur, exactement (le modèle est linéaire
  en logit sur des sommes par joueur) : `levels` (ses niveaux moins ceux de son adversaire de lane)
  et `respawn` (la récupération après une mort va à la victime, l'avance qui s'évapore débite son
  tueur et ses assistants) ; une ligne par joueur et par partie ;
- le reste (compteurs × temps, expiration des buffs, morts sans tueur) n'est pas attribuable à un
  joueur : il est renvoyé en résidu par équipe.
"""

import math
from statistics import mean
from typing import Dict, List, Optional

from ..config_winprob import winprob_config as cfg
from .model import WinModel
from .state import BLUE, RED, _other, segments, transitions

_MONSTERS = {"BARON_NASHOR": "baron", "RIFTHERALD": "herald", "HORDE": "grubs"}
_BUILDINGS = {"TOWER_BUILDING": "tower", "INHIBITOR_BUILDING": "inhibitor"}


# Un kill est rangé sous le rôle du joueur : mort (seul ou non), kill ou assistance.
KILL_TYPES = ("kill", "assist", "death", "death_solo")


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


def _lane_opponents(teams: Dict[int, int], roles: Optional[dict]) -> Dict[int, List[int]]:
    """Adversaire(s) de lane de chaque joueur : celui du même poste si les dix postes sont connus et
    distincts par équipe, sinon les cinq joueurs de l'autre équipe (la somme d'équipe reste exacte).
    """
    roles = roles or {}
    by_team = {t: [p for p, team in teams.items() if team == t] for t in (BLUE, RED)}
    lanes = {t: {roles.get(p) for p in players} for t, players in by_team.items()}
    paired = (
        len(teams) == 10
        and all(len(lanes[t]) == 5 and None not in lanes[t] for t in lanes)
        and lanes[BLUE] == lanes[RED]
    )
    return {
        p: (
            [q for q in by_team[_other(t)] if roles[q] == roles[p]]
            if paired
            else by_team[_other(t)]
        )
        for p, t in teams.items()
    }


def _segment_rows(
    model: WinModel, timeline: dict, teams: Dict[int, int], roles: Optional[dict], segs
) -> List[dict]:
    """Lignes `levels` et `respawn` : la variation de P entre deux événements, par joueur.

    Un joueur est évalué seul avec les poids du modèle (ses niveaux, sa mort), ce qui donne sa part
    exacte du changement de logit ; le rapport ΔP / Δlogit du segment la convertit en probabilité,
    orientée vers l'équipe du joueur.
    """
    zero = dict.fromkeys(model.inputs, 0.0)
    level, respawn = dict.fromkeys(teams, 0.0), dict.fromkeys(teams, 0.0)
    for a, b, players_a, players_b, killers in segs:
        p_a, p_b = model.predict(a), model.predict(b)
        d_logit = model.logit(b) - model.logit(a)
        ratio = (p_b - p_a) / d_logit if abs(d_logit) > 1e-9 else p_a * (1 - p_a)
        for pid in teams:
            solo = [
                {
                    **zero,
                    "time_min": s["time_min"],
                    **{n: float(v[n][pid]) for n in ("level", "dead", "dead_s") if n in zero},
                }
                for s, v in ((a, players_a), (b, players_b))
            ]
            parts = model.logit_parts(*solo)
            level[pid] += parts.get("level", 0.0) * ratio
            recovered = (parts.get("dead", 0.0) + parts.get("dead_s", 0.0)) * ratio
            respawn[pid] += recovered
            for killer in killers.get(pid, ()):
                respawn[killer] -= recovered / len(killers[pid])
    opponents = _lane_opponents(teams, roles)
    at = timeline["frames"][-1]["timestamp"]
    return [
        {"participant_id": pid, "event_time_ms": at, "event_type": label, "delta_p": delta}
        for label, values in (
            ("levels", {p: level[p] - mean(level[q] for q in opponents[p]) for p in teams}),
            ("respawn", respawn),
        )
        for pid, delta in values.items()
    ]


def impacts(model: WinModel, game: dict, timeline: dict, roles: Optional[dict] = None) -> dict:
    """Impacts de la partie : `rows` (une ligne par joueur et événement, plus `levels` et `respawn`
    par joueur), `teams` (par équipe : attribué, total et résidu non attribué, en probabilité).
    `roles` (`participant_roles`) apparie les adversaires de lane ; sans lui, la moyenne adverse."""
    teams = {p["participantId"]: p["teamId"] for p in game["participants"]}
    rows: List[dict] = []
    start = end = None
    for e, before, after in transitions(game, timeline):
        p_before, p_after = model.predict(before), model.predict(after)
        start = p_before if start is None else start
        end = p_after
        kind, ts = event_kind(e), e["timestamp"]

        def give(pid: int, team: int, share: float, label: str = kind) -> None:
            delta = p_after - p_before
            rows.append(
                {
                    "participant_id": pid,
                    "event_time_ms": ts,
                    "event_type": label,
                    "delta_p": share * (delta if team == BLUE else -delta),
                }
            )

        assists = [a for a in e.get("assistingParticipantIds", []) if a in teams]
        killer = [e["killerId"]] if e["killerId"] in teams else []
        if kind == "kill":
            victim = e["victimId"]
            solo = bool(killer) and not assists  # même définition que `solo_deaths` (SPEC-19)
            give(victim, teams[victim], 1.0, "death_solo" if solo else "death")
            gainers = [p for p in killer + assists if teams[p] != teams[victim]]
            team = _other(teams[victim])
        else:
            team = scoring_team(e, teams)
            if team is None:
                continue
            mates = [p for p, t in teams.items() if t == team]
            gainers = sorted(set(killer + assists + _present(timeline, e, mates)) & set(mates))
        for pid in gainers:
            give(
                pid,
                team,
                1 / len(gainers),
                "assist" if kind == "kill" and pid != e["killerId"] else kind,
            )
        if kind != "kill":
            loser = _other(team)
            foes = [p for p, t in teams.items() if t == loser]
            absent = sorted(set(foes) - set(_present(timeline, e, foes)))
            losers = absent or foes
            for pid in losers:
                give(pid, loser, 1 / len(losers), "lost_" + kind)
    if start is not None:
        rows += _segment_rows(model, timeline, teams, roles, segments(game, timeline))
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
