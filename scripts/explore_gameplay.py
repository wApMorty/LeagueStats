"""Exploration des parties capturées (SPEC-19 phase 2, tâche 32).

Pour chaque rôle et chaque métrique de la grille : distribution, et lien avec
la victoire mesuré par l'écart standardisé (d de Cohen) entre victoires et
défaites, orienté par le sens de la métrique (d > 0 : la métrique va du bon
côté quand on gagne). Deux lectures :

- tous les participants de tes parties, par rôle (~2 valeurs par partie) ;
- toi seul, sur ton rôle principal.

Une métrique qui ne sépare pas les victoires des défaites perd son rang dans
la grille (§5.1). Lecture seule.

USAGE:
    python scripts/explore_gameplay.py
    python scripts/explore_gameplay.py --db-path data/db.db
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, stdev

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.coaching.grid import GRID  # noqa: E402
from src.coaching.metrics import METRICS, compute_metrics  # noqa: E402
from src.config import config  # noqa: E402
from src.db import Database  # noqa: E402


def cohen_d(wins, losses):
    """Écart standardisé entre deux échantillons, None si incalculable."""
    if len(wins) < 2 or len(losses) < 2:
        return None
    pooled = (
        ((len(wins) - 1) * stdev(wins) ** 2 + (len(losses) - 1) * stdev(losses) ** 2)
        / (len(wins) + len(losses) - 2)
    ) ** 0.5
    return (mean(wins) - mean(losses)) / pooled if pooled else None


def load(db):
    """(lignes de métriques avec victoire, participant du joueur) par partie."""
    cursor = db.connection.cursor()
    cursor.execute(
        "SELECT game_id, player_participant_id, raw_game, raw_timeline, raw_eog "
        "FROM game_records ORDER BY game_creation_utc"
    )
    games = []
    for game_id, player_pid, raw_game, raw_timeline, raw_eog in cursor.fetchall():
        game = json.loads(raw_game)
        rows = compute_metrics(
            game,
            json.loads(raw_timeline) if raw_timeline else None,
            json.loads(raw_eog) if raw_eog else None,
        )
        wins = {p["participantId"]: p["stats"]["win"] for p in game["participants"]}
        games.append((game_id, player_pid, rows, wins))
    return games


def table(title, samples):
    """samples : {(rôle, métrique): ([victoires], [défaites])}."""
    print(f"\n{title}")
    print(f"{'rôle':<8}{'métrique':<28}{'n':>4}{'moy. V':>10}{'moy. D':>10}{'d':>7}  poids")
    for (role, metric), (wins, losses) in sorted(samples.items()):
        d = cohen_d(wins, losses)
        d_oriented = None if d is None else d * METRICS[metric].sense
        fmt = METRICS[metric].fmt.replace(".0f", ".1f")  # moyennes de comptes
        print(
            f"{role:<8}{METRICS[metric].label[:27]:<28}{len(wins) + len(losses):>4}"
            f"{fmt.format(mean(wins)) if wins else '-':>10}"
            f"{fmt.format(mean(losses)) if losses else '-':>10}"
            f"{'-' if d_oriented is None else f'{d_oriented:+.2f}':>7}"
            f"  {GRID.get(role, {}).get(metric, '')}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="SPEC-19 : exploration des parties capturées")
    parser.add_argument("--db-path", default=config.DATABASE_PATH)
    args = parser.parse_args()

    db = Database(args.db_path)
    db.connect()
    games = load(db)
    db.close()

    everyone = defaultdict(lambda: ([], []))
    player = defaultdict(lambda: ([], []))
    player_roles = Counter()
    unknown_roles = 0
    for _, player_pid, rows, wins in games:
        for row in rows:
            if row.role is None:
                unknown_roles += 1
                continue
            bucket = 0 if wins[row.participant_id] else 1
            everyone[(row.role, row.metric)][bucket].append(row.value)
            if row.participant_id == player_pid:
                player[(row.role, row.metric)][bucket].append(row.value)
                player_roles[row.role] += row.metric == "cs_per_min"

    print(f"{len(games)} parties, rôles joués : {dict(player_roles)}")
    print(f"Lignes sans poste : {unknown_roles}")
    table("TOUS LES PARTICIPANTS, PAR RÔLE", everyone)
    main_role = player_roles.most_common(1)[0][0] if player_roles else None
    table(
        f"TOI SEUL ({main_role})",
        {key: value for key, value in player.items() if key[0] == main_role},
    )
    print("\nd : écart standardisé victoires - défaites, orienté (d > 0 = bon sens).")
    print("Repères usuels : 0,2 faible, 0,5 moyen, 0,8 fort.")


if __name__ == "__main__":
    main()
