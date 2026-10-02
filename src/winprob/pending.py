"""Impacts des parties capturées du joueur, calculés après coup (SPEC-20 §5, tâche 44)."""

import json
from pathlib import Path
from typing import List, Optional, Tuple

from ..repositories.coaching import CoachingRepository
from .impact import impacts
from .model import WinModel
from .report import impact_report
from .train import model_path


def compute_pending(db, path: Optional[Path] = None) -> List[Tuple[int, List[str]]]:
    """Calcule et range l'impact des parties sans impact ; renvoie (game_id, rapport) de chacune.

    Sans modèle entraîné (`python -m src.winprob.retrain --force`), ne fait rien. Une partie
    au brut illisible ou sans événement est passée : elle ne doit pas bloquer les suivantes.
    """
    path = path or model_path()
    if not path.exists():
        return []
    model = WinModel.from_json(path.read_text(encoding="utf-8"))
    repo = CoachingRepository(db)
    done = []
    for g in repo.games_without_impact():
        try:
            game, timeline = json.loads(g["game"]), json.loads(g["timeline"])
            result = impacts(model, game, timeline)
            pid = g["player_pid"]
            lines = impact_report(model, game, timeline, pid, result) if pid else []
        except (KeyError, TypeError, ValueError):
            continue
        if result["rows"]:
            repo.save_impact(g["game_id"], model.version, result["rows"])
            done.append((g["game_id"], lines))
    return done
