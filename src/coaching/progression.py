"""Suivi dans le temps : schémas, profil, tendances, LP (SPEC-19 §7, tâche 36).

Tout se lit dans `game_metrics` et `rank_snapshots`, sans appel LCU. Aucun
verdict sous les seuils d'échantillon : l'ignorance reste visible.
"""

from dataclasses import dataclass
from math import erf, sqrt
from statistics import mean, variance
from typing import Dict, List, Optional

from ..config_constants import coaching_config
from ..draft.loadout import binomial_tail
from .grid import GRID
from .metrics import METRICS

TIERS = (
    "IRON",
    "BRONZE",
    "SILVER",
    "GOLD",
    "PLATINUM",
    "EMERALD",
    "DIAMOND",
    "MASTER",
    "GRANDMASTER",
    "CHALLENGER",
)
DIVISIONS = ("IV", "III", "II", "I")


@dataclass(frozen=True)
class Pattern:
    metric: str
    polarity: str  # "negative" ou "positive"
    count: int
    games: int
    p_value: float


@dataclass(frozen=True)
class WindowGap:
    metric: str
    mean_z: float  # z_norm moyen sur la fenêtre (parties à norme fiable seulement)
    zs: List[Optional[float]]  # un z par partie, de la plus ancienne à la plus récente
    game_ids: List[int]  # alignés sur `zs`
    mean_value: float
    mean_norm: Optional[float]
    objective: Optional[float]  # objectif OneTricks de la dernière partie


@dataclass(frozen=True)
class Trend:
    metric: str
    before: float
    after: float
    t: float  # orienté : positif = progrès
    games: int

    @property
    def verdict(self) -> str:
        if self.t >= coaching_config.TREND_MIN_T:
            return "progrès"
        if self.t <= -coaching_config.TREND_MIN_T:
            return "recul"
        return "stable"


def _series(history: List[dict], metric: str, reliable_norm: bool = False) -> List[dict]:
    """Lignes d'une métrique, de la plus récente à la plus ancienne."""
    rows = [row for row in history if row["metric"] == metric]
    if reliable_norm:
        rows = [
            row
            for row in rows
            if row["z_norm"] is not None and (row["norm_n"] or 0) >= coaching_config.MIN_NORM_SAMPLE
        ]
    return rows


def lower_tail(z: float) -> float:
    """P(Z <= z) pour une loi normale centrée réduite."""
    return 0.5 * (1 + erf(z / sqrt(2)))


def patterns(history: List[dict], role: str) -> List[Pattern]:
    """Constats trop fréquents sur les dernières parties pour être du bruit.

    Sous l'hypothèse nulle (joueur au niveau de ses pairs), `z_norm` suit à peu
    près une loi normale : un écart au-delà de MIN_ABS_Z a une probabilité
    connue, et le test binomial de SPEC-15 §3.2.1 dit si sa fréquence la dépasse.
    """
    threshold = coaching_config.MIN_ABS_Z
    base_rate = lower_tail(-threshold)
    found = []
    for metric in GRID.get(role, {}):
        recent = _series(history, metric, reliable_norm=True)[: coaching_config.RECURRENCE_WINDOW]
        if len(recent) < coaching_config.MIN_TREND_SAMPLE:
            continue
        for polarity, hits in (
            ("negative", sum(row["z_norm"] <= -threshold for row in recent)),
            ("positive", sum(row["z_norm"] >= threshold for row in recent)),
        ):
            p_value = binomial_tail(len(recent), base_rate, hits)
            if hits and p_value < coaching_config.RECURRENCE_ALPHA:
                found.append(Pattern(metric, polarity, hits, len(recent), p_value))
    return sorted(found, key=lambda pattern: pattern.p_value)


def profile(history: List[dict], role: str) -> List[tuple]:
    """(métrique, z_norm moyen, parties), du plus faible au plus fort."""
    rows = []
    for metric in GRID.get(role, {}):
        series = _series(history, metric, reliable_norm=True)
        if len(series) >= coaching_config.MIN_TREND_SAMPLE:
            rows.append((metric, mean(row["z_norm"] for row in series), len(series)))
    return sorted(rows, key=lambda row: row[1])


def objective_gaps(history: List[dict], role: str) -> List[tuple]:
    """(métrique, z_objective moyen, parties) sur les RECURRENCE_WINDOW dernières parties.

    Du plus bas au plus haut ; seules les métriques de la grille qui ont un objectif.
    """
    rows = []
    for metric in GRID.get(role, {}):
        recent = _series(history, metric)[: coaching_config.RECURRENCE_WINDOW]
        series = [row["z_objective"] for row in recent if row["z_objective"] is not None]
        if len(series) >= coaching_config.MIN_TREND_SAMPLE:
            rows.append((metric, mean(series), len(series)))
    return sorted(rows, key=lambda row: row[1])


def window_gaps(history: List[dict], role: str, games: int) -> List[WindowGap]:
    """Écart moyen de chaque métrique de la grille sur les `games` dernières parties du poste.

    Du plus faible au plus fort, pondéré par le rang de la grille comme `Finding.weighted`.
    Une métrique sous MIN_TREND_SAMPLE parties à norme fiable n'est pas classée.
    """
    found = []
    for metric in GRID.get(role, {}):
        recent = _series(history, metric)[:games]
        reliable = _series(recent, metric, reliable_norm=True)
        if len(reliable) < coaching_config.MIN_TREND_SAMPLE:
            continue
        ordered = recent[::-1]
        found.append(
            WindowGap(
                metric,
                mean(row["z_norm"] for row in reliable),
                [row["z_norm"] if row in reliable else None for row in ordered],
                [row["game_id"] for row in ordered],
                mean(row["value"] for row in recent),
                mean(row["norm_mean"] for row in reliable),
                recent[0]["objective_value"],
            )
        )
    return sorted(found, key=lambda gap: gap.mean_z * GRID[role][gap.metric])


def trends(history: List[dict], role: str) -> List[Trend]:
    """Valeur brute des dernières parties contre celles d'avant, par métrique.

    ponytail: deux moitiés de fenêtre et un t de Welch ; un CUSUM (§7.2) si les
    verdicts se révèlent trop lents à venir.
    """
    found = []
    for metric in GRID.get(role, {}):
        values = [row["value"] for row in _series(history, metric)][
            : 2 * coaching_config.RECURRENCE_WINDOW
        ]
        half = len(values) // 2
        if half < coaching_config.MIN_TREND_SAMPLE:
            continue
        recent, older = values[:half], values[half : 2 * half]
        spread = sqrt(variance(recent) / half + variance(older) / half)
        if not spread:
            continue
        t = METRICS[metric].sense * (mean(recent) - mean(older)) / spread
        found.append(Trend(metric, mean(older), mean(recent), t, 2 * half))
    return sorted(found, key=lambda trend: -abs(trend.t))


def lp_scale(tier: str, division: Optional[str], lp: int) -> int:
    """Rang en échelle continue : palier × 400 + division × 100 + LP (§8)."""
    index = TIERS.index(tier) if tier in TIERS else 0
    division_index = DIVISIONS.index(division) if division in DIVISIONS else 0
    if index >= TIERS.index("MASTER"):
        division_index = 0
    return index * 400 + division_index * 100 + lp


def lp_changes(snapshots: List[tuple]) -> Dict[str, tuple]:
    """File -> (première photo, dernière photo, écart en LP sur l'échelle continue)."""
    by_queue: Dict[str, list] = {}
    for captured, queue, tier, division, lp in snapshots:
        by_queue.setdefault(queue, []).append((captured, tier, division, lp))
    return {
        queue: (
            shots[0],
            shots[-1],
            lp_scale(*shots[-1][1:]) - lp_scale(*shots[0][1:]),
        )
        for queue, shots in by_queue.items()
    }
