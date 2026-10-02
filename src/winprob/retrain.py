"""Réentraînement déclenché par les données, champion contre challenger (SPEC-20 §4.4).

    python -m src.winprob.retrain          # si un déclencheur est atteint
    python -m src.winprob.retrain --force  # commande manuelle (`entrainer`)

Pas de réentraînement après chaque partie : la collecte grossit la base quoi que fasse
le joueur. Le modèle en place sert jusqu'à son remplacement ; le challenger n'est adopté
que s'il fait au moins aussi bien sur les parties les plus récentes, jamais entraînées.
"""

import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from ..config_winprob import winprob_config as cfg
from .crawl import _patch
from .model import WinModel, evaluate, fit
from .train import crawl_path, load, model_path


def patch_counts(path: Optional[Path] = None) -> Dict[str, int]:
    """Parties lues par patch ('16.19' -> 4 120)."""
    db = sqlite3.connect(path or crawl_path())
    rows = db.execute(
        "SELECT game_version FROM crawl_games WHERE length(raw) > 0 AND game_version IS NOT NULL"
    )
    return dict(Counter(".".join(map(str, _patch(v))) for (v,) in rows if _patch(v)))


def should_retrain(meta: Optional[dict], counts: Dict[str, int]) -> Optional[str]:
    """Raison du réentraînement, None s'il n'y en a pas. `meta` : `games` et `patch` du champion."""
    total = sum(counts.values())
    if not meta:
        return "aucun modèle" if total >= cfg.WINPROB_MIN_PATCH_GAMES else None
    latest = max(counts, key=lambda p: tuple(map(int, p.split("."))), default=None)
    if latest and latest != meta["patch"] and counts[latest] >= cfg.WINPROB_MIN_PATCH_GAMES:
        return f"nouveau patch {latest}"
    new = total - meta["games"]
    if (
        new >= cfg.WINPROB_RETRAIN_MIN_NEW_GAMES
        and new >= meta["games"] * cfg.WINPROB_RETRAIN_GROWTH
    ):
        return f"+{new} parties depuis le dernier entraînement"
    return None


def adopt(champion: dict, challenger: dict) -> bool:
    """Au moins aussi bien : Brier non dégradé, calibration non dégradée ou dans le seuil."""
    return challenger["brier"] <= champion["brier"] and (
        challenger["max_gap"] <= champion["max_gap"] or challenger["max_gap"] <= cfg.WINPROB_GAP_MAX
    )


def retrain(force: bool = False, path: Optional[Path] = None, out: Optional[Path] = None) -> str:
    """Réentraîne si un déclencheur est atteint ; renvoie la ligne de journal."""
    out = out or model_path()
    champion = WinModel.from_json(out.read_text(encoding="utf-8")) if out.exists() else None
    counts = patch_counts(path)
    reason = "manuel" if force else should_retrain(champion and champion.meta, counts)
    if reason is None:
        return "Pas de réentraînement : aucun déclencheur atteint"
    (train_x, train_y), (val_x, val_y) = load(path)
    challenger = fit(train_x, train_y)
    new = evaluate(challenger, val_x, val_y)
    if champion:
        old = evaluate(champion, val_x, val_y)
        ok = adopt(old, new)
        verdict = f"champion {old['brier']:.4f} / {old['max_gap'] * 100:.1f} pts"
    else:
        ok, verdict = new["accepted"], "sans champion, seuils du §11.2"
    line = (
        f"{reason} : challenger {challenger.version} {new['brier']:.4f} / {new['max_gap'] * 100:.1f} pts "
        f"contre {verdict} → {'ADOPTÉ' if ok else 'jeté'}"
    )
    if ok:
        total = sum(counts.values())
        latest = max(counts, key=lambda p: tuple(map(int, p.split("."))))
        challenger.meta = {
            "games": total,
            "patch": latest,
            "trained": datetime.now(timezone.utc).isoformat(),
        }
        out.write_text(challenger.to_json(), encoding="utf-8")
    with out.with_suffix(".log").open("a", encoding="utf-8") as journal:
        journal.write(f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M} {line}\n")
    return line


if __name__ == "__main__":
    print(retrain(force="--force" in sys.argv))
