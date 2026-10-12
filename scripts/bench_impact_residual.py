"""Banc du résidu de `impacts()` sur les parties réelles (SPEC-22 §4.6, tâche 57).

Lit `data/db.db` en lecture seule, rejoue `impacts()` avec le modèle courant sur les parties
ayant une timeline, et imprime pour l'équipe du joueur le résidu non attribué (en points, ×100) :
moyenne, moyenne en valeur absolue, maximum en valeur absolue, puis sa composition :
objectifs pris par l'équipe adverse (somme du ΔP des événements qu'elle marque) et dérive
(résidu moins objectifs adverses).

Ce n'est pas un test : les chiffres dépendent de la base réelle et du modèle entraîné.
Base de référence au §1 de SPEC-22 : −20,3 / 25,1 sur 45 parties (2026-10-04).

USAGE:
    python scripts/bench_impact_residual.py
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import config  # noqa: E402
from src.winprob.impact import event_kind, impacts, scoring_team  # noqa: E402
from src.winprob.model import WinModel  # noqa: E402
from src.winprob.state import BLUE, transitions  # noqa: E402
from src.winprob.train import model_path  # noqa: E402


def _points(value: float) -> str:
    """Probabilité en points (×100), format français à une décimale."""
    return f"{value * 100:.1f}".replace(".", ",")


def _side(team: int, delta: float) -> float:
    """ΔP d'un événement orienté du point de vue de `team` (même convention que `impacts()`)."""
    return delta if team == BLUE else -delta


def _objectives_against(
    model: WinModel, game: dict, timeline: dict, team: int, teams: dict
) -> float:
    """Somme du ΔP des objectifs (hors kills) marqués par l'équipe adverse, orienté `team`."""
    total = 0.0
    for e, before, after in transitions(game, timeline):
        if event_kind(e) == "kill":
            continue
        scorer = scoring_team(e, teams)
        if scorer is None or scorer == team:
            continue
        total += _side(team, model.predict(after) - model.predict(before))
    return total


def _read_games(conn: sqlite3.Connection) -> Tuple[List[Tuple[dict, dict, int]], int]:
    """Parties avec timeline lisibles : (partie, timeline, équipe du joueur), et nombre ignoré."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT raw_game, raw_timeline, player_participant_id FROM game_records "
        "WHERE raw_timeline IS NOT NULL ORDER BY game_creation_utc"
    )
    games, skipped = [], 0
    for raw_game, raw_timeline, pid in cursor.fetchall():
        try:
            game, timeline = json.loads(raw_game), json.loads(raw_timeline)
        except (json.JSONDecodeError, TypeError):
            skipped += 1
            continue
        team = _player_team(game, pid)
        if team is None:
            skipped += 1
            continue
        games.append((game, timeline, team))
    return games, skipped


def _player_team(game: dict, pid: Optional[int]) -> Optional[int]:
    """Équipe du joueur suivi dans la partie, None si son participant est absent."""
    for p in game.get("participants", []):
        if p.get("participantId") == pid:
            return p.get("teamId")
    return None


def main() -> None:
    """Imprime le résidu de l'équipe du joueur sur les parties de la base réelle."""
    db_path = Path(config.DATABASE_PATH).resolve()
    model = WinModel.from_json(model_path().read_text(encoding="utf-8"))
    conn = sqlite3.connect(f"{db_path.as_uri()}?mode=ro", uri=True)
    try:
        games, skipped = _read_games(conn)
    finally:
        conn.close()

    residuals, objectives, drifts = [], [], []
    for game, timeline, team in games:
        result = impacts(model, game, timeline)
        residual = result["teams"].get(team, {}).get("unattributed", 0.0)
        teams = {p["participantId"]: p["teamId"] for p in game["participants"]}
        against = _objectives_against(model, game, timeline, team, teams)
        residuals.append(residual)
        objectives.append(against)
        drifts.append(residual - against)

    n = len(residuals)
    print(f"[DATA] Modèle {model.version}, parties avec timeline rejouées : {n}")
    if skipped:
        print(f"[INFO] Parties ignorées (JSON illisible ou joueur absent) : {skipped}")
    if n == 0:
        print("[ERREUR] Aucune partie exploitable")
        return
    mean = sum(residuals) / n
    absolute = sum(abs(r) for r in residuals) / n
    maximum = max(abs(r) for r in residuals)
    print(
        f"[DATA] Résidu équipe du joueur (pts) : moyenne {_points(mean)}, "
        f"valeur absolue {_points(absolute)}, maximum en valeur absolue {_points(maximum)}"
    )
    print(
        f"[DATA] Composition (moyenne, pts) : objectifs adverses "
        f"{_points(sum(objectives) / n)}, dérive {_points(sum(drifts) / n)}"
    )


if __name__ == "__main__":
    main()
