"""Maîtrise personnelle par champion (SPEC-41).

Fonctions pures, sans base ni I/O. Une partie est une paire ``(champion, ΔP)`` où ΔP
est le delta de win chance de la partie, en points. La maîtrise d'un champion est son
écart moyen à la référence (moyenne de toutes les parties), rétréci vers 0 selon le
nombre de parties : ``points = raw_points × n / (n + k)``.

``k`` vient de :func:`shrink_k`, estimé sur les données elles-mêmes (méthode des
moments à effets aléatoires). Sans estimation fiable, l'appelant décide quoi faire
d'un ``None``.
"""

import random
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from ..winprob.model import _solve
from .probability import sigmoid

# Quantiles du bootstrap à 2,5 % et 97,5 %, et critère d'arrêt de Newton : constantes
# statistiques, pas des réglages.
_Q_LOW = 0.025
_Q_HIGH = 0.975
_NEWTON_TOLERANCE = 1e-10
_NEWTON_ITERATIONS = 50


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
    return pooled_shrink_k([groups])


def pooled_shrink_k(players: Sequence[Mapping[str, Sequence[float]]]) -> Optional[float]:
    """K = σ² / τ² commun à plusieurs joueurs : variance entre champions À L'INTÉRIEUR de chaque
    joueur, regroupée (méthode des moments).

    Chaque joueur a son propre niveau moyen : comparer ses champions à sa moyenne, et non à celle de
    la population, retire ce niveau de τ². Centrer les valeurs par joueur puis appeler `shrink_k` ne
    le fait pas : un joueur à un seul champion y ajoute un groupe de moyenne exactement 0, ce qui
    écrase τ². Pour un seul joueur, le résultat est celui de l'ANOVA à un facteur de `shrink_k`.

    Par joueur p (N_p valeurs, G_p champions, moyenne m_p) : SS inter = Σ n_c (m_c − m_p)², de
    degrés G_p − 1 et d'espérance (G_p − 1) σ² + (N_p − Σ n_c² / N_p) τ² ; SS intra de degrés N_p − G_p.
    Retourne ``None`` si τ² ≤ 0 ou sans degré de liberté inter ou intra.
    """
    within_ss = between_ss = tau_weight = 0.0
    within_df = between_df = 0
    for groups in players:
        sizes = [len(vals) for vals in groups.values() if vals]
        means = [sum(vals) / len(vals) for vals in groups.values() if vals]
        if not sizes:
            continue
        n_total = sum(sizes)
        player_mean = sum(n * m for n, m in zip(sizes, means)) / n_total
        within_ss += sum(
            sum((x - sum(vals) / len(vals)) ** 2 for x in vals) for vals in groups.values() if vals
        )
        between_ss += sum(n * (m - player_mean) ** 2 for n, m in zip(sizes, means))
        within_df += n_total - len(sizes)
        between_df += len(sizes) - 1
        tau_weight += n_total - sum(n * n for n in sizes) / n_total

    if within_df < 1 or between_df < 1:
        return None
    sigma2 = within_ss / within_df
    tau2 = (between_ss - sigma2 * between_df) / tau_weight
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


# ---------- étude du terme (SPEC-41 §4.3, tâche 199) ----------


def _gradient_hessian(
    xs: Sequence[Sequence[float]], ys: Sequence[int], coef: Sequence[float]
) -> Tuple[List[float], List[List[float]]]:
    """Gradient et hessienne (opposée) de la log-vraisemblance logistique en `coef`."""
    d = len(coef)
    grad = [0.0] * d
    hess = [[0.0] * d for _ in range(d)]
    for x, y in zip(xs, ys):
        p = sigmoid(sum(c * v for c, v in zip(coef, x)))
        weight = p * (1.0 - p)
        for a in range(d):
            grad[a] += (y - p) * x[a]
            for b in range(a, d):
                hess[a][b] += weight * x[a] * x[b]
    for a in range(d):
        for b in range(a):
            hess[a][b] = hess[b][a]
    return grad, hess


def fit_logistic(xs: Sequence[Sequence[float]], ys: Sequence[int]) -> List[float]:
    """Régression logistique par Newton (IRLS), estimateur du maximum de vraisemblance exact.

    `xs` : une ligne de variables par observation, biais compris (une colonne de 1 si voulu) ;
    `ys` : issues 0 ou 1. Rend les coefficients dans l'ordre des colonnes.
    """
    coef = [0.0] * len(xs[0])
    for _ in range(_NEWTON_ITERATIONS):
        grad, hess = _gradient_hessian(xs, ys, coef)
        step = _solve(hess, grad)
        coef = [c + s for c, s in zip(coef, step)]
        if max(abs(s) for s in step) < _NEWTON_TOLERANCE:
            break
    return coef


def predict_logistic(coef: Sequence[float], x: Sequence[float]) -> float:
    """Probabilité prédite par `fit_logistic` pour la ligne `x`."""
    return sigmoid(sum(c * v for c, v in zip(coef, x)))


def ci95(samples: Sequence[float]) -> Tuple[float, float]:
    """IC95 percentile d'un échantillon bootstrap."""
    ranked = sorted(samples)
    n = len(ranked)
    return ranked[int(_Q_LOW * n)], ranked[int(_Q_HIGH * n) - 1]


def _player_draws(players: Sequence[str], resamples: int, seed: int) -> List[Dict[str, int]]:
    """Tirages de joueurs avec remise : pour chacun, joueur -> nombre de fois tiré."""
    unique = sorted(set(players))
    rng = random.Random(seed)
    draws = []
    for _ in range(resamples):
        counts: Dict[str, int] = {}
        for _ in unique:
            player = unique[rng.randrange(len(unique))]
            counts[player] = counts.get(player, 0) + 1
        draws.append(counts)
    return draws


def player_bootstrap(
    players: Sequence[str],
    xs: Sequence[Sequence[float]],
    ys: Sequence[int],
    coef: Sequence[float],
    resamples: int,
    seed: int,
) -> List[List[float]]:
    """Coefficients rééchantillonnés par joueur, bootstrap linéarisé (« one-step »).

    Gradient et hessienne sont sommés par joueur une fois, au coefficient ajusté `coef` ; un tirage
    de joueurs avec remise donne `coef + H*⁻¹ g*`. Les parties d'un même joueur restent ensemble :
    elles ne sont pas indépendantes. O(joueurs) par tirage au lieu d'un réajustement complet.
    """
    by_player: Dict[str, Tuple[List[Sequence[float]], List[int]]] = {}
    for player, x, y in zip(players, xs, ys):
        rows = by_player.setdefault(player, ([], []))
        rows[0].append(x)
        rows[1].append(y)
    parts = {p: _gradient_hessian(rx, ry, coef) for p, (rx, ry) in by_player.items()}
    d = len(coef)
    out = []
    for counts in _player_draws(players, resamples, seed):
        grad = [0.0] * d
        hess = [[0.0] * d for _ in range(d)]
        for player, times in counts.items():
            g, h = parts[player]
            for a in range(d):
                grad[a] += times * g[a]
                for b in range(d):
                    hess[a][b] += times * h[a][b]
        step = _solve(hess, grad)
        out.append([c + s for c, s in zip(coef, step)])
    return out


def player_mean_bootstrap(
    players: Sequence[str], values: Sequence[float], resamples: int, seed: int
) -> List[float]:
    """Moyennes de `values` (une par observation) rééchantillonnées par joueur, avec remise."""
    sums: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for player, value in zip(players, values):
        sums[player] = sums.get(player, 0.0) + value
        counts[player] = counts.get(player, 0) + 1
    out = []
    for draw in _player_draws(players, resamples, seed):
        total = sum(times * sums[p] for p, times in draw.items())
        n = sum(times * counts[p] for p, times in draw.items())
        out.append(total / n)
    return out


def decide(coef_ci: Tuple[float, float], gain_ci: Tuple[float, float]) -> bool:
    """Seuil d'adoption de SPEC-41 §2, figé avant la mesure : l'IC95 du coefficient exclut 0 et
    celui du gain de Brier est entièrement positif."""
    coef_ok = coef_ci[0] > 0 or coef_ci[1] < 0
    return coef_ok and gain_ci[0] > 0


def leave_one_out_points(
    games: Sequence[Tuple[str, float]], k: float, norms: Optional[Mapping[str, float]] = None
) -> List[float]:
    """Pour chaque partie d'un joueur, `points` de son champion calculé sur ses AUTRES parties.

    Identique à `masteries(autres parties, k, norms)[champion].points` (0 si le champion n'y est
    pas), en O(1) par partie grâce aux sommes par champion.
    """
    offsets = norms or {}
    corrected = [(c, v - offsets.get(c, 0.0)) for c, v in games]
    total, n_total = sum(v for _, v in corrected), len(corrected)
    sums: Dict[str, float] = {}
    counts: Dict[str, int] = {}
    for champion, value in corrected:
        sums[champion] = sums.get(champion, 0.0) + value
        counts[champion] = counts.get(champion, 0) + 1
    out = []
    for champion, value in corrected:
        n = counts[champion] - 1
        if n == 0 or n_total == 1:
            out.append(0.0)
            continue
        reference = (total - value) / (n_total - 1)
        raw = (sums[champion] - value) / n - reference
        out.append(raw * n / (n + k))
    return out
