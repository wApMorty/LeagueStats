"""Spike Live Client API (SPEC-20 tâche 46, scripts/spike_live_client.py) : anonymisation et
inventaire des champs, sur un instantané simulé. Aucun appel réseau."""

import json
from collections import defaultdict

from scripts.spike_live_client import anonymize, describe

SNAPSHOT = {
    "gameData": {"gameTime": 612.5, "mapName": "Map11"},
    "allPlayers": [
        {"summonerName": "Paul", "riotId": "Paul#EUW", "scores": {"kills": 2}, "isDead": False},
        {"summonerName": "Ennemi", "riotId": "Ennemi#EUW", "scores": {"kills": 1}, "isDead": True},
    ],
    "events": {
        "Events": [
            {
                "EventName": "ChampionKill",
                "KillerName": "Paul",
                "VictimName": "Ennemi",
                "Assisters": [],
            },
            {"EventName": "DragonKill", "KillerName": "Paul#EUW", "DragonType": "Fire"},
        ]
    },
}


def test_anonymize_hides_every_form_of_every_name():
    text = json.dumps(anonymize(SNAPSHOT))
    assert "Paul" not in text and "Ennemi" not in text and "EUW" not in text
    assert json.loads(text)["gameData"]["gameTime"] == 612.5


def test_anonymize_never_corrupts_numbers_with_a_short_name():
    snapshot = {
        "gameData": {"gameTime": 106.58219},
        "allPlayers": [{"summonerName": "1", "riotId": "1#EUW", "scores": {"kills": 21}}],
    }
    anonymized = anonymize(snapshot)
    assert anonymized["gameData"]["gameTime"] == 106.58219
    assert anonymized["allPlayers"][0]["scores"] == {"kills": 21}
    assert anonymized["allPlayers"][0]["summonerName"].startswith("anon-")


def test_describe_lists_fields_per_event_type():
    seen = defaultdict(set)
    describe(SNAPSHOT, seen)
    assert {"scores", "isDead"} <= seen["player"] and seen["scores"] == {"kills"}
    assert "DragonType" in seen["event DragonKill"] and "VictimName" in seen["event ChampionKill"]
