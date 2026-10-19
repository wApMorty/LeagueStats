"""Étude Moneyball du début de partie (SPEC-35 §4.1, tâche 171).

Ce que chaque joueur fait avant 14 min : CS, morts, morts solo, morts sans contrepartie, présence aux
objectifs, et vision (en fin de partie, hors classement). Fonctions pures, sans base ni réseau : elles
lisent le format LCU commun à `crawl.db` et `game_records`.

`lane_rows` donne, par rôle, les écarts bleu − rouge entre adversaires de lane ; `player_gaps` donne les
écarts d'un joueur à son adversaire de lane. La valorisation (tâche 172) et la décision (tâche 173)
partent de ces lignes.
"""

from typing import Dict, List, Optional, Tuple

from ..config_constants import coaching_config
from ..winprob import impact
from ..winprob.state import BLUE, _other
from . import metrics

ACTIONS = ("cs", "deaths", "solo_deaths", "untraded_deaths", "presence")
# Valeurs suivies par `lane_rows` et `player_gaps` : les actions, plus la vision (hors classement).
_VALUES = ACTIONS + ("vision",)


def _team_of(game: dict) -> Dict[int, int]:
    """participantId -> teamId."""
    return {p["participantId"]: p["teamId"] for p in game["participants"]}


def _usable(game: dict, timeline: Optional[dict], minute: int) -> bool:
    """Partie exploitable à `minute` : pas de remake, durée suffisante, image de `minute` présente."""
    frames = (timeline or {}).get("frames") or []
    return (
        not metrics.is_remake(game)
        and (game.get("gameDuration") or 0) >= coaching_config.MONEYBALL_MIN_DURATION_MIN * 60
        and len(frames) > minute
    )


def _contributions(timeline: dict, team_of: Dict[int, int]) -> List[Tuple[int, int]]:
    """(instant, équipe) de chaque événement qui rapporte à une équipe, dans toute la timeline.

    Un kill rapporte à l'équipe de la victime adverse (comme le compteur de `winprob.state`). Un monstre
    épique ou un bâtiment rapporte à l'équipe qui le marque.
    """
    out = []
    for e in metrics._events(timeline, "CHAMPION_KILL"):
        if e.get("victimId") in team_of:
            out.append((e["timestamp"], _other(team_of[e["victimId"]])))
    for kind in ("ELITE_MONSTER_KILL", "BUILDING_KILL"):
        for e in metrics._events(timeline, kind):
            team = impact.scoring_team(e, team_of)
            if team is not None:
                out.append((e["timestamp"], team))
    return out


def _traded(t: int, team: int, contributions: List[Tuple[int, int]], window: int) -> bool:
    """Vrai si `team` rapporte un événement à ± `window` ms de l'instant `t` (la mort s'échange)."""
    return any(c_team == team and abs(ts - t) <= window for ts, c_team in contributions)


def player_actions(game: dict, timeline: dict, minute: int) -> Dict[int, Dict[str, float]]:
    """participantId -> actions à `minute` : CS, morts, morts solo, morts sans contrepartie, présence
    aux objectifs (part des monstres épiques de son équipe avant `minute` où il est présent). Plus
    `vision` (visionScore / min de partie entière, hors classement).

    Rend `{}` si l'image `minute` manque (pas de CS à lire).
    """
    frame = metrics._frame(timeline, minute)
    if frame is None:
        return {}
    team_of = _team_of(game)
    cutoff = minute * 60_000
    window = int(coaching_config.MONEYBALL_TRADE_WINDOW_S * 1000)
    kills = metrics._events(timeline, "CHAMPION_KILL")
    contributions = _contributions(timeline, team_of)
    monsters = [
        e
        for e in metrics._events(timeline, "ELITE_MONSTER_KILL")
        if e.get("monsterType") in metrics.ELITE_MONSTERS
        and e.get("killerId") in team_of
        and e["timestamp"] < cutoff
    ]
    actions: Dict[int, Dict[str, float]] = {}
    for p in game["participants"]:
        pid, team = p["participantId"], p["teamId"]
        deaths = [e for e in kills if e.get("victimId") == pid and e["timestamp"] < cutoff]
        solo = [
            e
            for e in deaths
            if e.get("killerId") in team_of and not e.get("assistingParticipantIds")
        ]
        untraded = [e for e in deaths if not _traded(e["timestamp"], team, contributions, window)]
        team_monsters = [e for e in monsters if team_of[e["killerId"]] == team]
        present = [
            e
            for e in team_monsters
            if pid == e["killerId"]
            or pid in (e.get("assistingParticipantIds") or [])
            or impact.present(timeline, e, [pid])
        ]
        actions[pid] = {
            "cs": float(metrics._cs(frame, pid)),
            "deaths": float(len(deaths)),
            "solo_deaths": float(len(solo)),
            "untraded_deaths": float(len(untraded)),
            "presence": len(present) / max(len(team_monsters), 1),
            "vision": p["stats"]["visionScore"] / (game["gameDuration"] / 60),
        }
    return actions


def _lane_pairs(
    roles: Dict[int, Optional[str]], team_of: Dict[int, int]
) -> Optional[Dict[str, Tuple[int, int]]]:
    """Rôle -> (participantId bleu, participantId rouge), None si un rôle manque ou est dupliqué
    dans une équipe (il faut exactement `metrics.ROLES` des deux côtés)."""
    pairs: Dict[str, Tuple[int, int]] = {}
    for role in metrics.ROLES:
        blue = [pid for pid, lane in roles.items() if lane == role and team_of[pid] == BLUE]
        red = [pid for pid, lane in roles.items() if lane == role and team_of[pid] != BLUE]
        if len(blue) != 1 or len(red) != 1:
            return None
        pairs[role] = (blue[0], red[0])
    return pairs


def lane_rows(game: dict, timeline: dict, minute: int) -> Dict[str, Dict[str, float]]:
    """Rôle -> écarts bleu − rouge des actions entre adversaires de lane, à `minute`.

    Vide si un poste manque ou est ambigu (`participant_roles`), si la partie est un remake, si elle
    dure moins de `MONEYBALL_MIN_DURATION_MIN`, ou si l'image `minute` manque.
    """
    if not _usable(game, timeline, minute):
        return {}
    team_of = _team_of(game)
    pairs = _lane_pairs(metrics.participant_roles(game), team_of)
    if pairs is None:
        return {}
    values = player_actions(game, timeline, minute)
    return {
        role: {k: values[blue][k] - values[red][k] for k in _VALUES}
        for role, (blue, red) in pairs.items()
    }


def player_gaps(
    game: dict, timeline: dict, eog: Optional[dict], player_pid: int, minute: int
) -> Optional[Tuple[str, Dict[str, float]]]:
    """(rôle, écarts joueur − adversaire de lane) pour une partie de @pj35, None si incalculable.

    Mêmes exclusions que `lane_rows` (remake, durée, image). Rôle par `participant_roles(game, eog)`,
    adversaire par `metrics._opponent` ; None s'il n'y a pas d'adversaire.
    """
    if not _usable(game, timeline, minute):
        return None
    roles = metrics.participant_roles(game, eog)
    role = roles.get(player_pid)
    if not role:
        return None
    opponent = metrics._opponent(player_pid, roles, _team_of(game))
    if opponent is None:
        return None
    values = player_actions(game, timeline, minute)
    return role, {k: values[player_pid][k] - values[opponent][k] for k in _VALUES}
