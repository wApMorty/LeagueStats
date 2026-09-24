"""Faut-il ajouter la force intrinsèque au modèle ? (SPEC-18, approche C)

Rejoue les parties labellisées de la table ``predictions`` et compare :

    1. le modèle tel qu'il a prédit (``predicted_probability`` stockée) ;
    2. la force intrinsèque seule (winrate de lane rétréci, allié − ennemi) ;
    3. les deux ensemble : logit stocké + terme de force intrinsèque,
       c'est-à-dire le modèle de SPEC-05 §3.3 tel qu'il était spécifié.

Critères : AUC (pouvoir de discrimination, insensible à la calibration) et
Brier. L'écart d'AUC (3 − 1) est donné avec un intervalle bootstrap à 90 % :
tant qu'il contient 0, les données ne tranchent pas.

Approximations :
- La lane des ennemis n'est pas journalisée : on prend leur lane principale
  (``champion_lanes``).
- Les winrates sont ceux de la base actuelle, pas ceux du jour de la partie.

Script en lecture seule : il n'écrit rien, ni en base ni dans la config.

USAGE:
    python scripts/compare_intrinsic_strength.py
    python scripts/compare_intrinsic_strength.py --db-path data/db.db
"""

import argparse
import random
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.calibration import auc, brier_score, intrinsic_points
from src.analysis.probability import logit, sigmoid, winrate_points_to_logit
from src.analysis.shrink import shrunk_lane_winrates
from src.config import config
from src.config_constants import analysis_config, scraping_config
from src.db import Database

BOOTSTRAP_DRAWS = 2000


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--db-path", default=config.DATABASE_PATH)
    return parser.parse_args()


def _lane_strength(db) -> dict:
    """{lane: {champion: winrate rétréci − moyenne de la lane}}."""
    strength = {}
    for lane in scraping_config.LANES:
        raw = db.get_lane_winrates(lane)
        total = sum(games for _, games in raw.values())
        if not total:
            continue
        mean = sum(winrate * games for winrate, games in raw.values()) / total
        strength[lane] = {
            name: value - mean for name, value in shrunk_lane_winrates(db, lane).items()
        }
    return strength


def _load_games(db) -> list:
    """[(allies, enemies, predicted_probability, outcome)] des parties labellisées."""
    names = db.get_all_champion_names()
    main_lane = {
        champion_id: max(shares, key=shares.get)
        for champion_id, shares in db.get_all_champion_lane_distributions().items()
        if shares
    }
    cursor = db.connection.cursor()
    cursor.execute(
        "SELECT ally_champions, enemy_champions, ally_lanes, predicted_probability, outcome "
        "FROM predictions WHERE outcome IS NOT NULL"
    )
    games = []
    for ally_ids, enemy_ids, ally_lanes, probability, outcome in cursor.fetchall():
        allies = [
            (names.get(int(i)), lane)
            for i, lane in zip(ally_ids.split(","), (ally_lanes or "").split(","))
        ]
        enemies = [(names.get(int(i)), main_lane.get(int(i))) for i in enemy_ids.split(",")]
        games.append((allies, enemies, probability, outcome))
    return games


def main() -> None:
    args = _parse_args()
    db = Database(args.db_path)
    db.connect()
    try:
        strength = _lane_strength(db)
        games = _load_games(db)
    finally:
        db.close()

    print(f"[INTRINSIC] {len(games)} parties labellisées (toutes versions du modèle).")
    if len(games) < analysis_config.MIN_ROWS_FOR_CALIBRATION:
        print("[INTRINSIC] Trop peu de parties pour conclure quoi que ce soit.")
        return

    rows = []  # (proba stockée, écart intrinsèque en points, proba combinée, outcome)
    for allies, enemies, probability, outcome in games:
        points = intrinsic_points(allies, enemies, strength)
        combined = sigmoid(logit(probability) + winrate_points_to_logit(points))
        rows.append((probability, points, combined, outcome))

    def aucs(sample):
        return (
            auc([(p, o) for p, _, _, o in sample]),
            auc([(x, o) for _, x, _, o in sample]),
            auc([(c, o) for _, _, c, o in sample]),
        )

    stored, alone, combined = aucs(rows)
    print(f"  AUC modèle actuel           : {stored:.3f}")
    print(f"  AUC force intrinsèque seule : {alone:.3f}")
    print(f"  AUC modèle + force          : {combined:.3f}")
    print(f"  Brier modèle actuel         : {brier_score([(p, o) for p, _, _, o in rows]):.4f}")
    print(f"  Brier modèle + force        : {brier_score([(c, o) for _, _, c, o in rows]):.4f}")

    rng = random.Random(0)
    gains = []
    for _ in range(BOOTSTRAP_DRAWS):
        sample = [rng.choice(rows) for _ in rows]
        base, _, with_force = aucs(sample)
        gains.append(with_force - base)
    gains.sort()
    low, high = gains[BOOTSTRAP_DRAWS // 20], gains[-BOOTSTRAP_DRAWS // 20]
    print(f"\n[INTRINSIC] Gain d'AUC en ajoutant la force : {combined - stored:+.3f}")
    print(f"[INTRINSIC] IC 90 % bootstrap : [{low:+.3f}, {high:+.3f}]")
    if low > 0:
        print("[INTRINSIC] Le gain est significatif : SPEC-18 phase B peut être rouverte.")
    else:
        print("[INTRINSIC] L'intervalle contient 0 : les données ne tranchent pas encore.")


if __name__ == "__main__":
    main()
