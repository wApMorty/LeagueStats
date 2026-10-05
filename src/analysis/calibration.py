"""Pure calibration math for the log-odds scoring model (SPEC-05 B7).

Extracted from scripts/calibrate_model.py (SPEC-12) so both the standalone
CLI diagnostic and the live Draft Coach's auto-triggered summary
(src/draft/calibration_notice.py) share one implementation instead of two.
No I/O beyond the DB read in fetch_labeled_predictions(); everything else is
plain math, hand-rolled per SPEC-05 section 8 ("hors périmètre" for
numpy/scipy/sklearn on a 2-parameter logistic regression).
"""

import math
import random
from typing import Dict, List, Optional, Sequence, Tuple

Row = Tuple[float, int]  # (predicted_probability, outcome)


def fetch_labeled_predictions(db, model_version: Optional[str] = None) -> List[Row]:
    """Rows with a known outcome, optionally restricted to one model_version
    (SPEC-05 §7: mixing model versions makes calibration meaningless)."""
    cursor = db.connection.cursor()
    if model_version:
        cursor.execute(
            "SELECT predicted_probability, outcome FROM predictions "
            "WHERE outcome IS NOT NULL AND model_version = ?",
            (model_version,),
        )
    else:
        cursor.execute(
            "SELECT predicted_probability, outcome FROM predictions WHERE outcome IS NOT NULL"
        )
    return cursor.fetchall()


def calibration_buckets(rows: List[Row]) -> List[dict]:
    """Bucket predictions into 10 decile buckets: `lo`/`hi` (percent), `n`, and, for a non-empty
    bucket, the mean `predicted` probability and the `observed` win rate (both in [0, 1])."""
    buckets: List[List[Row]] = [[] for _ in range(10)]
    for predicted, outcome in rows:
        idx = min(int(predicted * 10), 9)
        buckets[idx].append((predicted, outcome))
    return [
        {
            "lo": i * 10,
            "hi": (i + 1) * 10,
            "n": len(bucket),
            "predicted": sum(p for p, _ in bucket) / len(bucket) if bucket else None,
            "observed": sum(o for _, o in bucket) / len(bucket) if bucket else None,
        }
        for i, bucket in enumerate(buckets)
    ]


def calibration_curve(rows: List[Row]) -> str:
    """Bucket predictions into 10 decile buckets, predicted vs observed win rate."""
    lines = []
    for bucket in calibration_buckets(rows):
        lo, hi = bucket["lo"], bucket["hi"]
        if not bucket["n"]:
            lines.append(f"  [{lo:3d}-{hi:3d}%[  n=0")
            continue
        lines.append(
            f"  [{lo:3d}-{hi:3d}%[  n={bucket['n']:4d}  "
            f"predicted={bucket['predicted'] * 100:5.1f}%  observed={bucket['observed'] * 100:5.1f}%"
        )
    return "\n".join(lines)


def brier_score(rows: List[Row]) -> float:
    """Mean((predicted_probability - outcome)^2). 0 = perfect, 0.25 = always predicting 50%."""
    return sum((p - o) ** 2 for p, o in rows) / len(rows)


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def suggest_scale(rows: List[Row], iterations: int = 50) -> float:
    """Hand-rolled 1-parameter logistic recalibration (Platt scaling, no
    intercept -- our model is already centered at logit=0 for an even draft):
    finds the scale `s` maximizing the log-likelihood of the observed
    outcomes under `P = sigmoid(s * logit(predicted_probability))`.

    Newton's method in pure Python -- no numpy/scipy/sklearn, per SPEC-05
    section 8 ("la régression logistique de calibration se fait sur
    2 paramètres, à la main ... aucune dépendance nouvelle"). `s < 1` means
    the model is currently too confident (predictions too far from 50%);
    `s > 1` means it's too timid; `s <= 0` means no usable signal.

    L'ancienne montée de gradient (500 pas, taux 0,1) s'arrêtait à ~40 % du
    chemin : les logits d'un modèle quasi centré sont petits (|x| < 0,8), donc
    le gradient aussi. Elle rendait 0,586 là où l'optimum était -0,10.
    """
    logits = [_logit(p) for p, _ in rows]
    outcomes = [o for _, o in rows]

    def log_likelihood(scale: float) -> float:
        total = 0.0
        for x, y in zip(logits, outcomes):
            p = min(max(_sigmoid(scale * x), 1e-12), 1 - 1e-12)
            total += math.log(p if y else 1 - p)
        return total

    scale = 1.0
    for _ in range(iterations):
        probs = [_sigmoid(scale * x) for x in logits]
        gradient = sum((y - p) * x for x, y, p in zip(logits, outcomes, probs))
        hessian = sum(p * (1 - p) * x * x for x, p in zip(logits, probs))
        if hessian < 1e-12:
            break
        # Pas de Newton amorti : sur des logits saturés (0,9 gagnant une fois
        # sur deux) le pas plein oscille et diverge. On le divise par deux
        # tant qu'il ne fait pas monter la vraisemblance.
        step = gradient / hessian
        current = log_likelihood(scale)
        while abs(step) > 1e-9 and log_likelihood(scale + step) < current:
            step /= 2
        scale += step
        if abs(step) < 1e-9:
            break
    return scale


def scale_interval(
    rows: List[Row], confidence: float, resamples: int, seed: int = 0
) -> Tuple[float, float]:
    """Intervalle de confiance bootstrap de `suggest_scale` : refait l'ajustement
    sur `resamples` tirages avec remise. Graine fixe, pour que deux affichages
    du même diagnostic donnent le même intervalle."""
    rng = random.Random(seed)
    scales = sorted(suggest_scale([rng.choice(rows) for _ in rows]) for _ in range(resamples))
    tail = (1 - confidence) / 2
    return scales[int(tail * (resamples - 1))], scales[int((1 - tail) * (resamples - 1))]


def auc(scored: Sequence[Tuple[float, int]]) -> float:
    """Aire sous la courbe ROC de (score, outcome) : la probabilité qu'une
    victoire tirée au hasard ait un score plus haut qu'une défaite (0,5 =
    aucun pouvoir de discrimination). Insensible à l'échelle du score, ce qui
    permet de comparer des modèles non calibrés entre eux (SPEC-18).
    """
    wins = [score for score, outcome in scored if outcome == 1]
    losses = [score for score, outcome in scored if outcome == 0]
    if not wins or not losses:
        return 0.5
    pairs = sum((w > l) + 0.5 * (w == l) for w in wins for l in losses)
    return pairs / (len(wins) * len(losses))


Placed = Tuple[str, Optional[str]]  # (champion, lane)


def intrinsic_points(
    allies: Sequence[Placed],
    enemies: Sequence[Placed],
    strength: Dict[Optional[str], Dict[str, float]],
) -> float:
    """Écart de force intrinsèque entre les deux camps, en points de winrate
    (SPEC-18, terme de SPEC-05 §3.3 jamais implémenté).

    ``strength[lane][champion]`` est l'écart du winrate de lane rétréci à la
    moyenne de la lane. Un champion sans donnée sur sa lane vaut la moyenne (0).
    """

    def total(team: Sequence[Placed]) -> float:
        return sum(strength.get(lane, {}).get(champion, 0.0) for champion, lane in team)

    return total(allies) - total(enemies)
