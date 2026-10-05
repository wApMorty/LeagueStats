"""Relevé des formes LCU de la navigation du client (SPEC-21 tâche 76), en lecture seule.

À lancer client LoL ouvert (idéalement dans un lobby, pour ses formes). Chaque endpoint est lu (GET
uniquement : aucune écriture, aucun message) et sa réponse écrite dans `outputs/lcu_nav_forms/<nom>.json`
(ignoré par git), les identités remplacées. Un résumé de forme (clés, longueur) est imprimé ; un endpoint
sans réponse est signalé avec son code HTTP, jamais une erreur. Les fixtures de
`tests/fixtures/lcu_nav/` en sont tirées à la main (réduites, anonymisées).

USAGE:
    python scripts/dump_lcu_nav_forms.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.lcu_client import LCUClient  # noqa: E402

OUTPUT_DIR = Path(__file__).parent.parent / "outputs" / "lcu_nav_forms"
IDENTITY_KEYS = {
    "puuid",
    "summonerId",
    "accountId",
    "gameName",
    "tagLine",
    "summonerName",
    "displayName",
    "riotId",
    "pid",
    "note",
    "statusMessage",
    "body",
    "fromId",
    "fromPid",
    "fromSummonerId",
    "lastMessage",
    "inviterId",
    "toId",
}


CHAT_KEYS = {"id", "name"}  # dans le chat, `id` et `name` sont des identités d'amis


def anonymize(value, extra=frozenset()):
    """Remplace les identités par `anon` ; `extra` ajoute des clés (les `id` et `name` du chat, qui
    ailleurs désignent des files, des champions ou des défis et restent lisibles)."""
    if isinstance(value, dict):
        return {
            k: "anon" if k in IDENTITY_KEYS or k in extra else anonymize(v, extra)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [anonymize(item, extra) for item in value]
    return value


def shape(data) -> str:
    if isinstance(data, dict):
        return "objet {" + ", ".join(list(data)[:14]) + (", ..." if len(data) > 14 else "") + "}"
    if isinstance(data, list):
        return f"liste de {len(data)}" + (f" ; 1er : {shape(data[0])}" if data else "")
    return type(data).__name__


def endpoints(summoner_id: int, puuid: str, game_id):
    return [
        ("current_summoner", "/lol-summoner/v1/current-summoner"),
        ("ranked_stats", "/lol-ranked/v1/current-ranked-stats"),
        ("regalia", "/lol-regalia/v2/current-summoner/regalia"),
        ("challenges_summary", "/lol-challenges/v1/summary-player-data/local-player"),
        (
            "match_history",
            "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=19",
        ),
        ("game_detail", f"/lol-match-history/v1/games/{game_id}"),
        ("owned_champions", "/lol-champions/v1/owned-champions-minimal"),
        ("rune_pages", "/lol-perks/v1/pages"),
        ("item_sets", f"/lol-item-sets/v1/item-sets/{summoner_id}/sets"),
        ("queues", "/lol-game-queues/v1/queues"),
        ("lobby", "/lol-lobby/v2/lobby"),
        ("lobby_members", "/lol-lobby/v2/lobby/members"),
        ("lobby_search_state", "/lol-lobby/v2/lobby/matchmaking/search-state"),
        ("lobby_invitations", "/lol-lobby/v2/received-invitations"),
        ("matchmaking_search", "/lol-matchmaking/v1/search"),
        ("gameflow_phase", "/lol-gameflow/v1/gameflow-phase"),
        ("chat_me", "/lol-chat/v1/me"),
        ("chat_friends", "/lol-chat/v1/friends"),
        ("chat_conversations", "/lol-chat/v1/conversations"),
    ]


def main() -> int:
    lcu = LCUClient()
    if not lcu.connect():
        print("[ALERTE] Client LoL introuvable : ouvre-le (idéalement dans un lobby) et relance")
        return 1
    me = lcu._make_request("/lol-summoner/v1/current-summoner") or {}
    history = lcu._make_request(
        "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=0"
    )
    games = ((history or {}).get("games") or {}).get("games") or [{}]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, endpoint in endpoints(
        me.get("summonerId", 0), me.get("puuid", ""), games[0].get("gameId")
    ):
        data = lcu._make_request(endpoint)
        if data is None:
            print(f"[ALERTE] {endpoint} : pas de réponse (HTTP {lcu.last_status_code})")
            continue
        target = OUTPUT_DIR / f"{name}.json"
        target.write_text(
            json.dumps(
                anonymize(data, CHAT_KEYS if name.startswith("chat_") else frozenset()),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        print(f"[OK] {name} : {shape(data)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
