"""Recalcule game_metrics et game_findings depuis game_records (SPEC-19 §8).

Sans appel LCU : le brut stocké suffit. L'objectif OneTricks est relu (une
requête par champion et poste). Le Live Coach fait déjà ce recalcul au
démarrage quand `coaching_config.GRID_VERSION` change ; ce script le force,
par exemple après une correction de métrique sans changement de version.
Les axes de travail et leurs verdicts sont conservés.

USAGE:
    python scripts/recompute_coaching.py
    python scripts/recompute_coaching.py --db-path data/db.db
"""

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.coaching.findings import analyze_pending  # noqa: E402
from src.config import config  # noqa: E402
from src.db import Database  # noqa: E402
from src.repositories.coaching import CoachingRepository  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="SPEC-19 : recalcul de l'analyse des parties")
    parser.add_argument("--db-path", default=config.DATABASE_PATH)
    args = parser.parse_args()

    db = Database(args.db_path)
    db.connect()
    try:
        CoachingRepository(db).clear_analysis()
        analyses = analyze_pending(db)
        findings = sum(len(a.negatives) + len(a.positives) for a in analyses)
        print(f"[OK] {len(analyses)} parties analysées, {findings} constats")
    finally:
        db.close()


if __name__ == "__main__":
    main()
