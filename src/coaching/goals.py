"""Axes de travail (SPEC-19 §7.3, tâche 37).

Un ou deux axes actifs. Le joueur en fixe un (`axe <métrique>` dans le Live
Coach), sinon le schéma négatif le plus net en devient un. La cible est la
norme du moment : faire au moins aussi bien que ses pairs. Chaque partie
donne un verdict (tenu ou non) ; l'axe est acquis quand il tient GOAL_HOLD
parties sur les GOAL_WINDOW dernières, et le suivant est proposé.
"""

from typing import List, Optional

from ..config_constants import coaching_config
from ..repositories.coaching import CoachingRepository
from .findings import GameAnalysis
from .metrics import METRICS, format_value
from .progression import patterns


def _held(metric: str, value: float, target: float) -> bool:
    return METRICS[metric].sense * (value - target) >= 0


def _target(history: List[dict], metric: str) -> Optional[float]:
    """Norme la plus récente de la métrique, à défaut la moyenne du joueur."""
    rows = [row for row in history if row["metric"] == metric]
    for row in rows:
        if row["norm_mean"] is not None and (row["norm_n"] or 0) >= coaching_config.MIN_NORM_SAMPLE:
            return row["norm_mean"]
    return sum(row["value"] for row in rows) / len(rows) if rows else None


def describe(goal: dict) -> str:
    sign = "≥" if METRICS[goal["metric"]].sense > 0 else "≤"
    return (
        f"« {METRICS[goal['metric']].label} » ({goal['role']}, cible {sign} "
        f"{format_value(goal['metric'], goal['target'])})"
    )


def set_goal(repo: CoachingRepository, metric: str, role: str, origin: str = "player") -> str:
    """Active un axe sur la métrique ; le plus ancien cède sa place au-delà du maximum."""
    if metric not in METRICS:
        return f"[AXE] Métrique inconnue : '{metric}'. Valeurs : {', '.join(METRICS)}"
    target = _target(repo.player_history(role), metric)
    if target is None:
        return f"[AXE] Aucune partie analysée en {role} pour fixer la cible de {metric}"
    active = repo.goals()
    if any(goal["metric"] == metric and goal["role"] == role for goal in active):
        return f"[AXE] {METRICS[metric].label} est déjà un axe actif"
    for goal in active[: max(0, len(active) - coaching_config.MAX_ACTIVE_GOALS + 1)]:
        repo.set_goal_status(goal["id"], "dropped")
    repo.insert_goal(metric, role, target, origin)
    return f"[AXE] Nouvel axe de travail : {describe(repo.goals()[-1])}"


def propose(repo: CoachingRepository, role: str) -> Optional[str]:
    """Active le schéma négatif le plus net quand une place d'axe est libre."""
    active = repo.goals()
    if len(active) >= coaching_config.MAX_ACTIVE_GOALS:
        return None
    taken = {goal["metric"] for goal in active}
    for pattern in patterns(repo.player_history(role), role):
        if pattern.polarity == "negative" and pattern.metric not in taken:
            return set_goal(repo, pattern.metric, role, origin="proposed")
    return None


def judge(repo: CoachingRepository, analysis: GameAnalysis) -> List[str]:
    """Verdict de chaque axe actif sur la partie analysée, et acquisition éventuelle."""
    lines = []
    for goal in repo.goals():
        value = analysis.values.get(goal["metric"])
        if goal["role"] != analysis.role or value is None:
            continue
        held = _held(goal["metric"], value, goal["target"])
        repo.insert_verdict(goal["id"], analysis.game_id, value, held)
        recent = repo.verdicts(goal["id"], coaching_config.GOAL_WINDOW)
        lines.append(
            f"[{'OK' if held else 'ALERTE'}] Axe {describe(goal)} : "
            f"{format_value(goal['metric'], value)}, {'tenu' if held else 'non tenu'} "
            f"({sum(recent)}/{len(recent)} sur les dernières parties)"
        )
        if len(recent) >= coaching_config.GOAL_WINDOW and sum(recent) >= coaching_config.GOAL_HOLD:
            repo.set_goal_status(goal["id"], "acquired")
            lines.append(f"[OK] Axe acquis : {METRICS[goal['metric']].label} !")
    return lines


def draft_reminder(db) -> List[str]:
    """Une ligne par axe actif, pour l'écran de fin de draft."""
    repo = CoachingRepository(db)
    lines = []
    for goal in repo.goals():
        recent = repo.verdicts(goal["id"], coaching_config.GOAL_WINDOW)
        record = f", tenu {sum(recent)}/{len(recent)}" if recent else ""
        lines.append(f"[AXE] Axe de travail {describe(goal)}{record}")
    return lines
