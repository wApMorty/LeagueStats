"""Spike SPEC-19 §3 : ce que le LCU expose d'une partie terminée.

À lancer sur le PC où tourne le client League of Legends, idéalement juste
après une partie de SoloQ ou de Flex (client ouvert, pas besoin de l'app).
Répond aux questions du spike :

    1. Profondeur de l'historique : combien de parties le LCU sert-il ?
    2. `/lol-match-history/v1/games/{id}` : quelles stats pour les 10 joueurs ?
    3. `/lol-match-history/v1/game-timelines/{id}` : l'endpoint répond-il,
       avec quelles images (intervalle, champs) et quels événements ?
    4. La timeline de la partie la plus ancienne de l'historique est-elle
       encore servie (purge) ?
    5. `/lol-end-of-game/v1/eog-stats-block` pendant l'écran de fin.
    6. Classement : le LCU expose-t-il la variation de LP d'une partie (le
       « +19 LP » de l'écran de fin), ou seulement le rang courant ?

Les réponses brutes sont écrites dans `outputs/spike_gameplay/` (ignoré par
git), avec les identités des joueurs anonymisées pour pouvoir en tirer des
fixtures de test. Lecture seule : aucune écriture dans le client ni en base.

USAGE:
    python scripts/spike_gameplay_dump.py                 # dernière partie
    python scripts/spike_gameplay_dump.py --game-id 7412345678
    python scripts/spike_gameplay_dump.py --depth 100     # profondeur testée
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.lcu_client import LCUClient

OUTPUT_DIR = project_root / "outputs" / "spike_gameplay"

# Champs d'identité remplacés par un alias stable avant écriture sur disque.
IDENTITY_KEYS = {
    "accountId",
    "currentAccountId",
    "gameName",
    "platformId",
    "profileIcon",
    "puuid",
    "riotIdGameName",
    "riotIdTagLine",
    "riotIdTagline",
    "summonerId",
    "summonerName",
    "tagLine",
}


def anonymize(obj: Any, aliases: Dict[str, str]) -> Any:
    """Copie de `obj` où chaque valeur d'identité devient `anon-N`."""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key in IDENTITY_KEYS and value not in (None, "", 0):
                result[key] = aliases.setdefault(str(value), f"anon-{len(aliases) + 1}")
            else:
                result[key] = anonymize(value, aliases)
        return result
    if isinstance(obj, list):
        return [anonymize(item, aliases) for item in obj]
    return obj


def dump(name: str, payload: Any, aliases: Dict[str, str]) -> None:
    path = OUTPUT_DIR / name
    path.write_text(json.dumps(anonymize(payload, aliases), indent=1), encoding="utf-8")
    print(f"    -> {path.relative_to(project_root)}")


def history(lcu: LCUClient, depth: int) -> List[Dict[str, Any]]:
    response = lcu._make_request(
        "/lol-match-history/v1/products/lol/current-summoner/matches"
        f"?begIndex=0&endIndex={depth - 1}"
    )
    games = ((response or {}).get("games") or {}).get("games") or []
    print(f"\n[1] Historique : {len(games)} parties servies pour {depth} demandées")
    if games:
        print(f"    plus récente : {games[0].get('gameCreationDate')}")
        print(f"    plus ancienne : {games[-1].get('gameCreationDate')}")
        print(f"    files : {dict(Counter(g.get('queueId') for g in games))}")
    return games


def describe_game(game: Optional[Dict[str, Any]]) -> None:
    print("\n[2] Détail de la partie (/games/{id})")
    if not game:
        print("    indisponible")
        return
    participants = game.get("participants") or []
    print(f"    clés : {sorted(game)}")
    print(f"    participants : {len(participants)}")
    if participants:
        first = participants[0]
        print(f"    clés d'un participant : {sorted(first)}")
        print(f"    stats ({len(first.get('stats') or {})}) : {sorted(first.get('stats') or {})}")
        print(f"    timeline du participant : {first.get('timeline')}")
    print(f"    participantIdentities : {len(game.get('participantIdentities') or [])}")


def describe_timeline(timeline: Optional[Dict[str, Any]]) -> None:
    print("\n[3] Timeline (/game-timelines/{id})")
    if not timeline:
        print("    indisponible (404 ou réponse vide)")
        return
    frames = timeline.get("frames") or []
    print(f"    clés : {sorted(timeline)}")
    print(f"    images : {len(frames)}, intervalle : {timeline.get('frameInterval')}")
    if not frames:
        return
    participant_frames = frames[min(10, len(frames) - 1)].get("participantFrames") or {}
    sample = (
        next(iter(participant_frames.values()), {})
        if isinstance(participant_frames, dict)
        else (participant_frames[0] if participant_frames else {})
    )
    print(f"    champs d'une image joueur (~10 min) : {json.dumps(sample)[:600]}")
    events = [event for frame in frames for event in frame.get("events") or []]
    types = Counter(event.get("type") for event in events)
    print(f"    événements ({len(events)}) : {dict(types)}")
    for event_type in types:
        example = next(event for event in events if event.get("type") == event_type)
        print(f"      {event_type} : {json.dumps(example)[:300]}")


# Endpoints de classement candidats (documentation communautaire, non vérifiée).
RANKED_ENDPOINTS = (
    "/lol-ranked/v1/current-ranked-stats",
    "/lol-ranked/v1/current-lp-change-notification",
    "/lol-ranked/v1/notifications",
)


def lp_fields(obj: Any, path: str = "") -> List[str]:
    """Chemins des champs dont le nom évoque des LP ou un rang."""
    hints = ("lp", "leaguepoint", "tier", "division", "rank")
    found: List[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else key
            if any(hint in key.lower() for hint in hints) and not isinstance(value, (dict, list)):
                found.append(f"{child} = {value}")
            found.extend(lp_fields(value, child))
    elif isinstance(obj, list):
        for index, item in enumerate(obj[:3]):
            found.extend(lp_fields(item, f"{path}[{index}]"))
    return found


def describe_ranked(lcu: LCUClient, eog: Optional[Dict[str, Any]], aliases: Dict[str, str]) -> None:
    print("\n[6] Classement")
    for endpoint in RANKED_ENDPOINTS:
        payload = lcu._make_request(endpoint)
        fields = lp_fields(payload)
        print(f"    {endpoint} : {'indisponible' if payload is None else f'{len(fields)} champs'}")
        for field in fields[:15]:
            print(f"      {field}")
        if payload is not None:
            dump(endpoint.rsplit("/", 1)[-1] + ".json", payload, aliases)
    if eog:
        print("    champs LP/rang de l'écran de fin :")
        for field in lp_fields(eog)[:15] or ["aucun"]:
            print(f"      {field}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--game-id", type=int, help="partie à détailler (défaut : la dernière)")
    parser.add_argument("--depth", type=int, default=50, help="profondeur d'historique testée")
    args = parser.parse_args()

    lcu = LCUClient()
    if not lcu.connect():
        return 1
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    aliases: Dict[str, str] = {}

    games = history(lcu, args.depth)
    dump("history.json", games, aliases)
    game_id = args.game_id or (games[0].get("gameId") if games else None)
    if game_id is None:
        print("[ERREUR] Aucune partie dans l'historique")
        return 1

    game = lcu._make_request(f"/lol-match-history/v1/games/{game_id}")
    describe_game(game)
    dump(f"{game_id}_game.json", game, aliases)

    timeline = lcu._make_request(f"/lol-match-history/v1/game-timelines/{game_id}")
    describe_timeline(timeline)
    dump(f"{game_id}_timeline.json", timeline, aliases)

    if len(games) > 1:
        oldest = games[-1].get("gameId")
        old_timeline = lcu._make_request(f"/lol-match-history/v1/game-timelines/{oldest}")
        frames = len((old_timeline or {}).get("frames") or [])
        print(f"\n[4] Timeline de la plus ancienne ({oldest}) : {frames} images")

    eog = lcu._make_request("/lol-end-of-game/v1/eog-stats-block")
    print(f"\n[5] Écran de fin : {'disponible' if eog else 'indisponible'}")
    if eog:
        dump("eog_stats_block.json", eog, aliases)

    describe_ranked(lcu, eog, aliases)

    print(f"\n[OK] Fichiers dans {OUTPUT_DIR.relative_to(project_root)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
