"""Accueil du coaching (SPEC-21 §4.4, §4.10, tâche 71) : axes de travail, derniers constats, rang,
dernières parties et bilan du rôle.

Lecture de la base seulement ; fixer ou clore un axe passe par `goals.set_goal` et
`CoachingRepository.set_goal_status` sur la connexion d'écriture de `db.writable()` (route de
`app.py`). Les axes forment un fragment à part (`axes_view`) que le client recharge après chaque écriture.
"""

import json
from datetime import datetime
from typing import Dict, List, Optional

from markupsafe import Markup

from ..coaching.goals import next_proposal
from ..coaching.grid import GRID
from ..coaching.metrics import METRICS, format_value
from ..coaching.progression import profile
from ..config_client import client_config
from ..config_constants import coaching_config
from ..repositories.coaching import CoachingRepository
from .charts import SparkLine, diverging, sparkline
from .data import ago, default_role, finding_reference, parse_utc, plural, rank_view, scale_of
from .draft_view import ROLE_LABELS, Champions, fr, signed

GOAL_HUES = (290, 230)  # violet puis bleu : un axe par couleur
ORIGINS = ("proposed", "player")
ORIGIN_LABELS = {"proposed": "proposé par le coach", "player": "fixé par toi"}


def main_role(repo: CoachingRepository) -> Optional[str]:
    """Le poste le plus joué parmi les parties analysées, None sans partie analysée."""
    roles = repo.player_roles()
    return default_role(roles) if roles else None


def _goal_card(repo: CoachingRepository, goal: dict, index: int) -> dict:
    metric = METRICS[goal["metric"]]
    verdicts = repo.verdicts(
        goal["id"], coaching_config.GOAL_WINDOW
    )  # du plus récent au plus ancien
    judged = len(repo.verdicts(goal["id"], 10**6))
    marks = [bool(v) for v in reversed(verdicts)]
    marks += [None] * (coaching_config.GOAL_WINDOW - len(marks))  # pas encore jugées
    held = sum(verdicts)
    return {
        "id": goal["id"],
        "kind": "goal",
        "hue": GOAL_HUES[index % len(GOAL_HUES)],
        "tag": f"Axe {index + 1} · {ORIGIN_LABELS.get(goal['origin'], goal['origin'])}",
        "label": metric.label,
        "role": ROLE_LABELS.get(goal["role"], goal["role"]),
        "target": f"{'≥' if metric.sense > 0 else '≤'} {format_value(goal['metric'], goal['target'])}",
        "marks": marks,
        "hold": (
            f"Tenu {held} fois sur les {len(verdicts)} dernières · acquis à "
            f"{coaching_config.GOAL_HOLD} sur {coaching_config.GOAL_WINDOW}"
            if verdicts
            else "Pas encore jugé : le verdict tombe après ta prochaine partie à ce poste"
        ),
        "since": f"Actif depuis {plural(judged, 'partie')}" if judged else "Fixé, pas encore jugé",
    }


def axes_view(repo: CoachingRepository, notice: Optional[str] = None) -> dict:
    """Les places d'axe : les axes actifs, puis les places libres avec la proposition du coach.

    `notice` : le message de la dernière écriture (« déjà un axe actif »…), affiché au-dessus.
    """
    role = main_role(repo)
    goals = repo.goals()
    cards: List[dict] = [_goal_card(repo, goal, i) for i, goal in enumerate(goals)]
    taken = {goal["metric"] for goal in goals}
    proposal = next_proposal(repo, role) if role else None
    options = [
        {"metric": m, "label": METRICS[m].label}
        for m in (GRID[role] if role else ())
        if m not in taken
    ]
    for slot in range(len(goals), coaching_config.MAX_ACTIVE_GOALS):
        first = slot == len(goals)
        cards.append(
            {
                "kind": "free",
                "hue": GOAL_HUES[slot % len(GOAL_HUES)],
                "proposal": (
                    {"metric": proposal, "label": METRICS[proposal].label}
                    if proposal and first
                    else None
                ),
            }
        )
    active = len(goals)
    return {
        "role": role,
        "role_label": ROLE_LABELS.get(role),
        "cards": cards,
        "options": options,
        "note": (
            f"{plural(active, 'axe')} actif{'s' if active > 1 else ''} sur "
            f"{coaching_config.MAX_ACTIVE_GOALS}"
            + (
                " · clos-en un pour en fixer un autre"
                if active >= coaching_config.MAX_ACTIVE_GOALS
                else ""
            )
        ),
        "notice": notice,
        "minimum": coaching_config.MIN_TREND_SAMPLE,
    }


def _findings(repo: CoachingRepository, champions: Champions, now: datetime) -> Optional[dict]:
    """Le tableau des derniers constats : ceux de la dernière partie analysée qui en a."""
    latest = repo.latest_findings()
    if not latest:
        return None
    record = repo.game_record(latest["game_id"])
    rows = []
    for i, row in enumerate(latest["rows"]):
        metric = row["metric"]
        left, width = diverging(row["z"], client_config.HOME_FINDING_Z_FULL)
        norm, objective = finding_reference(row)
        reference = (norm or "—") + (f" · obj. {objective}" if objective else "")
        rows.append(
            {
                "label": METRICS[metric].label,
                "value": format_value(metric, row["value"]),
                "reference": reference,
                "z": f"{signed(row['z'], 1)} σ",
                "good": row["z"] >= 0,
                "left": round(left, 1),
                "width": round(width, 1),
                "delay": 480 + i * 70,
            }
        )
    game = json.loads(record["game"])
    me = next(p for p in game["participants"] if p["participantId"] == record["pid"])
    return {
        "game_id": latest["game_id"],
        "href": f"/parties/{latest['game_id']}",
        "win": bool(me["stats"]["win"]),
        "ended": ago(parse_utc(record["created"]), now),
        "champion": champions.name(me["championId"]),
        "rows": rows,
    }


def _last_games(repo: CoachingRepository, champions: Champions) -> dict:
    results = []
    for record in repo.recent_games(client_config.HOME_LAST_GAMES):
        try:
            game = json.loads(record["game"])
            me = next(p for p in game["participants"] if p["participantId"] == record["pid"])
            results.append(
                {
                    "href": f"/parties/{record['game_id']}",
                    "win": bool(me["stats"]["win"]),
                    "champion": champions.name(me["championId"]),
                    "portrait": champions.image(me["championId"]),
                }
            )
        except (KeyError, TypeError, ValueError, StopIteration):
            continue
    wins = sum(r["win"] for r in results)
    return {
        "games": results,
        "title": f"{plural(len(results), 'dernière')} parties · {wins} V · {len(results) - wins} D",
    }


def _rank_card(history: List[dict]) -> Optional[dict]:
    """La carte de rang de la colonne : la file solo/duo, à défaut la flexible ; None sans photo."""
    view = rank_view(history)
    card = next((c for c in view["cards"] if not c["empty"]), None)
    if card is None:
        return None
    photos = [s for s in history if s["queue"] == card["key"]]
    since = parse_utc(photos[-1]["captured"])
    recent = [
        scale_of(p)
        for p in photos
        if (since - parse_utc(p["captured"])).days < client_config.RANK_DELTA_DAYS
    ]
    spark = (
        Markup(
            sparkline(
                [SparkLine(recent, color="oklch(0.8 0.1 165)", width=1.8)],
                size=client_config.RANK_SPARK_SIZE,
                uid="spark-accueil",
                title=f"Rang sur {client_config.RANK_DELTA_DAYS} jours",
                trace_ms=1800,
                delay_ms=500,
            )
        )
        if len(recent) >= client_config.RANK_MIN_PHOTOS
        else None
    )
    return {**card, "spark": spark}


def _review(repo: CoachingRepository, role: Optional[str]) -> Optional[dict]:
    """Bilan du rôle : les deux plus fortes et les deux plus faibles métriques face à la norme."""
    if role is None:
        return None
    means = profile(repo.player_history(role), role)  # du plus faible au plus fort
    describe = lambda rows: [
        {"label": METRICS[m].label, "z": f"{signed(z, 1)} σ"} for m, z, _ in rows
    ]
    return {
        "role": role,
        "label": ROLE_LABELS[role],
        "strong": describe([r for r in means[::-1] if r[1] > 0][: client_config.HOME_STRENGTHS]),
        "weak": describe([r for r in means if r[1] < 0][: client_config.HOME_STRENGTHS]),
        "known": bool(means),
    }


def home_view(
    repo: CoachingRepository, champions: Champions, now: datetime, notice: Optional[str] = None
) -> dict:
    """L'accueil du coaching."""
    role = main_role(repo)
    count, latest = repo.capture_stats()
    history = repo.rank_history()
    return {
        "kicker": f"Coaching · rôle principal {ROLE_LABELS[role]}" if role else "Coaching",
        "status": (
            f"{plural(count, 'partie')} capturée{'s' if count > 1 else ''} · dernière "
            f"{ago(parse_utc(latest), now)}"
            if count
            else "Aucune partie capturée"
        ),
        "fresh": bool(count),
        "axes": axes_view(repo, notice),
        "findings": _findings(repo, champions, now),
        "last": _last_games(repo, champions),
        "rank": _rank_card(history),
        "review": _review(repo, role),
    }


def empty_home() -> Dict[str, object]:
    """L'accueil d'une base non migrée : aucune table, rien à lire."""
    return {
        "kicker": "Coaching",
        "status": "Base non migrée : lance `python -m alembic upgrade head`",
        "fresh": False,
        "axes": None,
        "findings": None,
        "last": {"games": [], "title": "Aucune partie"},
        "rank": None,
        "review": None,
    }
