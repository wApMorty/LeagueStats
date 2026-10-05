"""Données des écrans du coaching (SPEC-21 §4.4, §4.10) : lectures de la base devenues ce que les
gabarits dessinent.

Fonctions pures : des lignes de repository entrent, un dictionnaire prêt pour Jinja sort (avec les
graphiques de `charts.py` déjà rendus). Aucune requête, aucun LCU, aucune horloge cachée : un écran
est testable avec des listes de dictionnaires. Les valeurs de réglage sont dans `config_client.py`.
"""

from datetime import datetime, timezone
from statistics import mean
from typing import Dict, List, Optional, Sequence, Tuple

from markupsafe import Markup

from ..analysis.calibration import brier_score, calibration_buckets, fetch_labeled_predictions
from ..coaching.grid import GRID
from ..coaching.metrics import METRICS, format_value
from ..coaching.progression import DIVISIONS, TIERS, lp_scale, patterns, trends
from ..config_client import client_config
from ..config_constants import analysis_config, coaching_config
from .charts import (
    Band,
    Series,
    SparkLine,
    Tick,
    bar_chart,
    line_chart,
    reliability_chart,
    sparkline,
)
from .draft_view import ROLE_LABELS, fr, signed

FR_MONTHS = (
    "janv.",
    "févr.",
    "mars",
    "avr.",
    "mai",
    "juin",
    "juil.",
    "août",
    "sept.",
    "oct.",
    "nov.",
    "déc.",
)
MASTER_INDEX = TIERS.index("MASTER")


def parse_utc(text: str) -> datetime:
    """Horodatage SQLite (`YYYY-MM-DD HH:MM:SS`, UTC) en datetime."""
    return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def date_fr(moment: datetime) -> str:
    return f"{moment.day} {FR_MONTHS[moment.month - 1]}"


def ago(moment: datetime, now: datetime) -> str:
    """« il y a 2 h » : l'âge d'un événement, à la minute, à l'heure, puis au jour près."""
    seconds = max(0, int((now - moment).total_seconds()))
    if seconds < 60:
        return "à l'instant"
    if seconds < 3600:
        return f"il y a {seconds // 60} min"
    if seconds < 86400:
        return f"il y a {seconds // 3600} h"
    return f"il y a {seconds // 86400} j"


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count > 1 else ''}"


def thousands(value: float) -> str:
    """Entier à la française : espace fine insécable entre les milliers (« 19 265 »)."""
    return f"{round(value):,}".replace(",", "\u202f")


# ---------- rang ----------

# Habillage des deux files (jetons du thème) : dégradé de la courbe, couleur, teinte de la carte.
QUEUE_STYLE = {
    "RANKED_SOLO_5x5": {
        "stops": ("var(--blue)", "var(--mint)", "oklch(0.88 0.16 130)"),
        "color": "var(--mint)",
        "hue": 160,
        "spin": 120,
    },
    "RANKED_FLEX_SR": {
        "stops": ("var(--violet)", "var(--magenta)"),
        "color": "var(--violet)",
        "hue": 290,
        "spin": -120,
    },
}


def tier_name(snapshot: dict) -> str:
    """« Émeraude II » ; sans division à partir de Maître."""
    name = client_config.TIER_NAMES.get(snapshot["tier"], snapshot["tier"].title())
    master = snapshot["tier"] in TIERS and TIERS.index(snapshot["tier"]) >= MASTER_INDEX
    return f"{name} {snapshot['division']}" if snapshot.get("division") and not master else name


def scale_of(snapshot: dict) -> int:
    return lp_scale(snapshot["tier"], snapshot["division"], snapshot["lp"])


def scale_label(value: int) -> str:
    """Libellé d'une graduation de l'échelle continue (100 LP par division, 400 par palier).

    ponytail : au-delà de 400 LP en Maître+, l'échelle déborde sur le palier suivant et la graduation
    est fausse ; à reprendre quand @pj35 y arrive.
    """
    index = min(value // 400, len(TIERS) - 1)
    within = value - index * 400
    name = client_config.TIER_NAMES[TIERS[index]]
    if index >= MASTER_INDEX:
        return f"{name} {within} LP" if within else name
    return f"{name} {DIVISIONS[within // 100]}"


def _distinct(points: List[tuple]) -> List[tuple]:
    """Retire une photo identique à celle d'avant et à celle d'après : un plateau ne change pas la
    courbe, et chaque démarrage du Live Coach en prend une."""
    return [
        p
        for i, p in enumerate(points)
        if not (0 < i < len(points) - 1 and points[i - 1][1] == p[1] == points[i + 1][1])
    ]


def _axis(points: Sequence[tuple]) -> Tuple[Tuple[float, float], List[Tick], List[Band]]:
    """Domaine vertical arrondi à la centaine, graduations par division, bandes par palier."""
    values = [v for _, v in points]
    low = max(0, (min(values) // 100) * 100 - 100)
    high = ((max(values) + 99) // 100) * 100 + 100
    ticks, bands = [], []
    for value in range(low, high + 1, 100):
        index = min(value // 400, len(TIERS) - 1)
        hue = client_config.TIER_HUES[TIERS[index]]
        edge = value % 400 == 0
        ticks.append(
            Tick(
                value,
                scale_label(value),
                color="oklch(0.86 0.13 85 / 0.6)" if edge else f"oklch(0.78 0.12 {hue} / 0.16)",
                label_color=f"oklch(0.8 0.12 {hue})",
            )
        )
    for index in range(low // 400, high // 400 + 1):
        hue = client_config.TIER_HUES[TIERS[min(index, len(TIERS) - 1)]]
        bands.append(Band(index * 400, (index + 1) * 400, f"oklch(0.76 0.13 {hue} / 0.07)"))
    return (low, high), ticks, bands


def _queue_card(queue: str, photos: List[dict]) -> dict:
    style = QUEUE_STYLE[queue]
    card = {
        "key": queue,
        "name": client_config.RANK_QUEUE_NAMES[queue],
        "hue": style["hue"],
        "color": style["color"],
        "stops": style["stops"],
        "spin": style["spin"],
        "photos": len(photos),
        "empty": not photos,
        "curve": len(photos) >= client_config.RANK_MIN_PHOTOS,
    }
    if not photos:
        return card
    last = photos[-1]
    card.update(tier=tier_name(last), lp=last["lp"])
    wins, losses = last.get("wins"), last.get("losses")
    if wins is not None and losses is not None:
        card["stats"] = [
            (f"{wins} V", "victoires"),
            (f"{losses} D", "défaites"),
            (
                f"{round(100 * wins / (wins + losses))} %" if wins + losses else "—",
                "taux de victoire",
            ),
        ]
    since = parse_utc(last["captured"])
    window = [
        p for p in photos if (since - parse_utc(p["captured"])).days < client_config.RANK_DELTA_DAYS
    ]
    first = window[0]
    delta = scale_of(last) - scale_of(first)
    when = (
        f"sur {client_config.RANK_DELTA_DAYS} jours"
        if first is not photos[0]
        else f"depuis le {date_fr(parse_utc(first['captured']))}"
    )
    note = [
        f"{signed(delta, 0)} LP {when}" if first is not last else None,
        plural(len(photos), "photo"),
    ]
    card["note"] = " · ".join(n for n in note if n)
    return card


def rank_view(history: List[dict]) -> dict:
    """L'écran Rang : courbes par file, histogramme des LP par partie, cartes par file.

    `history` : `CoachingRepository.rank_history()`. Une file sous `RANK_MIN_PHOTOS` photos n'a pas de
    courbe (l'ignorance reste visible) ; la courbe omet les photos qui répètent leur voisine.
    """
    cfg = client_config
    by_queue = {q: [s for s in history if s["queue"] == q] for q in cfg.RANK_QUEUE_NAMES}
    cards = [_queue_card(queue, photos) for queue, photos in by_queue.items()]
    view = {
        "empty": not history,
        "kicker": plural(len(history), "photo") + " de rang",
        "cards": cards,
        "chart": None,
        "bars": None,
    }
    drawn = {
        queue: _distinct([(parse_utc(s["captured"]).timestamp(), scale_of(s)) for s in photos])
        for queue, photos in by_queue.items()
        if len(photos) >= cfg.RANK_MIN_PHOTOS
    }
    if drawn:
        every = [p for points in drawn.values() for p in points]
        start, end = min(x for x, _ in every), max(x for x, _ in every)
        y_domain, y_ticks, bands = _axis(every)
        labelled = next(iter(drawn))  # la file principale porte l'étiquette du dernier point
        series = [
            Series(
                cfg.RANK_QUEUE_NAMES[queue],
                points,
                stops=QUEUE_STYLE[queue]["stops"],
                width=2.8 if queue == labelled else 2.2,
                area=queue == labelled,
                dots=True,
                trace_ms=2400 if queue == labelled else 2600,
                delay_ms=300 if queue == labelled else 500,
                end_label=(
                    f"{tier_name(by_queue[queue][-1])} · {by_queue[queue][-1]['lp']} LP"
                    if queue == labelled
                    else ""
                ),
            )
            for queue, points in drawn.items()
        ]
        steps = cfg.RANK_X_TICKS - 1
        x_ticks = [
            Tick(
                start + (end - start) * i / steps,
                date_fr(datetime.fromtimestamp(start + (end - start) * i / steps, timezone.utc)),
            )
            for i in range(cfg.RANK_X_TICKS)
        ]
        view["chart"] = Markup(
            line_chart(
                series,
                size=cfg.RANK_CHART_SIZE,
                x_domain=(start, end if end > start else start + 1),
                y_domain=y_domain,
                uid="rang",
                title="Courbe de classement",
                desc="Rang sur une échelle continue, 100 LP par division, "
                + ", ".join(f"{s.name} : {len(by_queue[q])} photos" for s, q in zip(series, drawn)),
                x_ticks=x_ticks,
                y_ticks=y_ticks,
                bands=bands,
            )
        )
    solo = [
        s
        for s in by_queue.get("RANKED_SOLO_5x5", [])
        if s["lp_delta"] is not None and s["game_id"] is not None
    ][-cfg.RANK_BARS :]
    if solo:
        deltas = [s["lp_delta"] for s in solo]
        view["bars"] = {
            "title": f"LP par partie · {plural(len(solo), 'dernière')} en solo/duo",
            "mean": f"Moyenne {signed(sum(deltas) / len(deltas), 1)} LP",
            "svg": Markup(
                bar_chart(
                    deltas,
                    size=cfg.RANK_BARS_SIZE,
                    uid="rang-lp",
                    title="LP par partie",
                    desc="Variation de LP de chaque partie classée solo/duo, de la plus ancienne à la plus récente",
                    labels=[f"{signed(d, 0)} LP" for d in deltas],
                )
            ),
        }
    return view


# ---------- progression ----------

ROLE_ORDER = tuple(ROLE_LABELS)  # top, jungle, middle, bottom, support
ROLE_HUES = {"top": 55, "jungle": 150, "middle": 290, "bottom": 85, "support": 230}
ROW_HUES = (165, 230, 290, 345, 55, 85, 200, 120, 260, 20, 180, 310)
VERDICT_LABELS = {
    "progrès": ("up", "en progrès"),
    "recul": ("down", "en recul"),
    "stable": ("flat", "stable"),
}


def rolling(values: Sequence[float], window: int) -> List[float]:
    """Moyenne glissante : chaque point moyenne les `window` valeurs qui le précèdent (lui compris)."""
    return [mean(values[max(0, i + 1 - window) : i + 1]) for i in range(len(values))]


def default_role(roles: Dict[str, int]) -> str:
    """Le poste le plus joué (le premier de l'ordre des postes à égalité), Top sans partie."""
    played = {role: n for role, n in roles.items() if role in ROLE_ORDER and n}
    return max(ROLE_ORDER, key=lambda r: played.get(r, 0)) if played else ROLE_ORDER[0]


def _reference(history: Sequence[dict], metric: str) -> Tuple[str, str]:
    """(norme, objectif) les plus récents de la métrique, « — » quand il n'y en a pas : une norme
    sous `MIN_NORM_SAMPLE` parties est en construction, et la plupart des métriques n'ont pas d'objectif.
    """
    norm = next(
        (
            r["norm_mean"]
            for r in history
            if r["norm_mean"] is not None and (r["norm_n"] or 0) >= coaching_config.MIN_NORM_SAMPLE
        ),
        None,
    )
    objective = next(
        (r["objective_value"] for r in history if r["objective_value"] is not None), None
    )
    if norm is None:
        shown = "—"
    else:
        shown = "0" if METRICS[metric].zero_sum and norm == 0 else format_value(metric, norm)
    return shown, "—" if objective is None else format_value(metric, objective)


def _verdict(trend, games: int) -> dict:
    """Le verdict de `trends()`, ou la raison de son absence (`trends()` compare deux moitiés de
    `MIN_TREND_SAMPLE` parties : il en faut donc le double)."""
    if trend is not None:
        kind, text = VERDICT_LABELS[trend.verdict]
        return {"kind": kind, "text": text}
    sample = coaching_config.MIN_TREND_SAMPLE
    if games >= 2 * sample:  # assez de parties, mais aucun écart entre les deux moitiés à comparer
        return {"kind": "none", "text": f"{games} parties, écart nul : pas de verdict"}
    needed = sample * (2 if games >= sample else 1)
    return {"kind": "none", "text": f"{games}/{needed} parties, pas de verdict"}


def _metric_row(metric: str, weight: int, series: List[dict], trend, index: int) -> dict:
    """Une ligne de la grille ; `series` : les lignes de la métrique, de la plus récente à la plus ancienne."""
    cfg, hue = client_config, ROW_HUES[index % len(ROW_HUES)]
    color = f"oklch(0.8 0.15 {hue})"
    recent = [r["value"] for r in series[: coaching_config.RECURRENCE_WINDOW]]
    chrono = series[::-1]
    norm_z = [
        r["z_norm"]
        for r in chrono
        if r["z_norm"] is not None and (r["norm_n"] or 0) >= coaching_config.MIN_NORM_SAMPLE
    ]
    objective_z = [r["z_objective"] for r in chrono if r["z_objective"] is not None]
    lines = [
        SparkLine(
            rolling(zs, cfg.PROGRESSION_SPARK_WINDOW)[-cfg.PROGRESSION_SPARK_POINTS :], c, dashed
        )
        for zs, c, dashed in ((norm_z, color, False), (objective_z, "var(--copper)", True))
        if len(zs) >= 2
    ]
    norm, objective = _reference(series, metric)
    label = METRICS[metric].label
    delay = 120 + index * 55
    return {
        "metric": metric,
        "label": label,
        "color": color,
        "weight": "●●" if weight == 2 else "●",
        "you": format_value(metric, mean(recent)) if recent else "—",
        "norm": norm,
        "objective": objective,
        "verdict": _verdict(trend, len(series)),
        "spark": Markup(
            sparkline(
                lines,
                size=cfg.PROGRESSION_SPARK_SIZE,
                uid=f"prog-{metric}",
                title=f"Tendance de {label}",
                desc="Moyenne glissante de l'écart à la norme (trait plein) et à l'objectif (pointillé)",
                y_domain=(-cfg.PROGRESSION_Z_RANGE, cfg.PROGRESSION_Z_RANGE),
                baseline=0,
                delay_ms=delay,
            )
        ),
        "delay": delay,
    }


def _pattern_lines(found: list, role: str, games: int) -> List[dict]:
    if found:
        return [
            {
                "text": (
                    f"{'Faiblesse' if p.polarity == 'negative' else 'Force'} : "
                    f"{METRICS[p.metric].label}, "
                    f"{'sous' if p.polarity == 'negative' else 'au-dessus de'} la norme dans "
                    f"{p.count} parties sur {p.games}."
                ),
                "tone": "bad" if p.polarity == "negative" else "good",
            }
            for p in found
        ]
    if games < coaching_config.MIN_TREND_SAMPLE:
        text = f"Pas assez de parties en {ROLE_LABELS[role]} pour dégager un schéma."
    else:
        text = f"Aucun schéma significatif sur les {coaching_config.RECURRENCE_WINDOW} dernières parties."
    return [{"text": text, "tone": "muted"}]


def progression_view(roles: Dict[str, int], history: List[dict], role: Optional[str]) -> dict:
    """L'écran Progression d'un poste : grille, verdicts de `trends()`, schémas de `patterns()`.

    `roles` : `player_roles()` ; `history` : `player_history(role)` du poste affiché ; `role` absent
    ou inconnu : le poste le plus joué. Sous `MIN_TREND_SAMPLE` parties : aucun verdict.
    """
    role = role if role in ROLE_ORDER else default_role(roles)
    games = roles.get(role, 0)
    trend_of = {t.metric: t for t in trends(history, role)} if games else {}
    rows = [
        _metric_row(
            metric, weight, [r for r in history if r["metric"] == metric], trend_of.get(metric), i
        )
        for i, (metric, weight) in enumerate(GRID[role].items())
    ]
    sample = coaching_config.MIN_TREND_SAMPLE
    return {
        "role": role,
        "role_label": ROLE_LABELS[role],
        "chips": [
            {
                "key": r,
                "label": ROLE_LABELS[r],
                "n": roles.get(r, 0),
                "hue": ROLE_HUES[r],
                "on": r == role,
            }
            for r in ROLE_ORDER
        ],
        "games": games,
        "empty": games == 0,
        "rows": rows if games else [],
        "sample_note": (
            f"Tendance sur une moyenne glissante de {client_config.PROGRESSION_SPARK_WINDOW} "
            f"parties ; verdict à partir de {2 * sample} parties."
            if games >= sample
            else f"Sous {sample} parties, la grille s'affiche sans verdict."
        ),
        "patterns": _pattern_lines(patterns(history, role) if games else [], role, games),
    }


def finding_reference(row: dict) -> Tuple[Optional[str], Optional[str]]:
    """(norme, objectif) formatés d'un constat ; None quand la référence manque ou est en construction
    (norme sous `MIN_NORM_SAMPLE` parties). Un écart face à l'adversaire de lane a 0 pour norme."""
    metric = row["metric"]
    reliable = (
        row["norm_mean"] is not None and (row["norm_n"] or 0) >= coaching_config.MIN_NORM_SAMPLE
    )
    if not reliable:
        norm = None
    elif METRICS[metric].zero_sum and row["norm_mean"] == 0:
        norm = "0"
    else:
        norm = format_value(metric, row["norm_mean"])
    objective = (
        format_value(metric, row["objective_value"]) if row["objective_value"] is not None else None
    )
    return norm, objective


# ---------- calibration ----------


def calibration_view(repo, version: Optional[str]) -> dict:
    """L'écran Calibration d'une version du modèle de draft (jamais de mélange, SPEC-05 §7).

    `repo` : `CoachingRepository` ; `version` absente ou inconnue : la version courante de
    `analysis_config` si elle a des issues, sinon la plus fournie. Sous `MIN_ROWS_FOR_CALIBRATION`
    prédictions : le même refus que la console (`scripts/calibrate_model.py`), sans diagramme.
    """
    labelled = repo.labelled_versions()
    names = [name for name, _ in labelled]
    current = analysis_config.MODEL_VERSION
    chosen = version if version in names else current if current in names else None
    chosen = chosen or (names[0] if names else None)
    view = {
        "empty": chosen is None,
        "version": chosen,
        "current": current,
        "versions": [{"name": n, "count": c, "on": n == chosen} for n, c in labelled],
        "minimum": analysis_config.MIN_ROWS_FOR_CALIBRATION,
        "n": 0,
        "enough": False,
        "chart": None,
        "table": [],
        "brier": None,
    }
    if chosen is None:
        return view
    rows = fetch_labeled_predictions(repo.db, chosen)
    view["n"] = len(rows)
    if len(rows) < analysis_config.MIN_ROWS_FOR_CALIBRATION:
        return view
    buckets = calibration_buckets(rows)
    brier = brier_score(rows)
    view.update(
        enough=True,
        brier=fr(brier, 4),
        brier_value=brier,
        table=[
            {
                "range": f"{b['lo']} à {b['hi']} %",
                "n": b["n"],
                "predicted": f"{fr(b['predicted'] * 100, 1)} %" if b["n"] else "—",
                "observed": f"{fr(b['observed'] * 100, 1)} %" if b["n"] else "—",
            }
            for b in buckets
        ],
        chart=Markup(
            reliability_chart(
                [(b["predicted"], b["observed"], b["n"]) for b in buckets if b["n"]],
                size=client_config.CALIBRATION_CHART_SIZE,
                uid="calibration",
                title="Diagramme de fiabilité",
                desc=f"Probabilité prédite contre fréquence observée, {len(rows)} prédictions "
                f"du modèle {chosen}, Brier {fr(brier, 4)}",
            )
        ),
    )
    return view


class _NoPredictions:
    """Ce que lit `calibration_view` quand la base n'a pas (encore) de table de prédictions."""

    db = None

    @staticmethod
    def labelled_versions() -> list:
        return []


def calibration_empty() -> dict:
    return calibration_view(_NoPredictions(), None)
