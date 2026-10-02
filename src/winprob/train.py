"""Entraînement et validation du modèle de win chance depuis `crawl.db` (SPEC-20 §4.3).

python -m src.winprob.train          # rapport seul
python -m src.winprob.train --save   # écrit data/winprob_model.json
"""

import random
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from ..config import config
from ..config_winprob import winprob_config as cfg
from .crawl import unpack
from .model import INPUTS, WinModel, evaluate, fit, score
from .state import blue_win, frame_states

Rows = Tuple[List[dict], List[int]]  # (états, victoire bleue)


def crawl_path() -> Path:
    return Path(config.DATABASE_PATH).with_name(cfg.CRAWL_DB_FILENAME)


def model_path() -> Path:
    return Path(config.DATABASE_PATH).with_name(cfg.WINPROB_MODEL_FILENAME)


def games(path: Optional[Path] = None, seed: int = 0) -> List[Tuple[List[dict], int]]:
    """Parties lues, de la plus ancienne à la plus récente : (images tirées, victoire bleue).

    Les images sont tirées au hasard si elles dépassent `WINPROB_MAX_ROWS` ; les parties
    sans timeline, sans issue ou de moins de 5 min (remakes) sont écartées.
    """
    db = sqlite3.connect(path or crawl_path())
    query = "FROM crawl_games WHERE length(raw) > 0"
    keep = min(
        1.0,
        cfg.WINPROB_MAX_ROWS / max(1, db.execute(f"SELECT COUNT(*) {query}").fetchone()[0] * 28),
    )
    rng, out = random.Random(seed), []  # ~28 images par partie
    for (raw,) in db.execute(f"SELECT raw {query} ORDER BY game_creation_utc, game_id"):
        d = unpack(raw)
        win = blue_win(d["game"])
        if d["timeline"] and win is not None and d["game"].get("gameDuration", 0) >= 300:
            states = [s for s in frame_states(d["game"], d["timeline"]) if rng.random() < keep]
            out.append((states, int(win)))
    return out


def _flatten(parts: List[Tuple[List[dict], int]]) -> Rows:
    return [s for states, _ in parts for s in states], [w for states, w in parts for _ in states]


def load(path: Optional[Path] = None, seed: int = 0) -> Tuple[Rows, Rows]:
    """(entraînement, validation) : la validation prend les parties les plus récentes.

    Découpage par partie, jamais par image (SPEC-20 §4.3).
    """
    parts = games(path, seed)
    cut = int(len(parts) * (1 - cfg.WINPROB_VALIDATION_FRACTION))
    return _flatten(parts[:cut]), _flatten(parts[cut:])


def cross_validate(path: Optional[Path] = None, folds: int = 5) -> dict:
    """Validation croisée par blocs contigus de parties (SPEC-20 §4.3), prédictions poolées.

    Chaque bloc est prédit par un modèle entraîné sur les autres ; le décile se mesure sur
    toutes les parties à la fois, où le bruit d'un bloc de ~1 000 parties (2 à 6 pts
    d'écart pour un même modèle) se dilue.
    """
    parts = games(path)
    n, pooled = len(parts), []
    for k in range(folds):
        lo, hi = k * n // folds, (k + 1) * n // folds
        train_x, train_y = _flatten(parts[:lo] + parts[hi:])
        model = fit(train_x, train_y)
        pooled += [
            (model.predict(s), win, s["time_min"]) for states, win in parts[lo:hi] for s in states
        ]
    return score(pooled)


def report(path: Optional[Path] = None, save: bool = False) -> WinModel:
    (train_x, train_y), (val_x, val_y) = load(path)
    model = fit(train_x, train_y)
    with_gold = fit(train_x, train_y, INPUTS + ("gold",))
    base = sum(val_y) / len(val_y)
    print(f"Entraînement {len(train_x)} images, validation {len(val_x)} images (parties récentes)")
    for label, m in (("sans l'or", model), ("avec l'or", with_gold)):
        r = evaluate(m, val_x, val_y)
        print(
            f"  {label:10s} Brier {r['brier']:.4f}  écart max par décile {r['max_gap'] * 100:.1f} pts"
            f"  {'ACCEPTÉ' if r['accepted'] else 'REFUSÉ'}"
        )
    print(f"  Référence : taux de victoire bleue constant, Brier {base * (1 - base):.4f}")
    cv = cross_validate(path)
    print(
        f"  Validation croisée à 5 blocs (poolée) : Brier {cv['brier']:.4f}  écart max par décile "
        f"{cv['max_gap'] * 100:.1f} pts  {'ACCEPTÉ' if cv['accepted'] else 'REFUSÉ'}"
    )
    print(f"Version du modèle : {model.version}")
    if save:
        model_path().write_text(model.to_json(), encoding="utf-8")
        print(f"Écrit : {model_path()}")
    return model


if __name__ == "__main__":
    report(save="--save" in sys.argv)
