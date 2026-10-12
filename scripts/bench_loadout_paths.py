"""Banc SPEC-31 : « Situationnels » avant / après le chemin du core, sur 12 pages OneTricks.

À lancer à la main, une seule fois (12 requêtes espacées de 20 s, soit ~4 min : hors du
volume de la boucle de draft qui fonde ADR-003, sous le plafond mesuré par le spike de
SPEC-15, blocage à ~17 pages en 5 min).

    python scripts/bench_loadout_paths.py

Par page : situationnels de l'ancien calcul (``popularItems``) et du nouveau (suites du
core), nombre d'items hors du chemin du core dans chacun, repli ou non. Synthèse : items
hors chemin avant / après (après : 0 attendu), taux de repli, nombre médian de situationnels.
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.draft import loadout  # noqa: E402

# (champion, lane) : trois pages mesurées dans la spec, puis neuf postes variés. Pas de support :
# OneTricks nomme ce poste « supp » et `LANE_TO_ONETRICKS_ROLE` ne le traduit pas (404).
PAGES = (
    ("Ambessa", "top"),
    ("Yorick", "top"),
    ("Jinx", "bottom"),
    ("Darius", "top"),
    ("Garen", "top"),
    ("Lee Sin", "jungle"),
    ("Viego", "jungle"),
    ("Ahri", "middle"),
    ("Orianna", "middle"),
    ("Kai'Sa", "bottom"),
    ("Ezreal", "bottom"),
    ("Syndra", "middle"),
)
DELAY_SECONDS = 20


def measure(champion: str, lane: str) -> dict:
    """Situationnels avant / après pour une page, ou {"error": ...} si elle manque."""
    page = loadout.get_page(champion, lane)
    if page is None:
        return {"error": "page indisponible"}
    stats = page["firstItemStats"]["all"]["all"]
    chosen = loadout._chosen_items(stats)
    games = int(page["patchStats"]["all"])
    path = loadout._core_path(stats, games, chosen["Core"][0])
    before = dict(loadout._item_blocks(stats, chosen))["Situationnels"]
    after = dict(loadout._item_blocks(stats, chosen, path=path))["Situationnels"]
    followers = {item for item, _, _ in path or []}
    names = page["itemData"]
    return {
        "core_games": loadout.pick_build(page).path_games,
        "fallback": path is None,
        "before": [names.get(str(i), i) for i in before],
        "after": [names.get(str(i), i) for i in after],
        "off_before": sum(item not in followers for item in before),
        "off_after": 0 if path is None else sum(item not in followers for item in after),
    }


def main() -> None:
    rows = []
    for index, (champion, lane) in enumerate(PAGES):
        if index:
            time.sleep(DELAY_SECONDS)
        row = measure(champion, lane)
        rows.append(row)
        print(f"[DATA] {champion} {lane} : {row}")
    ok = [row for row in rows if "error" not in row]
    if not ok:
        print("[ERREUR] aucune page lue")
        return
    print(f"[DATA] pages lues : {len(ok)} / {len(rows)}")
    print(f"[DATA] items hors chemin avant : {sum(row['off_before'] for row in ok)}")
    print(f"[DATA] items hors chemin après : {sum(row['off_after'] for row in ok)}")
    print(f"[DATA] repli : {sum(row['fallback'] for row in ok)} / {len(ok)}")
    print(f"[DATA] situationnels médian avant : {statistics.median(len(r['before']) for r in ok)}")
    print(f"[DATA] situationnels médian après : {statistics.median(len(r['after']) for r in ok)}")


if __name__ == "__main__":
    main()
