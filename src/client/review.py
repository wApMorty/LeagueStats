"""Parties capturées dans le client : la liste et la page d'une partie (SPEC-21 §4.4, tâches 53 et 75).

Lecture de la base seulement (`CoachingRepository`) : ni rapport texte dupliqué, ni appel LCU. Le brut
de la partie et sa timeline donnent les noms, les postes et le libellé des événements ; l'impact par
événement vient de `game_impact` (SPEC-20) et la courbe de win chance du modèle entraîné
(`winprob.report.curve_points`). Une donnée absente est dite, jamais inventée : « impact non calculé »,
« pas de timeline », « modèle absent ».
"""

import json
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from markupsafe import Markup

from ..coaching.metrics import METRICS, format_value
from ..config_client import client_config
from ..repositories.coaching import CoachingRepository
from ..winprob.impact import KILL_TYPES, event_kind, impacts, scoring_team
from ..winprob.model import WinModel
from ..winprob.report import LABELS, TAKEN, curve_points
from ..winprob.train import model_path
from .charts import Band, Mark, Series, Tick, diverging, line_chart
from .data import ago, date_fr, finding_reference, parse_utc, plural, tier_name
from .draft_view import ROLE_LABELS, Champions, fr, signed

# Couleur du repère d'un événement qui rapporte (un événement qui coûte est toujours rose).
KIND_COLORS = {
    "baron": "oklch(0.74 0.22 310)",
    "tower": "oklch(0.88 0.14 85)",
    "dragon": "oklch(0.76 0.18 45)",
    "elder": "oklch(0.76 0.18 45)",
    "grubs": "oklch(0.72 0.2 290)",
    "herald": "oklch(0.76 0.15 230)",
    "inhibitor": "oklch(0.86 0.15 110)",
    "kill": "oklch(0.82 0.14 160)",
}
COST_COLOR = "var(--rose)"
SHORT = {"tower": "Tour", "inhibitor": "Inhib.", "grubs": "Larves", "elder": "Ancien"}
LOST = {"tower": "Tour perdue", "inhibitor": "Inhibiteur perdu"}
DEATHS = ("death", "death_solo")
CURVE_STOPS = ("var(--blue)", "var(--violet)", "var(--mint)", "oklch(0.9 0.14 95)")


def load_model() -> Optional[WinModel]:
    """Le modèle de win chance entraîné, ou None (absent ou illisible : la courbe n'est pas tracée)."""
    try:
        path = model_path()
        return WinModel.from_json(path.read_text(encoding="utf-8")) if path.exists() else None
    except (OSError, ValueError, KeyError):
        return None


def clock(seconds: float) -> str:
    return f"{int(seconds) // 60:02d}:{int(seconds) % 60:02d}"


def _ended(record: dict, game: dict) -> datetime:
    """Heure de fin de la partie : son début plus sa durée."""
    return parse_utc(record["created"]) + timedelta(
        seconds=record["duration_s"] or game.get("gameDuration", 0)
    )


def _opponent(players: Dict[int, dict], roles: Dict[int, str], pid: int) -> Optional[dict]:
    role = roles.get(pid)
    mine = players[pid]["teamId"]
    return next(
        (
            p
            for p in players.values()
            if role and p["teamId"] != mine and roles.get(p["participantId"]) == role
        ),
        None,
    )


def _player_impact(repo: CoachingRepository, game_id: int, pid: int) -> Optional[float]:
    rows = repo.impact_rows(game_id, pid)
    return sum(r["delta_p"] for r in rows) if rows else None


def _pts(delta: float) -> str:
    """Points de win chance signés, à la française, sans « −0,0 »."""
    points = round(delta * 100, 1)
    return fr(0, 1) if points == 0 else signed(points, 1)


# ---------- liste ----------


def _row(repo: CoachingRepository, record: dict, champions: Champions, now: datetime) -> dict:
    game = json.loads(record["game"])
    players = {p["participantId"]: p for p in game["participants"]}
    pid = record["pid"]
    me = players[pid]
    roles = repo.game_roles(record["game_id"])
    opponent = _opponent(players, roles, pid)
    stats = me["stats"]
    rank = repo.rank_after_game(record["game_id"])
    impact = _player_impact(repo, record["game_id"], pid)
    ended = _ended(record, game)
    return {
        "game_id": record["game_id"],
        "href": f"/parties/{record['game_id']}",
        "win": bool(stats["win"]),
        "champion": champions.name(me["championId"]),
        "portrait": champions.image(me["championId"]),
        "role": ROLE_LABELS.get(roles.get(pid), None),
        "opponent": champions.name(opponent["championId"]) if opponent else None,
        "kda": f"{stats['kills']} / {stats['deaths']} / {stats['assists']}",
        "duration": clock(record["duration_s"] or game.get("gameDuration", 0)),
        "queue": client_config.GAME_QUEUE_NAMES.get(record["queue_id"], str(record["queue_id"])),
        "date": date_fr(ended),
        "ago": ago(ended, now),
        "lp": (
            f"{signed(rank['lp_delta'], 0)} LP" if rank and rank["lp_delta"] is not None else None
        ),
        "impact": f"{_pts(impact)} pts" if impact is not None else None,
    }


def games_view(repo: CoachingRepository, champions: Champions, now: datetime) -> dict:
    """La liste des parties capturées, de la plus récente à la plus ancienne. Une partie au brut
    illisible est passée : elle ne doit pas masquer les autres."""
    rows = []
    for record in repo.recent_games(client_config.PARTIES_LIMIT):
        try:
            rows.append(_row(repo, record, champions, now))
        except (KeyError, TypeError, ValueError):
            continue
    wins = sum(r["win"] for r in rows)
    return {
        "empty": not rows,
        "rows": rows,
        "summary": f"{plural(len(rows), 'partie')} capturée{'s' if len(rows) > 1 else ''} · "
        f"{wins} V · {len(rows) - wins} D",
    }


# ---------- page d'une partie ----------


def _index_events(timeline: dict) -> Dict[Tuple[int, str], List[dict]]:
    index: Dict[Tuple[int, str], List[dict]] = defaultdict(list)
    for frame in timeline["frames"]:
        for event in frame["events"]:
            try:
                index[(event["timestamp"], event_kind(event))].append(event)
            except KeyError:  # événement non suivi (achat d'objet, niveau…)
                continue
    return index


def _describe(
    kind: str, event: dict, pid: int, teams: Dict[int, int], name
) -> Tuple[str, str, str]:
    """(libellé, qui, libellé court) de l'événement du point de vue de l'équipe du joueur."""

    def names(ids) -> str:
        return ", ".join("toi" if i == pid else name(i) for i in ids if i in teams)

    mine = teams[pid]
    involved = [event.get("killerId", 0)] + list(event.get("assistingParticipantIds", []))
    if kind == "kill":
        victim, killer = event["victimId"], event.get("killerId", 0)
        assists = event.get("assistingParticipantIds", [])
        if victim == pid:
            solo = killer in teams and not assists
            who = names([killer] + list(assists))
            return ("Mort solo" if solo else "Mort"), (f"tué par {who}" if who else ""), "Mort"
        if teams.get(victim) == mine:
            return f"Mort de {name(victim)}", names([killer]), "Mort"
        return f"Kill sur {name(victim)}", names([killer] + list(assists)), "Kill"
    won = scoring_team(event, teams) == mine
    if kind in TAKEN:
        label = TAKEN[kind].capitalize() if won else LOST[kind]
    elif kind == "grubs":
        label = f"Larves {'prises' if won else 'perdues'}"
    else:
        label = f"{LABELS[kind].capitalize()} {'pris' if won else 'perdu'}"
    return label, (names(involved) if won else ""), SHORT.get(kind, LABELS[kind].capitalize())


def _events(
    rows: List[dict], timeline: dict, game: dict, pid: int, champions: Champions
) -> List[dict]:
    """Les événements de la partie avec leur ΔP du point de vue de l'équipe du joueur, par ordre
    chronologique. Un kill compte par la ligne de sa victime, un objectif par celles de l'équipe qui
    le prend (les autres lignes en sont le partage entre joueurs)."""
    players = {p["participantId"]: p for p in game["participants"]}
    teams = {i: p["teamId"] for i, p in players.items()}
    index = _index_events(timeline)

    def name(participant_id: int) -> str:
        return champions.name(players[participant_id]["championId"])

    groups: Dict[Tuple[int, str], List[dict]] = defaultdict(list)
    for row in rows:
        kind = "kill" if row["event_type"] in KILL_TYPES else row["event_type"]
        groups[(row["event_time_ms"], kind)].append(row)
    events = []
    for (ts, kind), group in sorted(groups.items()):
        candidates = index.get((ts, kind), [])
        victims = {r["participant_id"] for r in group if r["event_type"] in DEATHS}
        event = next((e for e in candidates if e.get("victimId") in victims), None) or (
            candidates[0] if candidates else None
        )
        if event is None:
            continue
        primary = [r for r in group if r["event_type"] in DEATHS] if kind == "kill" else group
        delta = sum(
            (1 if teams[r["participant_id"]] == teams[pid] else -1) * r["delta_p"] for r in primary
        )
        mine = [r for r in group if r["participant_id"] == pid]
        label, who, short = _describe(kind, event, pid, teams, name)
        events.append(
            {
                "ts": ts,
                "time": clock(ts / 1000),
                "kind": kind,
                "label": label,
                "who": who,
                "short": short,
                "delta": delta,
                "delta_text": _pts(delta),
                "color": COST_COLOR if delta < 0 else KIND_COLORS[kind],
                "mine": bool(mine),
                "mine_delta": sum(r["delta_p"] for r in mine),
            }
        )
    return events


def _curve_at(points: List[Tuple[float, float]], minute: float) -> float:
    """Win chance (0 à 100) de la courbe à `minute`, par interpolation entre deux images."""
    if minute <= points[0][0]:
        return points[0][1] * 100
    for (m0, p0), (m1, p1) in zip(points, points[1:]):
        if m0 <= minute <= m1:
            return (p0 + (p1 - p0) * ((minute - m0) / ((m1 - m0) or 1))) * 100
    return points[-1][1] * 100


def _curve_chart(points: List[Tuple[float, float]], events: List[dict]) -> Markup:
    cfg = client_config
    top = sorted(events, key=lambda e: -abs(e["delta"]))[: cfg.GAME_MARKS]
    end = max(points[-1][0], 1.0)
    percent = [(m, p * 100) for m, p in points]
    return Markup(
        line_chart(
            [
                Series(
                    "Chance de victoire",
                    percent,
                    stops=CURVE_STOPS,
                    width=3,
                    area=True,
                    trace_ms=2600,
                    delay_ms=400,
                )
            ],
            size=cfg.GAME_CURVE_SIZE,
            margin=cfg.GAME_CURVE_MARGIN,
            x_domain=(0, end),
            y_domain=(0, 100),
            uid="partie",
            title="Chance de victoire",
            desc=f"Probabilité de victoire de ton équipe minute par minute, de {percent[0][1]:.0f} % "
            f"à {percent[-1][1]:.0f} % en fin de partie",
            x_ticks=[
                Tick(m, f"{m} min") for m in range(0, int(end) + 1, cfg.GAME_CURVE_X_STEP_MIN)
            ],
            y_ticks=[
                Tick(0, "0 %", color="oklch(0.74 0.11 55 / 0.12)"),
                Tick(50, "50 %", color="oklch(0.74 0.11 55 / 0.45)", dash="4 5"),
                Tick(100, "100 %", color="oklch(0.74 0.11 55 / 0.12)"),
            ],
            bands=[
                Band(50, 100, "oklch(0.82 0.15 165 / 0.05)"),
                Band(0, 50, "oklch(0.72 0.21 345 / 0.06)"),
            ],
            marks=[
                Mark(
                    e["ts"] / 60000,
                    _curve_at(points, e["ts"] / 60000),
                    e["color"],
                    e["short"],
                    above=e["delta"] >= 0,
                )
                for e in top
            ],
        )
    )


def game_page(
    repo: CoachingRepository,
    game_id: int,
    champions: Champions,
    model: Optional[WinModel],
    now: datetime,
    review: bool = False,
) -> Optional[dict]:
    """La page d'une partie capturée ; None si elle n'existe pas. `review` : la revue qui suit la
    partie (`/postgame`), au lieu de la partie consultée plus tard."""
    record = repo.game_record(game_id)
    if record is None:
        return None
    game = json.loads(record["game"])
    timeline = json.loads(record["timeline"]) if record["timeline"] else None
    players = {p["participantId"]: p for p in game["participants"]}
    pid = record["pid"]
    me = players[pid]
    roles = repo.game_roles(game_id)
    opponent = _opponent(players, roles, pid)
    ended = _ended(record, game)
    win = bool(me["stats"]["win"])
    prediction = repo.prediction(game_id)

    page: Dict[str, Any] = {
        "game_id": game_id,
        "review": review,
        "kicker": (
            f"Revue de partie · {ago(ended, now)}"
            if review
            else f"Partie du {date_fr(ended)} · {ago(ended, now)}"
        ),
        "win": win,
        "title": "Victoire" if win else "Défaite",
        "champion": champions.name(me["championId"]),
        "role": ROLE_LABELS.get(roles.get(pid)),
        "opponent": champions.name(opponent["championId"]) if opponent else None,
        "duration": clock(record["duration_s"] or game.get("gameDuration", 0)),
        "queue": client_config.GAME_QUEUE_NAMES.get(record["queue_id"], str(record["queue_id"])),
        "date": date_fr(ended),
        "ago": ago(ended, now),
        "predicted": (
            f"{fr(prediction['probability'] * 100, 1)} % · modèle {prediction['model_version']}"
            if prediction
            else None
        ),
        "curve": None,
        "curve_note": None,
        "impact_note": None,
        "impact": {"available": False, "costly": [], "profitable": [], "events": []},
        "lp": None,
        "axes": [],
        "findings": [],
    }
    points: List[Tuple[float, float]] = []
    if timeline is None:
        page["curve_note"] = (
            "Pas de timeline pour cette partie : la courbe et l'impact ne sont pas calculables."
        )
    elif model is None:
        page["curve_note"] = (
            "Modèle de win chance absent : lance `python -m src.winprob.retrain --force` pour l'entraîner."
        )
    else:
        points = curve_points(model, game, timeline, me["teamId"])
        if not points:
            page["curve_note"] = "Courbe indisponible pour cette partie."
    rows = repo.impact_rows(game_id)
    events = _events(rows, timeline, game, pid, champions) if rows and timeline else []
    if events:
        mine = [e for e in events if e["mine"]]
        stack = sorted(
            sorted(events, key=lambda e: -abs(e["delta"]))[: client_config.GAME_MARKS],
            key=lambda e: e["ts"],
        )
        biggest = max(abs(e["delta"]) for e in stack) or 1.0
        residual = _residual(model, game, timeline, rows, me["teamId"])
        page["impact"] = {
            "available": True,
            "events": events,
            "stack": [
                {**e, **_bar(e["delta"], biggest), "delay": 500 + i * 110}
                for i, e in enumerate(stack)
            ],
            "costly": sorted(
                (e for e in mine if e["mine_delta"] < 0), key=lambda e: e["mine_delta"]
            )[: client_config.GAME_TOP],
            "profitable": sorted(
                (e for e in mine if e["mine_delta"] > 0), key=lambda e: -e["mine_delta"]
            )[: client_config.GAME_TOP],
            "attributed": _pts(sum(e["mine_delta"] for e in mine)),
            "residual": _pts(residual) if residual is not None else None,
        }
    elif timeline is not None:
        page["impact_note"] = "Impact non calculé pour cette partie."
    if points:
        page["curve"] = _curve_chart(points, events)

    rank = repo.rank_after_game(game_id)
    if rank:
        page["lp"] = {
            "delta": signed(rank["lp_delta"], 0) if rank["lp_delta"] is not None else None,
            "gain": (rank["lp_delta"] or 0) >= 0,
            "value": abs(rank["lp_delta"] or 0),
            "rank": f"{tier_name(rank)} · {rank['lp']} LP",
        }
    for verdict in repo.game_verdicts(game_id):
        metric = METRICS[verdict["metric"]]
        page["axes"].append(
            {
                "held": verdict["held"],
                "text": (
                    f"Axe « {metric.label} » : {'tenu' if verdict['held'] else 'non tenu'} "
                    f"({format_value(verdict['metric'], verdict['value'])}, cible "
                    f"{'≥' if metric.sense > 0 else '≤'} "
                    f"{format_value(verdict['metric'], verdict['target'])})"
                ),
            }
        )
    for finding in repo.game_findings(game_id):
        norm, objective = finding_reference(finding)
        page["findings"].append(
            {
                "label": METRICS[finding["metric"]].label,
                "value": format_value(finding["metric"], finding["value"]),
                "reference": " · ".join(
                    part
                    for part in (
                        f"norme {norm}" if norm else "",
                        f"obj. {objective}" if objective else "",
                    )
                    if part
                )
                or "—",
                "good": finding["z"] >= 0,
            }
        )
    return page


def _bar(delta: float, biggest: float) -> dict:
    """Position (en %) de la barre divergente d'un événement, la plus grande remplissant la demi-largeur."""
    left, width = diverging(delta, biggest)
    return {"left": round(left, 1), "width": round(width, 1)}


def _residual(
    model: Optional[WinModel], game: dict, timeline: dict, rows: List[dict], team: int
) -> Optional[float]:
    """Ce que le temps, le farm et les niveaux ont changé hors des événements, pour l'équipe du joueur
    (non attribué). Recalculé avec le modèle qui a produit les lignes stockées : d'une autre version,
    il ne leur correspondrait plus et n'est pas affiché."""
    if model is None or rows[0]["model_version"] != model.version:
        return None
    summary = impacts(model, game, timeline)["teams"].get(team)
    return summary["unattributed"] if summary else None
