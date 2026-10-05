"""Rapport d'impact de fin de partie (SPEC-20 §5, tâche 44) : cumul du joueur, ses trois
événements les plus coûteux et les plus rentables, courbe de win chance."""

from collections import defaultdict
from statistics import mean
from typing import Dict, List, Tuple

from ..config_constants import coaching_config
from .impact import KILL_TYPES, event_kind, scoring_team
from .model import WinModel
from .state import BLUE, _other, frame_states

SPARK = "▁▂▃▄▅▆▇█"
LABELS = {
    "baron": "Nashor",
    "dragon": "dragon",
    "elder": "Ancien",
    "herald": "Héraut",
    "grubs": "larves",
    "tower": "tour",
    "inhibitor": "inhibiteur",
}
TAKEN = {"tower": "tour détruite", "inhibitor": "inhibiteur détruit"}
# Une mort suivie d'un objectif adverse dans ce délai est signalée avec lui.
FOLLOW_UP_MS = 60_000
TOP = 3


def _pts(delta: float) -> str:
    """Points de win chance signés, sans « -0 »."""
    return f"{round(delta * 100):+d}"


def _clock(ms: int) -> str:
    return f"{ms // 60000}:{ms // 1000 % 60:02d}"


def curve_points(
    model: WinModel, game: dict, timeline: dict, team: int
) -> List[Tuple[float, float]]:
    """`(minute, win chance de team)` à chaque image : les points de la courbe, avant son rendu."""
    points = []
    for state in frame_states(game, timeline):
        probability = model.predict(state)
        points.append((state["time_min"], probability if team == BLUE else 1 - probability))
    return points


def curve(model: WinModel, game: dict, timeline: dict, team: int) -> str:
    """Win chance de `team` à chaque image, en blocs ▁ à █ (0 % à 100 %)."""
    probs = [p for _, p in curve_points(model, game, timeline, team)]
    return "".join(SPARK[min(int(p * len(SPARK)), len(SPARK) - 1)] for p in probs)


def _describe(e: dict, pid: int, teams: Dict[int, int], events: List[dict]) -> str:
    kind, at = event_kind(e), _clock(e["timestamp"])
    if kind == "kill":
        if e["victimId"] == pid:
            solo = e["killerId"] in teams and not e.get("assistingParticipantIds")
            lost = next(
                (
                    LABELS[event_kind(o)]
                    for o in events
                    if 0 < o["timestamp"] - e["timestamp"] <= FOLLOW_UP_MS
                    and event_kind(o) in LABELS
                    and scoring_team(o, teams) == _other(teams[pid])
                ),
                None,
            )
            return f"mort{' solo' if solo else ''} à {at}" + (
                f", {lost} perdu derrière" if lost else ""
            )
        return f"{'kill' if e['killerId'] == pid else 'assistance'} à {at}"
    return f"{TAKEN.get(kind, LABELS[kind] + ' pris')} à {at}"


def impact_report(model: WinModel, game: dict, timeline: dict, pid: int, result: dict) -> List[str]:
    """Lignes du rapport pour le participant `pid`, depuis la sortie de `impacts()`."""
    teams = {p["participantId"]: p["teamId"] for p in game["participants"]}
    mine = [r for r in result["rows"] if r["participant_id"] == pid]
    events = [e for f in timeline["frames"] for e in f["events"] if _tracked(e)]
    by_key = {(e["timestamp"], event_kind(e)): e for e in events}
    total = sum(r["delta_p"] for r in mine)
    lines = [f"[DATA] Impact sur la win chance : {_pts(total)} pts cumulés"]
    lines.append(f"  Courbe de ton équipe : {curve(model, game, timeline, teams[pid])}")
    for title, rows in (
        ("Plus coûteux", sorted((r for r in mine if r["delta_p"] < 0), key=lambda r: r["delta_p"])),
        (
            "Plus rentables",
            sorted((r for r in mine if r["delta_p"] > 0), key=lambda r: -r["delta_p"]),
        ),
    ):
        for r in rows[:TOP]:
            e = by_key[
                (r["event_time_ms"], "kill" if r["event_type"] in KILL_TYPES else r["event_type"])
            ]
            lines.append(
                f"  {title} : {_pts(r['delta_p'])} pts, {_describe(e, pid, teams, events)}"
            )
    team = result["teams"].get(teams[pid])
    if team:
        lines.append(
            f"  Non attribué (temps, farm, niveaux) : {_pts(team['unattributed'])} pts pour ton "
            "équipe ; vision, placement et gestion de vague ne sont pas mesurés"
        )
    return lines


def _tracked(e: dict) -> bool:
    try:
        event_kind(e)
    except KeyError:
        return False
    return True


TYPE_LABELS = {
    "death_solo": "Morts en solo",
    "death": "Morts avec assistance adverse",
    "kill": "Kills",
    "assist": "Assistances",
    **{kind: label.capitalize() for kind, label in LABELS.items()},
}


def impact_review(rows: List[dict]) -> List[str]:
    """Section du bilan (SPEC-20 §7) : impact par partie et par type d'événement, depuis
    `CoachingRepository.player_impact` (plus récentes d'abord)."""
    games: Dict[int, float] = defaultdict(float)
    by_type: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        games[r["game_id"]] += r["delta_p"]
        by_type[r["event_type"]].append(r["delta_p"])
    if not games:
        return []
    totals = list(games.values())  # ordre d'insertion : de la plus récente à la plus ancienne
    n = len(totals)
    lines = [
        f"\n  Impact sur la win chance, sur {n} partie(s) : {_pts(mean(totals))} pts par partie "
        "en moyenne (tes événements, hors temps, farm et niveaux)"
    ]
    half = n // 2
    if half >= coaching_config.MIN_TREND_SAMPLE:
        lines.append(
            f"    dernières {half} parties : {_pts(mean(totals[:half]))} pts, "
            f"les {half} d'avant : {_pts(mean(totals[half : 2 * half]))} pts"
        )
    per_game = {t: sum(v) / n for t, v in by_type.items()}
    ranked = sorted(per_game, key=per_game.get)
    for kind in [t for t in ranked if per_game[t] < 0][:TOP] + [
        t for t in ranked[::-1] if per_game[t] > 0
    ][:2]:
        lines.append(
            f"    {TYPE_LABELS.get(kind, kind):<30} {_pts(mean(by_type[kind]))} pts en moyenne, "
            f"{len(by_type[kind]) / n:.1f} par partie ({_pts(per_game[kind])} pts par partie)"
        )
    return lines
