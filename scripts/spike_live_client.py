"""Spike SPEC-20 §6 / tâche 46 : ce que la Live Client API expose en partie.

À lancer PENDANT une partie (SoloQ, Flex, ou un entraînement en mode personnalisé : la
partie entière n'est pas nécessaire pour les champs, mais plus elle dure, plus les types
d'événements vus sont variés). Répond aux questions du spike :

    1. `allgamedata` : quels champs (`gameData`, `allPlayers`, `events`) ?
    2. `allPlayers[*].scores`, `level`, `isDead`, `respawnTimer` sont-ils servis pour les
       10 joueurs, adversaires compris, et l'or l'est-il pour les adversaires ?
    3. Quels types d'événements, avec quels champs (`TurretKilled`, `DragonKill`, ...) ?
    4. Comment se nomment tours, inhibiteurs et tueurs (pour attribuer l'équipe) ?

Un instantané est pris toutes les `--every` secondes jusqu'à la fin de la partie (ou
`--max-minutes`). Les instantanés bruts sont écrits dans `outputs/spike_live/` (ignoré par
git), identités remplacées par `anon-N` pour pouvoir en tirer des fixtures de test. Lecture
seule : aucune écriture dans le jeu ni en base.

USAGE:
    python scripts/spike_live_client.py              # un instantané toutes les 30 s
    python scripts/spike_live_client.py --every 5 --max-minutes 10
    python scripts/spike_live_client.py --once
"""

import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "spike_live"
IDENTITY_KEYS = ("summonerName", "riotId", "riotIdGameName", "riotIdTagLine", "gameName")

# Le client du jeu sert un certificat auto-signé sur localhost.
CONTEXT = ssl.create_default_context()
CONTEXT.check_hostname = False
CONTEXT.verify_mode = ssl.CERT_NONE


def fetch() -> dict:
    with urllib.request.urlopen(URL, context=CONTEXT, timeout=5) as response:
        return json.load(response)


def anonymize(text: str, snapshot: dict) -> str:
    """Remplace chaque nom de joueur (toutes les formes) par `anon-N`, y compris dans les événements."""
    names = []
    for player in snapshot.get("allPlayers", []):
        names += [player.get(key) for key in IDENTITY_KEYS]
    for i, name in enumerate(sorted({n for n in names if n}, key=len, reverse=True)):
        text = re.sub(re.escape(name), f"anon-{i}", text)
    return text


def describe(snapshot: dict, seen: dict) -> None:
    """Accumule les champs vus : clés de gameData, du joueur, de ses scores, et par type d'événement."""
    seen["gameData"] |= set(snapshot.get("gameData", {}))
    for player in snapshot.get("allPlayers", []):
        seen["player"] |= set(player)
        seen["scores"] |= set(player.get("scores", {}))
    for event in snapshot.get("events", {}).get("Events", []):
        seen[f"event {event.get('EventName')}"] |= set(event)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--every", type=float, default=30.0, help="secondes entre deux instantanés")
    parser.add_argument("--max-minutes", type=float, default=60.0)
    parser.add_argument("--once", action="store_true", help="un seul instantané")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seen: dict = defaultdict(set)
    deadline = time.monotonic() + args.max_minutes * 60
    taken = 0
    while time.monotonic() < deadline:
        try:
            snapshot = fetch()
        except (urllib.error.URLError, OSError, ValueError) as e:
            if taken:
                print(f"Plus de réponse ({e}) : fin de partie ?")
                break
            print(f"Aucune partie en cours ({e}). Nouvelle tentative dans {args.every:.0f} s.")
            if args.once:
                sys.exit(1)
            time.sleep(args.every)
            continue
        game_time = snapshot.get("gameData", {}).get("gameTime", 0)
        path = OUTPUT_DIR / f"snapshot_{int(game_time):05d}.json"
        path.write_text(anonymize(json.dumps(snapshot, indent=1), snapshot), encoding="utf-8")
        describe(snapshot, seen)
        taken += 1
        print(f"[{game_time / 60:5.1f} min] {path.name}")
        if args.once:
            break
        time.sleep(args.every)

    print(f"\n{taken} instantané(s) dans {OUTPUT_DIR}\n")
    for group, keys in sorted(seen.items()):
        print(f"{group}: {', '.join(sorted(keys))}")


if __name__ == "__main__":
    main()
