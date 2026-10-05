"""Données des écrans du coaching (SPEC-21 §4.4, §4.10) : lectures de la base devenues ce que les
gabarits dessinent.

Fonctions pures : des lignes de repository entrent, un dictionnaire prêt pour Jinja sort (avec les
graphiques de `charts.py` déjà rendus). Aucune requête, aucun LCU, aucune horloge cachée : un écran
est testable avec des listes de dictionnaires. Les valeurs de réglage sont dans `config_client.py`.
"""

from datetime import datetime, timezone
from typing import List, Sequence, Tuple

from markupsafe import Markup

from ..coaching.progression import DIVISIONS, TIERS, lp_scale
from ..config_client import client_config
from .charts import Band, Series, Tick, bar_chart, line_chart
from .draft_view import fr, signed

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


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'s' if count > 1 else ''}"


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
