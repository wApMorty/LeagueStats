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
from .model import INPUTS, WinModel, evaluate, fit
from .state import blue_win, frame_states

Rows = Tuple[List[dict], List[int]]  # (états, victoire bleue)


def crawl_path() -> Path:
    return Path(config.DATABASE_PATH).with_name(cfg.CRAWL_DB_FILENAME)


def model_path() -> Path:
    return Path(config.DATABASE_PATH).with_name(cfg.WINPROB_MODEL_FILENAME)


def load(path: Optional[Path] = None, seed: int = 0) -> Tuple[Rows, Rows]:
    """(entraînement, validation) : la validation prend les parties les plus récentes.

    Découpage par partie, jamais par image (SPEC-20 §4.3) ; les images sont tirées au
    hasard si elles dépassent `WINPROB_MAX_ROWS`.
    """
    db = sqlite3.connect(path or crawl_path())
    ids = [
        row[0]
        for row in db.execute(
            "SELECT game_id FROM crawl_games WHERE length(raw) > 0 "
            "ORDER BY game_creation_utc, game_id"
        )
    ]
    cut = int(len(ids) * (1 - cfg.WINPROB_VALIDATION_FRACTION))
    keep = min(1.0, cfg.WINPROB_MAX_ROWS / max(1, len(ids) * 28))  # ~28 images par partie
    rng, out = random.Random(seed), (([], []), ([], []))
    for i, game_id in enumerate(ids):
        raw = db.execute("SELECT raw FROM crawl_games WHERE game_id = ?", (game_id,)).fetchone()[0]
        d = unpack(raw)
        win = blue_win(d["game"])
        if not d["timeline"] or win is None or d["game"].get("gameDuration", 0) < 300:
            continue  # sans timeline, issue inconnue ou remake
        states, wins = out[int(i >= cut)]
        for state in frame_states(d["game"], d["timeline"]):
            if rng.random() < keep:
                states.append(state)
                wins.append(int(win))
    return out


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
    print(f"Version du modèle : {model.version}")
    if save:
        model_path().write_text(model.to_json(), encoding="utf-8")
        print(f"Écrit : {model_path()}")
    return model


if __name__ == "__main__":
    report(save="--save" in sys.argv)
