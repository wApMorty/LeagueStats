"""Métriques de la grille pour les 10 participants (SPEC-19 §5.1, tâche 31).

Fonctions pures : brut LCU (`games/{id}`, timeline, écran de fin) -> lignes
de `game_metrics`. Aucune base, aucun réseau.

Chaque métrique est normalisée à la minute ou prise à un instant fixe, pour
neutraliser la durée de partie. Une métrique incalculable (partie trop courte,
timeline absente, adversaire direct inconnu) est omise plutôt que mise à 0.
"""

from dataclasses import dataclass
from typing import Dict, List, NamedTuple, Optional

from ..config_constants import coaching_config

# Postes de l'écran de fin -> lanes internes (scraping_config.LANES).
EOG_POSITIONS = {
    "TOP": "top",
    "JUNGLE": "jungle",
    "MIDDLE": "middle",
    "BOTTOM": "bottom",
    "UTILITY": "support",
}
ROLES = tuple(EOG_POSITIONS.values())
# Monstres épiques de la présence aux objectifs (dragons, larves, Héraut, Baron, Atakhan).
ELITE_MONSTERS = ("DRAGON", "HORDE", "RIFTHERALD", "BARON_NASHOR", "ATAKHAN")


@dataclass(frozen=True)
class Metric:
    """Définition d'une métrique : libellé console, sens et format."""

    label: str
    sense: int  # +1 si plus est mieux, -1 sinon
    fmt: str  # format de la valeur, ex. "{:.0f}" ou "{:.0%}"
    zero_sum: bool = False  # écart face à l'adversaire direct (grid.norm_reference)


METRICS: Dict[str, Metric] = {
    "cs_10": Metric("CS @10", 1, "{:.0f}"),
    "cs_14": Metric("CS @14", 1, "{:.0f}"),
    "cs_per_min": Metric("CS/min", 1, "{:.1f}"),
    "gold_diff_15": Metric("Écart d'or @15", 1, "{:+.0f}", zero_sum=True),
    "xp_diff_15": Metric("Écart d'XP @15", 1, "{:+.0f}", zero_sum=True),
    "deaths_before_14": Metric("Morts avant 14 min", -1, "{:.0f}"),
    "solo_deaths": Metric("Morts en solo", -1, "{:.0f}"),
    "deaths_per_10": Metric("Morts / 10 min", -1, "{:.1f}"),
    "kill_participation": Metric("Participation aux kills", 1, "{:.0%}"),
    "objective_presence": Metric("Présence aux objectifs", 1, "{:.0%}"),
    "damage_per_min": Metric("Dégâts / min", 1, "{:.0f}"),
    "damage_share": Metric("Part des dégâts", 1, "{:.0%}"),
    "structure_damage_per_min": Metric("Dégâts aux structures / min", 1, "{:.0f}"),
    "vision_per_min": Metric("Vision / min", 1, "{:.2f}"),
    "wards_killed_per_10": Metric("Wards détruites / 10 min", 1, "{:.1f}"),
    "control_wards_per_10": Metric("Pinks achetées / 10 min", 1, "{:.1f}"),
}


class MetricRow(NamedTuple):
    participant_id: int
    team_id: int
    role: Optional[str]
    champion_id: int
    metric: str
    value: float


def format_value(metric: str, value: float) -> str:
    return METRICS[metric].fmt.format(value)


# ---------- postes ----------


def participant_roles(game: dict, eog: Optional[dict] = None) -> Dict[int, Optional[str]]:
    """participantId -> lane, None si le poste reste ambigu.

    L'écran de fin fait foi quand il existe ; sinon l'objet de quête de rôle
    (`roleBoundItem`), puis Châtiment pour la jungle, puis l'élimination : le
    dernier inconnu d'une équipe prend le dernier poste libre.
    """
    positions: Dict[tuple, str] = {}
    for team in (eog or {}).get("teams") or []:
        for player in team.get("players") or []:
            lane = EOG_POSITIONS.get(player.get("detectedTeamPosition", ""))
            if lane:
                positions[(player["teamId"], player["championId"])] = lane

    roles: Dict[int, Optional[str]] = {}
    for team_id in {p["teamId"] for p in game["participants"]}:
        team = [p for p in game["participants"] if p["teamId"] == team_id]
        guesses = {p["participantId"]: _guess_role(p, positions) for p in team}
        taken = [lane for lane in guesses.values() if lane]
        for pid, lane in guesses.items():  # un poste revendiqué deux fois est ambigu
            if lane and taken.count(lane) > 1:
                guesses[pid] = None
        unknown = [pid for pid, lane in guesses.items() if lane is None]
        free = [lane for lane in ROLES if lane not in guesses.values()]
        if len(unknown) == 1 and len(free) == 1:
            guesses[unknown[0]] = free[0]
        roles.update(guesses)
    return roles


def _guess_role(participant: dict, positions: Dict[tuple, str]) -> Optional[str]:
    known = positions.get((participant["teamId"], participant["championId"]))
    if known:
        return known
    item = participant["stats"].get("roleBoundItem") or 0
    if item in coaching_config.ROLE_BOUND_ITEMS:
        return coaching_config.ROLE_BOUND_ITEMS[item]
    if coaching_config.SMITE_SPELL_ID in (participant.get("spell1Id"), participant.get("spell2Id")):
        return "jungle"
    return "bottom" if item else None


# ---------- métriques ----------


def is_remake(game: dict) -> bool:
    """Partie écourtée (remake) : rien à juger."""
    return any(p["stats"].get("gameEndedInEarlySurrender") for p in game["participants"])


def _frame(timeline: Optional[dict], minute: int) -> Optional[dict]:
    """participantFrames à la minute donnée (une image par minute), ou None."""
    frames = (timeline or {}).get("frames") or []
    return frames[minute]["participantFrames"] if len(frames) > minute else None


def _events(timeline: Optional[dict], kind: str) -> List[dict]:
    return [
        event
        for frame in (timeline or {}).get("frames") or []
        for event in frame.get("events") or []
        if event.get("type") == kind
    ]


def compute_metrics(
    game: dict, timeline: Optional[dict] = None, eog: Optional[dict] = None
) -> List[MetricRow]:
    """Toutes les métriques calculables, pour les 10 participants."""
    if is_remake(game) or not game.get("gameDuration"):
        return []
    minutes = game["gameDuration"] / 60
    roles = participant_roles(game, eog)
    by_id = {p["participantId"]: p for p in game["participants"]}
    team_of = {pid: p["teamId"] for pid, p in by_id.items()}
    team_kills: Dict[int, int] = {}
    team_damage: Dict[int, int] = {}
    for p in game["participants"]:
        team_kills[p["teamId"]] = team_kills.get(p["teamId"], 0) + p["stats"]["kills"]
        team_damage[p["teamId"]] = (
            team_damage.get(p["teamId"], 0) + p["stats"]["totalDamageDealtToChampions"]
        )

    kills = _events(timeline, "CHAMPION_KILL")
    monsters = [
        e
        for e in _events(timeline, "ELITE_MONSTER_KILL")
        if e.get("monsterType") in ELITE_MONSTERS and e.get("killerId") in team_of
    ]
    early, lane, diff = (
        _frame(timeline, coaching_config.EARLY_MINUTE),
        _frame(timeline, coaching_config.LANE_MINUTE),
        _frame(timeline, coaching_config.DIFF_MINUTE),
    )

    rows: List[MetricRow] = []
    for pid, p in by_id.items():
        s, team = p["stats"], p["teamId"]
        values: Dict[str, Optional[float]] = {
            "cs_per_min": (s["totalMinionsKilled"] + s["neutralMinionsKilled"]) / minutes,
            "deaths_per_10": s["deaths"] / minutes * 10,
            "kill_participation": _ratio(s["kills"] + s["assists"], team_kills[team]),
            "damage_per_min": s["totalDamageDealtToChampions"] / minutes,
            "damage_share": _ratio(s["totalDamageDealtToChampions"], team_damage[team]),
            "structure_damage_per_min": s["damageDealtToTurrets"] / minutes,
            "vision_per_min": s["visionScore"] / minutes,
            "wards_killed_per_10": s["wardsKilled"] / minutes * 10,
            "control_wards_per_10": s["visionWardsBoughtInGame"] / minutes * 10,
        }
        if timeline and timeline.get("frames"):
            values["deaths_before_14"] = sum(
                1
                for e in kills
                if e.get("victimId") == pid
                and e["timestamp"] < coaching_config.LANE_MINUTE * 60_000
            )
            values["solo_deaths"] = sum(
                1
                for e in kills
                if e.get("victimId") == pid
                and e.get("killerId") in team_of
                and not e.get("assistingParticipantIds")
            )
            team_monsters = [e for e in monsters if team_of[e["killerId"]] == team]
            values["objective_presence"] = _ratio(
                sum(
                    1
                    for e in team_monsters
                    if pid == e["killerId"] or pid in (e.get("assistingParticipantIds") or [])
                ),
                len(team_monsters),
            )
        for name, frame in (("cs_10", early), ("cs_14", lane)):
            if frame:
                values[name] = _cs(frame, pid)
        opponent = _opponent(pid, roles, team_of)
        if diff and opponent:
            mine, theirs = diff[str(pid)], diff[str(opponent)]
            values["gold_diff_15"] = mine["totalGold"] - theirs["totalGold"]
            values["xp_diff_15"] = mine["xp"] - theirs["xp"]

        rows.extend(
            MetricRow(pid, team, roles.get(pid), p["championId"], name, float(value))
            for name, value in values.items()
            if value is not None
        )
    return rows


def _ratio(part: float, total: float) -> Optional[float]:
    return part / total if total else None


def _cs(frame: dict, pid: int) -> int:
    player = frame[str(pid)]
    return player["minionsKilled"] + player["jungleMinionsKilled"]


def _opponent(pid: int, roles: Dict[int, Optional[str]], team_of: Dict[int, int]) -> Optional[int]:
    """Adversaire direct : même poste, autre équipe."""
    if not roles.get(pid):
        return None
    return next(
        (
            other
            for other, lane in roles.items()
            if lane == roles[pid] and team_of[other] != team_of[pid]
        ),
        None,
    )
