"""Seuils de couleur de la pastille de l'éclaireur (SPEC-33 §2, tâche 155 amendée le 2026-10-14).

Quartiles des impacts ΔP moyens à 10 parties des joueurs de `crawl.db`, calculés hors client : la base
est ouverte en LECTURE SEULE (le Live Coach peut rester ouvert), chaque partie lue est passée par le
modèle de win chance comme le fait l'éclaireur (`form.player_impact`), puis chaque joueur garde ses
`SCOUT_BADGE_WINDOW` parties les plus récentes de la base.

Ce n'est pas un test : les chiffres dépendent de la base et du modèle. ~10 ms par partie.

USAGE:
    python scripts/measure_scout_quartiles.py
    python scripts/measure_scout_quartiles.py --limit 20000   # les 20 000 parties les plus récentes
"""

import argparse
import sqlite3
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.coaching.metrics import participant_roles
from src.config_winprob import winprob_config as cfg
from src.winprob.crawl import unpack
from src.winprob.impact import impacts
from src.winprob.train import crawl_path, load_model

PROGRESS_EVERY = 5000


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SPEC-33 : quartiles de la pastille de l'éclaireur"
    )
    parser.add_argument("--db-path", default=str(crawl_path()))
    parser.add_argument(
        "--limit", type=int, default=None, help="parties les plus récentes, au plus"
    )
    return parser.parse_args()


def main() -> None:
    """Parcourt les parties de la plus récente à la plus ancienne et imprime les quartiles."""
    args = _parse_args()
    model = load_model()
    if model is None:
        print("[ERREUR] Pas de modèle de win chance : python -m src.winprob.retrain --force")
        raise SystemExit(1)
    path = Path(args.db_path)
    if not path.exists():
        print(f"[ERREUR] Pas de base de collecte : {path}")
        raise SystemExit(1)

    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    window = cfg.SCOUT_BADGE_WINDOW
    points = defaultdict(list)  # puuid -> impacts, du plus récent au plus ancien
    began, seen, failed = time.monotonic(), 0, 0
    rows = db.execute(
        "SELECT raw FROM crawl_games WHERE length(raw) > 0 ORDER BY game_creation_utc DESC LIMIT ?",
        (args.limit if args.limit else -1,),
    )
    for (raw,) in rows:
        seen += 1
        if seen % PROGRESS_EVERY == 0:
            print(f"[INFO] {seen} parties en {time.monotonic() - began:.0f} s")
        try:
            packed = unpack(raw)
            game, timeline = packed["game"], packed["timeline"]
            if not (timeline or {}).get("frames"):
                continue
            puuid_of = {
                i["participantId"]: (i.get("player") or {}).get("puuid")
                for i in game.get("participantIdentities") or []
            }
            wanted = {pid for pid, p in puuid_of.items() if p and len(points[p]) < window}
            if not wanted:
                continue
            totals = defaultdict(float)
            for row in impacts(model, game, timeline, participant_roles(game))["rows"]:
                totals[row["participant_id"]] += row["delta_p"]
            for pid in wanted:
                points[puuid_of[pid]].append(100 * totals[pid])
        except Exception:  # pylint: disable=broad-exception-caught
            failed += 1  # partie illisible : ignorée, comme dans l'éclaireur
    db.close()

    means = [statistics.mean(v) for v in points.values() if len(v) >= window]
    print(
        f"[DATA] {seen} parties lues ({failed} illisibles) en {time.monotonic() - began:.0f} s, "
        f"{len(means)} joueurs à {window} parties"
    )
    if len(means) < 2:
        print("[ALERTE] Moins de deux joueurs à 10 parties : pas de quartiles.")
        return
    q1, median, q3 = statistics.quantiles(means, n=4)
    print(f"[DATA] Impacts à {window} parties : Q1 {q1:+.1f}, médiane {median:+.1f}, Q3 {q3:+.1f}")
    print(f"[DATA] SCOUT_IMPACT_QUARTILES = ({q1:.1f}, {q3:.1f})")


if __name__ == "__main__":
    main()
