"""Faux LCU de la navigation du client (SPEC-21 lots 5 et 6) : sert les fixtures de `tests/fixtures/lcu_nav/`.

`overrides` remplace la réponse d'un endpoint (None = 404) ; chaque appel est noté dans `calls`, les
écritures dans `writes`. Aucun test n'ouvre le vrai client LoL.
"""

import json
from pathlib import Path

from src.client.assets import Assets
from src.config_client import client_config

FIXTURES = Path(__file__).parent / "fixtures" / "lcu_nav"
GAME_ID = 8004684141

ROUTES = {
    "/lol-summoner/v1/current-summoner": "current_summoner",
    "/lol-ranked/v1/current-ranked-stats": "ranked_stats",
    "/lol-regalia/v2/current-summoner/regalia": "regalia",
    "/lol-challenges/v1/summary-player-data/local-player": "challenges_summary",
    "/lol-champions/v1/owned-champions-minimal": "owned_champions",
    "/lol-item-sets/v1/item-sets/2001/sets": "item_sets",
    "/lol-game-queues/v1/queues": "queues",
    "/lol-lobby/v2/lobby": "lobby",
    "/lol-lobby/v2/lobby/members": "lobby_members",
    "/lol-lobby/v2/lobby/matchmaking/search-state": "search_state_idle",
    "/lol-matchmaking/v1/search": "matchmaking_search",
    "/lol-chat/v1/me": "chat_me",
    "/lol-chat/v1/friends": "chat_friends",
    "/lol-chat/v1/conversations": "chat_conversations",
    "/lol-perks/v1/pages": "../lcu_forms/pages",
}


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class FauxLcuNav:
    def __init__(self, overrides=None):
        self.credentials = object()
        self.overrides = overrides or {}
        self.calls = []
        self.phase = "None"  # phase du client : sert aussi de sonde « client ouvert »

    def find_lcu_credentials(self):
        return self.credentials

    def _make_request(self, endpoint, method="GET", data=None):
        self.calls.append((method, endpoint, data))
        if method != "GET":
            return {}  # écriture acceptée : le test lit `writes`
        if endpoint in self.overrides:
            return self.overrides[endpoint]
        if endpoint == "/lol-gameflow/v1/gameflow-phase":
            return self.phase
        if endpoint.startswith(
            "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex="
        ):
            return fixture("match_history")
        if endpoint == f"/lol-match-history/v1/games/{GAME_ID}":
            return fixture("game_detail")
        name = ROUTES.get(endpoint)
        return fixture(name) if name else None

    @property
    def writes(self):
        return [call for call in self.calls if call[0] != "GET"]


CHAMPIONS = {
    "data": {
        "Sion": {"key": "14", "id": "Sion", "name": "Sion", "tags": []},
        "Malphite": {
            "key": "54",
            "id": "Malphite",
            "name": "<script>alert(1)</script>",
            "tags": [],
        },
        "Ambessa": {"key": "799", "id": "Ambessa", "name": "Ambessa", "tags": []},
        "Annie": {"key": "1", "id": "Annie", "name": "Annie", "tags": ["Mage"]},
        "Jax": {"key": "24", "id": "Jax", "name": "Jax", "tags": ["Fighter"]},
        "Thresh": {"key": "412", "id": "Thresh", "name": "Thresh", "tags": ["Support"]},
    }
}


def make_assets(tmp_path):
    """Data Dragon factice : quelques champions, le reste retombe sur « Champion n »."""
    base = client_config.DDRAGON_BASE
    files = {
        f"{base}/api/versions.json": json.dumps(["16.2.1"]).encode(),
        f"{base}/cdn/16.2.1/data/fr_FR/champion.json": json.dumps(CHAMPIONS).encode(),
    }
    return Assets(tmp_path / "cache", fetch=files.get)
