"""Régression logistique de la win chance, en Python pur (SPEC-20 §4, tâche 42).

Variables de `state.py` (différences bleu − rouge) et leurs produits avec le temps,
pour qu'un écart de kills pèse différemment à 10 et à 30 min. Ajustée par Newton à
hessienne sous-échantillonnée, sur variables centrées-réduites.
"""

import hashlib
import json
import math
from typing import Iterable, List, Optional, Sequence, Tuple

from ..analysis.calibration import brier_score
from ..config_winprob import winprob_config as cfg
from .state import FEATURES

# Variables du modèle : tout sauf le temps, qui n'entre que par les produits.
INPUTS = tuple(name for name in FEATURES if name != "time_min")
TIME_SCALE_MIN = 30.0


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(min(x, 30.0), -30.0)))


def expand(state: dict, inputs: Sequence[str] = INPUTS) -> List[float]:
    """Vecteur du modèle : variables, puis variables × temps."""
    base = [state[name] for name in inputs]
    t = state["time_min"] / TIME_SCALE_MIN
    return base + [value * t for value in base]


def _solve(a: List[List[float]], b: List[float]) -> List[float]:
    """Résout a·x = b (élimination de Gauss avec pivot partiel)."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


class WinModel:
    def __init__(
        self,
        inputs: Sequence[str],
        mean: List[float],
        scale: List[float],
        weights: List[float],
        meta: Optional[dict] = None,
    ):
        self.inputs = tuple(inputs)
        self.mean, self.scale, self.weights = mean, scale, weights  # weights : dernier = biais
        digest = hashlib.sha1(json.dumps([self.inputs, weights]).encode()).hexdigest()
        self.version = f"wp-{digest[:8]}"
        self.meta = meta  # parties, patch et date de l'entraînement (retrain.py)

    def _z(self, state: dict) -> List[float]:
        x = expand(state, self.inputs)
        return [(v - m) / s for v, m, s in zip(x, self.mean, self.scale)]

    def predict(self, state: dict) -> float:
        """Probabilité que l'équipe bleue gagne."""
        z = self._z(state)
        return _sigmoid(sum(w * v for w, v in zip(self.weights, z)) + self.weights[-1])

    def to_json(self) -> str:
        return json.dumps(
            {
                "inputs": self.inputs,
                "mean": self.mean,
                "scale": self.scale,
                "weights": self.weights,
                "meta": self.meta,
            }
        )

    @classmethod
    def from_json(cls, text: str) -> "WinModel":
        d = json.loads(text)
        return cls(d["inputs"], d["mean"], d["scale"], d["weights"], d.get("meta"))


def fit(states: Sequence[dict], wins: Sequence[int], inputs: Sequence[str] = INPUTS) -> WinModel:
    """Ajuste la logistique sur des images (état, victoire bleue)."""
    rows = [expand(s, inputs) for s in states]
    d, n = len(rows[0]), len(rows)
    mean = [sum(r[j] for r in rows) / n for j in range(d)]
    scale = [math.sqrt(sum((r[j] - mean[j]) ** 2 for r in rows) / n) or 1.0 for j in range(d)]
    z = [[(r[j] - mean[j]) / scale[j] for j in range(d)] + [1.0] for r in rows]  # biais en dernier
    del rows
    step = max(1, n // cfg.WINPROB_HESSIAN_ROWS)
    sample = z[::step]
    w = [0.0] * (d + 1)
    for _ in range(cfg.WINPROB_ITERATIONS):
        grad = [cfg.WINPROB_L2 * w[j] if j < d else 0.0 for j in range(d + 1)]
        for row, y in zip(z, wins):
            err = _sigmoid(sum(a * b for a, b in zip(w, row))) - y
            for j in range(d + 1):
                grad[j] += err * row[j] / n
        hess = [
            [(cfg.WINPROB_L2 if i == j < d else 0.0) for j in range(d + 1)] for i in range(d + 1)
        ]
        for row in sample:
            p = _sigmoid(sum(a * b for a, b in zip(w, row)))
            weight = p * (1 - p) / len(sample)
            for i in range(d + 1):
                f = weight * row[i]
                for j in range(i, d + 1):
                    hess[i][j] += f * row[j]
        for i in range(d + 1):
            for j in range(i):
                hess[i][j] = hess[j][i]
        delta = _solve(hess, grad)
        w = [a - b for a, b in zip(w, delta)]
        if max(abs(x) for x in delta) < 1e-4:
            break
    return WinModel(inputs, mean, scale, w)


def score(predictions: Iterable[Tuple[float, int, float]]) -> dict:
    """Brier et écart de calibration par décile sur des (probabilité, issue, minute),
    images après `WINPROB_EVAL_AFTER_MIN`."""
    rows: List[Tuple[float, int]] = sorted(
        (p, y) for p, y, minute in predictions if minute >= cfg.WINPROB_EVAL_AFTER_MIN
    )
    n = len(rows)
    gaps = []
    for k in range(10):
        decile = rows[k * n // 10 : (k + 1) * n // 10]
        if decile:
            gaps.append(abs(sum(p for p, _ in decile) - sum(y for _, y in decile)) / len(decile))
    brier = brier_score(rows)
    return {
        "images": n,
        "brier": brier,
        "max_gap": max(gaps),
        "accepted": brier <= cfg.WINPROB_BRIER_MAX and max(gaps) <= cfg.WINPROB_GAP_MAX,
    }


def evaluate(model: WinModel, states: Sequence[dict], wins: Sequence[int]) -> dict:
    return score((model.predict(s), y, s["time_min"]) for s, y in zip(states, wins))
