"""Banc du résidu de `impacts()` sur les parties réelles (SPEC-22 §4.6, tâche 57).

Lit `data/db.db` en lecture seule, rejoue `impacts()` avec le modèle courant sur les parties
ayant une timeline, et imprime pour l'équipe du joueur le résidu non attribué (en points, ×100) :
moyenne, moyenne en valeur absolue, maximum en valeur absolue, puis ce que les lignes de
l'équipe portent hors événements de combat : objectifs perdus (`lost_*`), niveaux et respawn.

Ce n'est pas un test : les chiffres dépendent de la base réelle et du modèle entraîné.
Base de référence (avant SPEC-22) : −20,3 / 25,1 sur 45 parties (2026-10-04), −21,4 / 24,0 sur
les 108 parties de la base au 2026-10-13.

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
from src.winprob.impact import impacts  # noqa: E402
from src.winprob.model import WinModel  # noqa: E402
from src.winprob.train import model_path  # noqa: E402


def _points(value: float) -> str:
    """Probabilité en points (×100), format français à une décimale."""
    return f"{value * 100:.1f}".replace(".", ",")


def _carried(result: dict, teams: dict, team: int) -> dict:
    """Somme, pour l'équipe `team`, des lignes `lost_*`, `levels` et `respawn` de `impacts()`."""
    carried = {"objectifs perdus": 0.0, "niveaux": 0.0, "respawn": 0.0}
    for r in result["rows"]:
        if teams[r["participant_id"]] != team:
            continue
        label = "objectifs perdus" if r["event_type"].startswith("lost_") else r["event_type"]
        label = {"levels": "niveaux"}.get(label, label)
        if label in carried:
            carried[label] += r["delta_p"]
    return carried


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

    residuals, carried = [], []
    for game, timeline, team in games:
        result = impacts(model, game, timeline)
        residual = result["teams"].get(team, {}).get("unattributed", 0.0)
        teams = {p["participantId"]: p["teamId"] for p in game["participants"]}
        residuals.append(residual)
        carried.append(_carried(result, teams, team))

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
    parts = ", ".join(f"{k} {_points(sum(c[k] for c in carried) / n)}" for k in carried[0])
    print(f"[DATA] Porté par les lignes de l'équipe (moyenne, pts) : {parts}")


if __name__ == "__main__":
    main()
