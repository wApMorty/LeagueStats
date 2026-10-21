"""Maîtrise personnelle par champion (SPEC-41).

Fonctions pures, sans base ni I/O. Une partie est une paire ``(champion, ΔP)`` où ΔP
est le delta de win chance de la partie, en points. La maîtrise d'un champion est son
écart moyen à la référence (moyenne de toutes les parties), rétréci vers 0 selon le
nombre de parties : ``points = raw_points × n / (n + k)``.

``k`` vient de :func:`shrink_k`, estimé sur les données elles-mêmes (méthode des
moments à effets aléatoires). Sans estimation fiable, l'appelant décide quoi faire
d'un ``None``.
"""

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Mastery:
    """Maîtrise d'un champion : écart moyen à la référence, puis rétréci."""

    champion: str
    games: int
    raw_points: float
    points: float


def shrink_k(groups: Mapping[str, Sequence[float]]) -> Optional[float]:
    """Calcule K = σ² / τ² (ANOVA à un facteur, groupes déséquilibrés).

    σ² est la variance intra-groupe, τ² la variance inter-groupe (effets aléatoires),
    estimées par la méthode des moments. Les groupes à une seule valeur comptent dans
    l'inter-groupe, pas dans l'intra-groupe.

    Retourne ``None`` si τ² ≤ 0, si G < 2 groupes, ou si N − G < 1 (pas de degré de
    liberté intra-groupe).
    """
    sizes: List[int] = []
    means: List[float] = []
    total = 0.0
    within_ss = 0.0
    for vals in groups.values():
        if not vals:
            continue
        mean = sum(vals) / len(vals)
        sizes.append(len(vals))
        means.append(mean)
        total += sum(vals)
        within_ss += sum((x - mean) ** 2 for x in vals)

    g_count = len(sizes)
    n_total = sum(sizes)
    if g_count < 2 or n_total - g_count < 1:
        return None

    grand_mean = total / n_total
    sigma2 = within_ss / (n_total - g_count)

    between_ss = sum(n * (m - grand_mean) ** 2 for n, m in zip(sizes, means))
    n0 = (n_total - sum(n * n for n in sizes) / n_total) / (g_count - 1)
    tau2 = (between_ss / (g_count - 1) - sigma2) / n0
    if tau2 <= 0:
        return None
    return sigma2 / tau2


def masteries(
    games: Sequence[Tuple[str, float]],
    k: float,
    norms: Optional[Mapping[str, float]] = None,
) -> Dict[str, Mastery]:
    """Une :class:`Mastery` par champion joué, depuis des parties ``(champion, ΔP)``.

    Référence : moyenne de toutes les valeurs (variante a). Avec ``norms``, chaque valeur
    est d'abord diminuée de ``norms.get(champion, 0.0)``, puis référence et moyennes sont
    recalculées sur les valeurs corrigées (variante b). ``raw_points`` est la moyenne du
    champion moins la référence ; ``points = raw_points × n / (n + k)``.

    Un champion absent de ``games`` n'apparaît pas dans le résultat ; une liste vide
    donne ``{}``.
    """
    if not games:
        return {}

    offsets = norms or {}
    corrected: List[Tuple[str, float]] = [
        (champion, value - offsets.get(champion, 0.0)) for champion, value in games
    ]
    reference = sum(value for _, value in corrected) / len(corrected)

    by_champion: Dict[str, List[float]] = {}
    for champion, value in corrected:
        by_champion.setdefault(champion, []).append(value)

    result: Dict[str, Mastery] = {}
    for champion, vals in by_champion.items():
        n = len(vals)
        raw = sum(vals) / n - reference
        result[champion] = Mastery(
            champion=champion,
            games=n,
            raw_points=raw,
            points=raw * n / (n + k),
        )
    return result
