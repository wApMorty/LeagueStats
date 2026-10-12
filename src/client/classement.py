"""Classement des dix joueurs d'une partie par impact ΔP (SPEC-32 §4.1).

Module pur, sans base ni réseau : les lignes d'impact, le brut de la partie, les rôles et les
portraits entrent, un dictionnaire prêt pour le gabarit sort. Les portraits viennent de `Champions`.
"""

from collections import defaultdict
from typing import Dict, List, Optional

from .draft_view import ROLE_LABELS, Champions


def ranking(
    rows: List[dict], game: dict, roles: Dict[int, str], pid: int, champions: Champions
) -> Optional[dict]:
    """Les deux équipes classées par ΔP cumulé, la plus proche (celle de `pid`) d'abord.
    None si `rows` est vide ou si le brut de la partie est illisible."""
    if not rows:
        return None
    try:
        impact: Dict[int, float] = defaultdict(float)
        for row in rows:
            impact[row["participant_id"]] += row["delta_p"]
        teams = _teams(game, roles, pid, champions, impact)
        decisive = sorted(team["win"] for team in teams) == [False, True]
    except (KeyError, TypeError, ValueError):
        return None
    if decisive:  # remake (deux équipes identiques) : aucun badge
        for team in teams:
            team["players"][0]["badge"] = "MVP" if team["win"] else "ACE"
    return {"teams": sorted(teams, key=lambda team: not team["mine"])}


def _teams(
    game: dict,
    roles: Dict[int, str],
    pid: int,
    champions: Champions,
    impact: Dict[int, float],
) -> List[dict]:
    """Les équipes du brut, joueurs triés par ΔP décroissant puis `participantId`."""
    by_team: Dict[int, List[dict]] = {}
    for participant in game["participants"]:
        by_team.setdefault(participant["teamId"], []).append(participant)
    teams = []
    for members in by_team.values():
        players = []
        for participant in members:
            participant_id = participant["participantId"]
            stats = participant["stats"]
            champion_id = participant["championId"]
            players.append(
                {
                    "pid": participant_id,
                    "impact": impact.get(participant_id, 0.0),
                    "champion": champions.name(champion_id),
                    "portrait": champions.image(champion_id),
                    "role": ROLE_LABELS.get(roles.get(participant_id)),
                    "kda": f"{stats['kills']} / {stats['deaths']} / {stats['assists']}",
                    "me": participant_id == pid,
                    "badge": None,
                }
            )
        players.sort(key=lambda player: (-player["impact"], player["pid"]))
        for rank, player in enumerate(players, start=1):
            player["rank"] = rank
        teams.append(
            {
                "win": members[0]["stats"]["win"],
                "mine": any(player["me"] for player in players),
                "players": players,
            }
        )
    return teams
