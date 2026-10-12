"""Spike SPEC-27 tâche 122 : relevé des postes en partie, comparé à l'écran de fin.

Pendant une partie, lit `allgamedata` toutes les `--every` secondes et écrit dans
`outputs/spike_live/positions-<horodatage>.jsonl` une ligne par relevé :
`{"t": temps de jeu, "players": [{"champion", "raw", "team", "position", "smite"}]}`.
Aucune identité (ni `summonerName`, ni `riotId`) n'est écrite.

`--compare FICHIER` : après la partie, lit en lecture seule `game_records.raw_eog` de la
partie la plus récente et affiche, par tranche de temps de jeu, la part des joueurs dont le
poste lu en jeu égale `detectedTeamPosition` de l'écran de fin, alliés et adversaires séparés.
La jointure se fait sur le nom de champion (écran de fin `championName`, relevé `championName`
ou `rawChampionName`), l'équipe alliée est celle de mon champion (`isLocalPlayer`).

USAGE:
    python scripts/spike_live_positions.py                  # un relevé toutes les 5 s
    python scripts/spike_live_positions.py --every 5 --max-minutes 60
    python scripts/spike_live_positions.py --compare outputs/spike_live/positions-XXXX.jsonl
"""

import argparse
import json
import re
import ssl
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.coaching.metrics import EOG_POSITIONS  # noqa: E402

URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
OUTPUT_DIR = ROOT / "outputs" / "spike_live"
DB_PATH = ROOT / "data" / "db.db"
RAW_PREFIX = "game_character_displayname_"
# (borne haute en secondes de temps de jeu, libellé)
SLICES = (
    (30, "0-30 s"),
    (60, "30-60 s"),
    (180, "1-3 min"),
    (600, "3-10 min"),
    (float("inf"), "10 min et plus"),
)

# Le client du jeu sert un certificat auto-signé sur localhost.
CONTEXT = ssl.create_default_context()
CONTEXT.check_hostname = False
CONTEXT.verify_mode = ssl.CERT_NONE


def fetch() -> dict:
    """Instantané brut de la Live Client API."""
    with urllib.request.urlopen(URL, context=CONTEXT, timeout=5) as response:
        return json.load(response)


def releve_of(snapshot: dict) -> dict:
    """Relevé sans identité : temps de jeu, puis champion, équipe, poste et Châtiment de chaque joueur."""
    players = []
    for player in snapshot.get("allPlayers", []):
        spells = player.get("summonerSpells") or {}
        players.append(
            {
                "champion": player.get("championName") or "",
                "raw": (player.get("rawChampionName") or "").removeprefix(RAW_PREFIX),
                "team": player.get("team") or "",
                "position": player.get("position") or "",
                "smite": any(
                    "Smite" in (s or {}).get("rawDisplayName", "") for s in spells.values()
                ),
            }
        )
    return {"t": snapshot.get("gameData", {}).get("gameTime", 0), "players": players}


def record(args: argparse.Namespace) -> None:
    """Écrit un relevé toutes les `args.every` secondes jusqu'à la fin de la partie."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / f"positions-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
    deadline = time.monotonic() + args.max_minutes * 60
    taken = 0
    with path.open("w", encoding="utf-8") as out:
        while time.monotonic() < deadline:
            try:
                snapshot = fetch()
            except (urllib.error.URLError, OSError, ValueError) as e:
                if taken:
                    print(f"Plus de réponse ({e}) : fin de partie ?")
                    break
                print(f"Aucune partie en cours ({e}). Nouvelle tentative dans {args.every:.0f} s.")
                time.sleep(args.every)
                continue
            out.write(json.dumps(releve_of(snapshot)) + "\n")
            out.flush()
            taken += 1
            time.sleep(args.every)
    print(f"[INFO] {taken} relevé(s) écrit(s) dans {path}")


def norm(text: str) -> str:
    """Clé de comparaison : minuscules, sans caractère non alphanumérique."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


def latest_eog(db_path: Path) -> tuple:
    """(game_id, écran de fin) de la partie la plus récente, lue en lecture seule."""
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True)) as conn:
        row = conn.execute(
            "SELECT game_id, raw_eog FROM game_records WHERE raw_eog IS NOT NULL "
            "ORDER BY game_creation_utc DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise LookupError("aucune partie avec écran de fin dans game_records")
    return row[0], json.loads(row[1])


def compare(releves: list, eog: dict) -> None:
    """Affiche, par tranche de temps de jeu et par camp, la part des postes lus conformes à l'écran de fin."""
    eog_players = [p for team in eog.get("teams") or [] for p in team.get("players") or []]
    eog_by_key = {norm(p.get("championName") or ""): p for p in eog_players}

    def eog_of(entry: dict):
        for key in (norm(entry["champion"]), norm(entry["raw"])):
            if key in eog_by_key:
                return eog_by_key[key]
        return None

    local = next((p for p in eog_players if p.get("isLocalPlayer")), None)
    my_team = next(
        (
            e["team"]
            for r in releves
            for e in r["players"]
            if local is not None and eog_of(e) is local
        ),
        None,
    )
    if my_team is None:
        raise LookupError("mon champion (isLocalPlayer) absent du relevé")

    # cellule : [joueurs comparables, sans poste lu, conformes]
    cells = defaultdict(lambda: [0, 0, 0])
    unmatched = set()
    for releve in releves:
        label = next(lbl for bound, lbl in SLICES if releve["t"] < bound)
        for entry in releve["players"]:
            eog_player = eog_of(entry)
            if eog_player is None:
                unmatched.add(entry["champion"])
                continue
            detected = eog_player.get("detectedTeamPosition") or ""
            if not detected:
                continue
            cell = cells[(label, "allies" if entry["team"] == my_team else "ennemis")]
            cell[0] += 1
            if not entry["position"]:
                cell[1] += 1
            elif entry["position"] == detected and entry["position"] in EOG_POSITIONS:
                cell[2] += 1

    for side in ("ennemis", "allies"):
        for _, label in SLICES:
            n, vides, ok = cells[(label, side)]
            comparable = n - vides
            share = f"{ok / comparable:.0%}" if comparable else "n/a"
            print(
                f"[DATA] {side:<8} {label:<15} relevés={n:4} sans poste={vides:4} "
                f"conformes={ok}/{comparable} ({share})"
            )
    if unmatched:
        print(
            f"[INFO] Champions du relevé absents de l'écran de fin : {', '.join(sorted(unmatched))}"
        )


def load_releves(path: Path) -> list:
    """Relevés d'un fichier `.jsonl`."""
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--every", type=float, default=5.0, help="secondes entre deux relevés")
    parser.add_argument("--max-minutes", type=float, default=60.0)
    parser.add_argument(
        "--compare",
        type=Path,
        metavar="FICHIER",
        help="relevé .jsonl à comparer à la dernière partie",
    )
    parser.add_argument(
        "--db", type=Path, default=DB_PATH, help="base lue en lecture seule (--compare)"
    )
    args = parser.parse_args()

    if args.compare is None:
        record(args)
        return
    try:
        game_id, eog = latest_eog(args.db)
        print(f"[INFO] Partie {game_id} comparée au relevé {args.compare.name}")
        compare(load_releves(args.compare), eog)
    except (sqlite3.Error, LookupError, OSError, ValueError) as e:
        print(f"[ERREUR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
