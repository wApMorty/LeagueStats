"""Formes LCU de la navigation relevées par la tâche 76 (SPEC-21 §11) et figées en fixtures.

Chaque fixture porte les clés que les écrans lisent : si un relevé futur (`scripts/dump_lcu_nav_forms.py`)
change une forme, ce test le dit avant les écrans. Les fixtures du lobby sont construites d'après le schéma
de `/help` (aucun lobby n'était ouvert au relevé) ; celles du relevé réel sont réduites et anonymisées.
"""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "lcu_nav"
QUEUE_KEYS = {"queueType", "tier", "division", "leaguePoints", "wins", "losses"}
PARTICIPANT_KEYS = {"summonerName", "puuid", "isLeader", "firstPositionPreference", "ready"}

SHAPES = {
    "current_summoner": {
        "gameName",
        "tagLine",
        "profileIconId",
        "summonerLevel",
        "summonerId",
        "puuid",
    },
    "ranked_stats": {"queues", "queueMap", "highestRankedEntry"},
    "regalia": {"crestType", "bannerType", "highestRankedEntry", "lastSeasonHighestRank"},
    "challenges_summary": {
        "overallChallengeLevel",
        "totalChallengeScore",
        "categoryProgress",
        "topChallenges",
    },
    "match_history": {"accountId", "games"},
    "game_detail": {"gameId", "queueId", "participants", "participantIdentities", "teams"},
    "item_sets": {"itemSets"},
    "lobby": {"members", "localMember", "gameConfig", "canStartActivity", "invitations"},
    "search_state_idle": {"searchState", "errors", "lowPriorityData"},
    "search_state_searching": {"searchState", "errors", "lowPriorityData"},
    "matchmaking_search": {
        "searchState",
        "timeInQueue",
        "estimatedQueueTime",
        "isCurrentlyInQueue",
    },
    "chat_me": {"availability", "gameName", "gameTag", "icon", "statusMessage", "lol"},
}
LISTS = {
    "owned_champions": {"id", "name", "alias", "roles", "ownership"},
    "queues": {
        "id",
        "name",
        "category",
        "gameSelectModeGroup",
        "isCustom",
        "queueAvailability",
        "isVisible",
    },
    "lobby_members": PARTICIPANT_KEYS,
    "chat_friends": {
        "availability",
        "gameName",
        "gameTag",
        "groupName",
        "icon",
        "lol",
        "statusMessage",
    },
    "chat_conversations": {"id", "name", "unreadMessageCount", "lastMessage"},
}


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_forme_objet(name):
    assert SHAPES[name] <= set(load(name))


@pytest.mark.parametrize("name", sorted(LISTS))
def test_forme_liste(name):
    rows = load(name)
    assert rows and all(LISTS[name] <= set(row) for row in rows)


def test_historique_et_detail_decrivent_la_meme_partie():
    game = load("match_history")["games"]["games"][0]
    detail = load("game_detail")
    assert game["gameId"] == detail["gameId"]
    assert len(game["participants"]) == 1  # la liste ne porte que le joueur
    assert len(detail["participants"]) == 10  # le détail porte tout le monde
    assert QUEUE_KEYS <= set(load("ranked_stats")["queues"][0])
    assert {p["participantId"] for p in detail["participants"]} == {
        i["participantId"] for i in detail["participantIdentities"]
    }


def test_les_identites_sont_synthetiques():
    """Aucun pseudo ni identifiant du relevé réel : tout vient de `Invocateur` et de `Joueur<n>`."""
    summoner = load("current_summoner")
    assert summoner["puuid"].startswith("puuid-test-")
    assert all(f["puuid"].startswith("puuid-test-") for f in load("chat_friends"))
    assert all(m["puuid"].startswith("puuid-test-") for m in load("lobby_members"))
