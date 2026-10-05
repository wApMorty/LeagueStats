"""Graphiques SVG du client (SPEC-21 §4.4, tâche 50) : fonctions pures, sans HTTP ni base.

Chaque fonction rend le balisage d'un `<svg>` prêt à être inclus tel quel dans un gabarit. Les
couleurs sont des variables CSS (`var(--mint)`), les libellés passent par `html.escape`, chaque
graphique porte `<title>` et `<desc>` (`role="img"`). Les tracés utilisent les attributs de
`motion.js` (`data-trace`, `data-fade`, `data-pop`, `data-bar`) : les durées et les délais sont des
paramètres, aucun JS n'est généré ici.

Les dégradés sont en `userSpaceOnUse` : en `objectBoundingBox`, une ligne parfaitement horizontale
(un palier de rang qui ne bouge pas) a une boîte de hauteur nulle et le navigateur ne la dessine pas.
"""

from dataclasses import dataclass
from html import escape
from math import sqrt
from typing import Callable, Optional, Sequence, Tuple

Point = Tuple[float, float]
Domain = Tuple[float, float]


@dataclass(frozen=True)
class Tick:
    """Repère d'un axe : filet (`color`, `dash`) et libellé."""

    value: float
    label: str = ""
    color: str = "var(--rule)"
    dash: str = ""
    label_color: str = "var(--muted-2)"


@dataclass(frozen=True)
class Band:
    """Bande de fond entre deux valeurs de l'axe vertical."""

    lo: float
    hi: float
    color: str


@dataclass(frozen=True)
class Series:
    """Une courbe : points `(x, y)` dans les unités des domaines, dégradé de gauche à droite."""

    name: str
    points: Sequence[Point]
    stops: Sequence[str] = ("var(--mint)",)
    width: float = 2.5
    area: bool = False
    dots: bool = False
    trace_ms: int = 2400
    delay_ms: int = 300
    end_label: str = ""  # dernier point lumineux, avec son étiquette


@dataclass(frozen=True)
class Mark:
    """Repère posé sur la courbe (événement d'une partie)."""

    x: float
    y: float
    color: str
    label: str = ""
    above: bool = True


@dataclass(frozen=True)
class SparkLine:
    """Une ligne de sparkline : valeurs réparties à intervalles égaux."""

    values: Sequence[float]
    color: str = "var(--copper)"
    dashed: bool = False
    width: float = 2.0


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def _n(value: float) -> str:
    return f"{value:.1f}"


def _scale(domain: Domain, start: float, end: float) -> Callable[[float], float]:
    low, high = domain
    span = (high - low) or 1.0
    return lambda value: start + (value - low) / span * (end - start)


def _path(points: Sequence[Point]) -> str:
    return " ".join(f"{'L' if i else 'M'}{_n(x)},{_n(y)}" for i, (x, y) in enumerate(points))


def _open(width: float, height: float, uid: str, title: str, desc: str, css: str = "chart") -> str:
    return (
        f'<svg class="{css}" viewBox="0 0 {width:g} {height:g}" role="img" '
        f'aria-labelledby="{uid}-t {uid}-d"><title id="{uid}-t">{esc(title)}</title>'
        f'<desc id="{uid}-d">{esc(desc)}</desc>'
    )


def _gradient(gid: str, stops: Sequence[str], x1: float, x2: float, opacities=None) -> str:
    last = max(len(stops) - 1, 1)
    items = "".join(
        f'<stop offset="{i / last:g}" style="stop-color:{esc(color)}'
        + (f";stop-opacity:{opacities[i]}" if opacities else "")
        + '"/>'
        for i, color in enumerate(stops)
    )
    return (
        f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{_n(x1)}" x2="{_n(x2)}" '
        f'y1="0" y2="0">{items}</linearGradient>'
    )


def line_chart(
    series: Sequence[Series],
    *,
    size: Tuple[int, int],
    x_domain: Domain,
    y_domain: Domain,
    uid: str,
    title: str,
    desc: str,
    margin: Tuple[int, int, int, int] = (90, 40, 44, 60),
    x_ticks: Sequence[Tick] = (),
    y_ticks: Sequence[Tick] = (),
    bands: Sequence[Band] = (),
    marks: Sequence[Mark] = (),
) -> str:
    """Courbes sur deux axes, avec bandes, filets gradués, repères et dernier point lumineux.

    `margin` : gauche, haut, droite, bas (pixels) ; la zone de tracé est le reste. Une série de
    moins de deux points n'est pas tracée (ignorance visible : c'est à l'appelant de le dire).
    `uid` distingue les identifiants de dégradés quand plusieurs graphiques cohabitent.
    """
    width, height = size
    left, top, right, bottom = margin
    sx = _scale(x_domain, left, width - right)
    sy = _scale(y_domain, height - bottom, top)
    plot_bottom = height - bottom
    out = [_open(width, height, uid, title, desc)]

    drawn = [(i, s) for i, s in enumerate(series) if len(s.points) >= 2]
    out.append("<defs>")
    for i, s in drawn:
        out.append(_gradient(f"{uid}-g{i}", s.stops, left, width - right))
        if s.area:
            top_color = s.stops[len(s.stops) // 2]
            out.append(
                f'<linearGradient id="{uid}-a{i}" gradientUnits="userSpaceOnUse" x1="0" x2="0" '
                f'y1="{_n(top)}" y2="{_n(plot_bottom)}"><stop offset="0" style="stop-color:'
                f'{esc(top_color)};stop-opacity:.28"/><stop offset="1" style="stop-color:'
                f'{esc(s.stops[0])};stop-opacity:0"/></linearGradient>'
            )
    out.append("</defs>")

    for band in bands:
        lo, hi = max(band.lo, y_domain[0]), min(band.hi, y_domain[1])
        if hi > lo:
            out.append(
                f'<rect x="{left}" y="{_n(sy(hi))}" width="{width - left - right}" '
                f'height="{_n(sy(lo) - sy(hi))}" style="fill:{esc(band.color)}"/>'
            )
    for tick in y_ticks:
        y = sy(tick.value)
        dash = f";stroke-dasharray:{esc(tick.dash)}" if tick.dash else ""
        out.append(
            f'<line x1="{left}" x2="{width - right}" y1="{_n(y)}" y2="{_n(y)}" '
            f'style="stroke:{esc(tick.color)}{dash}"/>'
        )
        if tick.label:
            out.append(
                f'<text class="ch-tick" x="{left - 12}" y="{_n(y + 4)}" text-anchor="end" '
                f'style="fill:{esc(tick.label_color)}">{esc(tick.label)}</text>'
            )
    for tick in x_ticks:
        out.append(
            f'<text class="ch-tick" x="{_n(sx(tick.value))}" y="{plot_bottom + 30}" '
            f'text-anchor="middle" style="fill:{esc(tick.label_color)}">{esc(tick.label)}</text>'
        )

    for i, s in drawn:
        points = [(sx(x), sy(y)) for x, y in s.points]
        line = _path(points)
        if s.area:
            out.append(
                f'<path data-fade="1" data-delay="{s.delay_ms + s.trace_ms - 500}" '
                f'd="{line} L{_n(points[-1][0])},{_n(plot_bottom)} L{_n(points[0][0])},'
                f'{_n(plot_bottom)} Z" style="fill:url(#{uid}-a{i})"/>'
            )
        out.append(
            f'<path class="ch-line" data-trace="{s.trace_ms}" data-delay="{s.delay_ms}" d="{line}" '
            f'style="stroke:url(#{uid}-g{i});stroke-width:{s.width:g}"/>'
        )
        span = (points[-1][0] - points[0][0]) or 1.0
        for j, (x, y) in enumerate(points):
            last = j == len(points) - 1
            when = int(s.delay_ms + (x - points[0][0]) / span * s.trace_ms)
            if last and s.end_label:
                out.append(_end_point(x, y, s.end_label, when, width))
            elif s.dots:
                out.append(
                    f'<circle class="ch-dot" data-fade="1" data-delay="{when}" cx="{_n(x)}" '
                    f'cy="{_n(y)}" r="4"/>'
                )

    for mark in marks:
        x, y = sx(mark.x), sy(mark.y)
        offset = -22 if mark.above else 28
        label = (
            f'<text class="ch-mark-label" x="{_n(x)}" y="{_n(y + offset)}" text-anchor="middle" '
            f'style="fill:{esc(mark.color)}">{esc(mark.label)}</text>'
            if mark.label
            else ""
        )
        when = int(300 + (x - sx(x_domain[0])) / ((sx(x_domain[1]) - sx(x_domain[0])) or 1) * 2600)
        out.append(
            f'<g class="ch-mark" data-pop="1" data-delay="{when}"><circle cx="{_n(x)}" cy="{_n(y)}" '
            f'r="7" style="stroke:{esc(mark.color)}"/>{label}</g>'
        )
    out.append("</svg>")
    return "".join(out)


def _end_point(x: float, y: float, label: str, delay: int, width: float) -> str:
    """Dernier point lumineux et son étiquette (rabattue à gauche près du bord droit)."""
    box = len(label) * 7.6 + 26
    box_x = max(4.0, min(x - box + 20, width - box - 4))
    return (
        f'<circle class="ch-end" data-pop="1" data-delay="{delay}" cx="{_n(x)}" cy="{_n(y)}" r="9"/>'
        f'<g data-fade="1" data-delay="{delay + 100}"><rect class="ch-label-box" x="{_n(box_x)}" '
        f'y="{_n(y - 50)}" width="{_n(box)}" height="30" rx="4"/><text class="ch-label" '
        f'x="{_n(box_x + 13)}" y="{_n(y - 30)}">{esc(label)}</text></g>'
    )


def sparkline(
    lines: Sequence[SparkLine],
    *,
    size: Tuple[int, int],
    uid: str,
    title: str,
    desc: str = "",
    y_domain: Optional[Domain] = None,
    baseline: Optional[float] = None,
    trace_ms: int = 1200,
    delay_ms: int = 0,
    pad: int = 4,
) -> str:
    """Lignes superposées sur la même échelle. `y_domain` absent : de la plus petite à la plus
    grande valeur. `baseline` : filet pointillé à cette valeur (le zéro d'un écart, par exemple)."""
    width, height = size
    values = [v for line in lines for v in line.values]
    if y_domain is None:
        y_domain = (min(values), max(values)) if values else (0.0, 1.0)
    sy = _scale(y_domain, height - pad, pad)
    out = [_open(width, height, uid, title, desc or title, "spark")]
    if baseline is not None:
        y = _n(sy(baseline))
        out.append(f'<line class="spark-base" x1="0" x2="{width}" y1="{y}" y2="{y}"/>')
    for line in lines:
        count = len(line.values)
        if count < 2:
            continue
        low, high = y_domain
        points = [
            (i * width / (count - 1), sy(min(max(v, low), high))) for i, v in enumerate(line.values)
        ]
        dash = ";stroke-dasharray:4 4" if line.dashed else ""
        trace = "" if line.dashed else f' data-trace="{trace_ms}" data-delay="{delay_ms}"'
        fade = f' data-fade="1" data-delay="{delay_ms + 600}"' if line.dashed else ""
        out.append(
            f'<path class="spark-line"{trace}{fade} d="{_path(points)}" data-pen="{esc(line.color)}" '
            f'style="stroke:{esc(line.color)};stroke-width:{line.width:g}{dash}"/>'
        )
    out.append("</svg>")
    return "".join(out)


def bar_chart(
    values: Sequence[float],
    *,
    size: Tuple[int, int],
    uid: str,
    title: str,
    desc: str,
    labels: Optional[Sequence[str]] = None,
    gap: int = 10,
    delay_ms: int = 700,
) -> str:
    """Histogramme divergent autour d'une ligne médiane : hausse en menthe vers le haut, baisse en
    rose vers le bas, hauteurs proportionnelles à la plus grande valeur absolue."""
    width, height = size
    middle = height / 2
    top_bar = middle - 2
    biggest = max((abs(v) for v in values), default=0) or 1.0
    count = max(len(values), 1)
    slot = (width - gap * (count - 1)) / count
    out = [
        _open(width, height, uid, title, desc),
        f'<line class="ch-axis" x1="0" x2="{width}" y1="{_n(middle)}" y2="{_n(middle)}"/>',
    ]
    for i, value in enumerate(values):
        bar = max(abs(value) / biggest * top_bar, 1.0)
        positive = value >= 0
        label = esc(labels[i]) if labels else esc(f"{value:+g}")
        out.append(
            f'<rect class="ch-bar {"ch-pos" if positive else "ch-neg"}" data-bar="y" '
            f'data-delay="{delay_ms + i * 40}" x="{_n(i * (slot + gap))}" '
            f'y="{_n(middle - bar if positive else middle)}" width="{_n(slot)}" height="{_n(bar)}" '
            f'rx="3"><title>{label}</title></rect>'
        )
    out.append("</svg>")
    return "".join(out)


def reliability_chart(
    points: Sequence[Tuple[float, float, int]],
    *,
    size: Tuple[int, int],
    uid: str,
    title: str,
    desc: str,
    margin: Tuple[int, int, int, int] = (64, 24, 24, 56),
) -> str:
    """Diagramme de fiabilité : probabilité prédite (x) contre fréquence observée (y), de 0 à 1.

    `points` : `(prédite moyenne, observée, parties)` par classe non vide. La diagonale est le modèle
    parfait ; le rayon d'un point suit le nombre de parties de sa classe."""
    width, height = size
    left, top, right, bottom = margin
    sx = _scale((0, 1), left, width - right)
    sy = _scale((0, 1), height - bottom, top)
    out = [_open(width, height, uid, title, desc)]
    for i in range(0, 11, 2):
        value = i / 10
        x, y = _n(sx(value)), _n(sy(value))
        out.append(
            f'<line class="ch-grid" x1="{left}" x2="{width - right}" y1="{y}" y2="{y}"/>'
            f'<line class="ch-grid" x1="{x}" x2="{x}" y1="{top}" y2="{height - bottom}"/>'
            f'<text class="ch-tick" x="{left - 10}" y="{_n(sy(value) + 4)}" text-anchor="end">'
            f"{round(value * 100)} %</text>"
            f'<text class="ch-tick" x="{x}" y="{height - bottom + 24}" text-anchor="middle">'
            f"{round(value * 100)} %</text>"
        )
    out.append(
        f'<line class="ch-diag" x1="{_n(sx(0))}" y1="{_n(sy(0))}" x2="{_n(sx(1))}" y2="{_n(sy(1))}"/>'
    )
    coords = [(sx(p), sy(o)) for p, o, _ in points]
    if len(coords) >= 2:
        out.append(
            f'<path class="ch-line" data-trace="1600" data-delay="300" d="{_path(coords)}" '
            f'style="stroke:var(--gold);stroke-width:2.4"/>'
        )
    biggest = max((n for _, _, n in points), default=1) or 1
    for (x, y), (predicted, observed, n) in zip(coords, points):
        radius = 4 + 7 * sqrt(n / biggest)
        out.append(
            f'<circle class="ch-dot ch-dot-solid" data-fade="1" data-delay="900" cx="{_n(x)}" '
            f'cy="{_n(y)}" r="{_n(radius)}"><title>{esc(_reading(predicted, observed, n))}'
            "</title></circle>"
        )
    out.append("</svg>")
    return "".join(out)


def _reading(predicted: float, observed: float, n: int) -> str:
    return (
        f"prédit {predicted * 100:.0f} %, observé {observed * 100:.0f} %, "
        f"{n} partie{'s' if n > 1 else ''}"
    )


def diverging(value: float, scale: float, half: float = 50.0) -> Tuple[float, float]:
    """`(gauche, largeur)` en % d'une barre divergente centrée : `scale` est la valeur qui remplit
    une demi-largeur. Une valeur positive part du centre vers la droite, une négative vers la gauche.
    """
    width = min(half, abs(value) / (scale or 1.0) * half)
    return (half if value >= 0 else half - width), width
