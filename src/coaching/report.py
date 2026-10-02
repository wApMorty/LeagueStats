"""Sorties console : rapport de fin de partie et bilan (SPEC-19 §6.1, §7.4, tâches 35, 38)."""

from typing import Callable, List, Optional

from ..config_constants import coaching_config
from ..repositories.coaching import CoachingRepository
from ..winprob.report import impact_review
from .findings import Finding, GameAnalysis
from .goals import describe, propose
from .grid import Reference
from .metrics import METRICS, format_value
from .progression import lp_changes, patterns, profile, trends

LABEL_WIDTH = 36


def _ref(metric: str, ref: Optional[Reference], name: str) -> Optional[str]:
    return f"{name} {format_value(metric, ref.mean)}" if ref else None


def finding_line(finding: Finding) -> str:
    tag = "[ALERTE]" if finding.z < 0 else "[OK]    "
    label = f"{METRICS[finding.metric].label} : {format_value(finding.metric, finding.value)}"
    refs = [
        _ref(finding.metric, finding.norm, "norme"),
        _ref(finding.metric, finding.objective, "objectif"),
    ]
    refs_text = ", ".join(r for r in refs if r)
    return f"{tag} {label:<{LABEL_WIDTH}} ({refs_text})  z {finding.z:+.1f}"


def game_report(
    analysis: GameAnalysis,
    name_of: Callable[[int], str],
    predicted: Optional[float] = None,
    duel: Optional[float] = None,
) -> List[str]:
    """Rapport de fin de partie (maquette §6.1)."""
    queue = coaching_config.QUEUE_NAMES.get(analysis.queue_id, str(analysis.queue_id))
    opponent = (
        f" vs {name_of(analysis.opponent_champion_id)}" if analysis.opponent_champion_id else ""
    )
    lines = [
        f"[DATA] Fin de partie : {name_of(analysis.champion_id)} {analysis.role or '?'}{opponent}, "
        f"{'victoire' if analysis.win else 'défaite'} ({analysis.duration_s // 60} min, {queue})"
    ]
    context = []
    if predicted is not None:
        context.append(f"{predicted:.0%} prédit")
    if duel is not None:
        side = "favorable" if duel > 0 else "défavorable"
        gold = analysis.values.get("gold_diff_15")
        lane = f", écart d'or @15 {gold:+.0f}" if gold is not None else ""
        context.append(f"duel {side} ({duel:+.1f} pts){lane}")
    if context:
        lines.append(f"  Draft : {', '.join(context)}")
    if analysis.role is None:
        lines.append("[INFO] Poste inconnu pour cette partie : aucun constat")
    elif not (analysis.negatives or analysis.positives):
        if analysis.norm_n < coaching_config.MIN_NORM_SAMPLE:
            lines.append(
                f"[INFO] Norme en construction ({analysis.norm_n}/"
                f"{coaching_config.MIN_NORM_SAMPLE} parties en {analysis.role}) : aucun verdict"
            )
        else:
            lines.append("[INFO] Aucun écart marquant face à la norme")
    lines += [finding_line(f) for f in analysis.negatives + analysis.positives]
    return lines


def review(db) -> List[str]:
    """Bilan : LP, progrès et reculs, schémas, profil, axes (§7.4)."""
    repo = CoachingRepository(db)
    roles = repo.player_roles()
    if not roles:
        return ["[INFO] Bilan : aucune partie analysée pour l'instant"]
    role = max(roles, key=roles.get)
    history = repo.player_history(role)
    lines = [
        "=" * 80,
        f"BILAN DU COACH DE GAMEPLAY - {sum(roles.values())} parties analysées, "
        f"poste principal : {role} ({roles[role]})",
        "=" * 80,
    ]

    changes = lp_changes(repo.rank_snapshots())
    for queue, (first, last, delta) in changes.items():
        lines.append(
            f"  LP {queue} : {first[1]} {first[2] or ''} {first[3]} -> "
            f"{last[1]} {last[2] or ''} {last[3]} ({delta:+d} LP depuis le {first[0][:10]})"
        )

    moving = [t for t in trends(history, role) if t.verdict != "stable"]
    lines.append("\n  Progrès et reculs (valeur brute, dernières parties contre celles d'avant) :")
    lines += [
        f"    {t.verdict:<8} {METRICS[t.metric].label} : "
        f"{format_value(t.metric, t.before)} -> {format_value(t.metric, t.after)}"
        for t in moving
    ] or ["    rien de net pour l'instant (écarts dans le bruit, ou trop peu de parties)"]

    found = patterns(history, role)
    lines.append(
        f"\n  Schémas sur les {coaching_config.RECURRENCE_WINDOW} dernières parties (face à la norme) :"
    )
    lines += [
        f"    {'faiblesse' if p.polarity == 'negative' else 'force':<9} "
        f"{METRICS[p.metric].label} : {p.count}/{p.games} parties"
        for p in found
    ] or ["    aucun schéma significatif"]

    means = profile(history, role)
    if means:
        lines.append("\n  Profil moyen face à la norme (z) :")
        lines += [
            f"    {METRICS[metric].label:<{LABEL_WIDTH}} {z:+.1f}  ({n} parties)"
            for metric, z, n in means[:3] + [m for m in means[-3:] if m not in means[:3]]
        ]
    else:
        lines.append(
            f"\n  Profil : norme en construction (il faut {coaching_config.MIN_NORM_SAMPLE} "
            "parties par poste)"
        )

    lines += impact_review(repo.player_impact(coaching_config.RECURRENCE_WINDOW))

    proposal = propose(repo, role)
    lines.append("\n  Axes de travail :")
    lines += [f"    {describe(goal)}" for goal in repo.goals()] or ["    aucun axe actif"]
    if proposal:
        lines.append(f"  {proposal}")
    lines.append("=" * 80)
    return lines
