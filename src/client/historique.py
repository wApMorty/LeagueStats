"""Écran Historique : les parties du compte lues dans le LCU, et le détail d'une partie (SPEC-21 tâche 78).

Fonctions pures. Le LCU sert 20 parties au plus ; la liste ne porte que le joueur (un seul participant par
partie), le détail porte les dix. Une partie aussi capturée par le Live Coach renvoie vers sa page
d'analyse (`/parties/{id}` : win chance, impact), les autres n'ont que ce que le LCU en dit.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from ..config_client import client_config
from .data import ago, date_fr, plural, thousands
from .draft_view import Champions, fr
from .lcu_proxy import LcuProxy
from .profil import SUMMONER
from .review import clock

MATCHES = "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex={last}"
GAME = "/lol-match-history/v1/games/{id}"

SLOTS = tuple(f"item{i}" for i in range(7))  # `item6` est le trinket
TEAM_NAMES = {100: "Équipe bleue", 200: "Équipe rouge"}
OBJECTIVES = (
    ("towerKills", "tours"),
    ("inhibitorKills", "inhibiteurs"),
    ("dragonKills", "dragons"),
    ("baronKills", "barons"),
    ("riftHeraldKills", "hérauts"),
    ("hordeKills", "larves"),
)


def _moment(game: Dict[str, Any]) -> datetime:
    return datetime.fromtimestamp(game["gameCreation"] / 1000, tz=timezone.utc)


def _queue(game: Dict[str, Any]) -> str:
    queue = game["queueId"]
    return client_config.GAME_QUEUE_NAMES.get(queue, f"File {queue}")


def _cs(stats: Dict[str, Any]) -> int:
    return stats["totalMinionsKilled"] + stats["neutralMinionsKilled"]


def _kda(stats: Dict[str, Any]) -> str:
    return f"{stats['kills']} / {stats['deaths']} / {stats['assists']}"


def _row(game: Dict[str, Any], captured: Set[int], champions: Champions, now: datetime) -> dict:
    me = game["participants"][0]
    stats = me["stats"]
    minutes = max(game["gameDuration"], 1) / 60
    moment = _moment(game)
    return {
        "game_id": game["gameId"],
        "href": f"/historique/{game['gameId']}",
        "win": bool(stats["win"]),
        "champion": champions.name(me["championId"]),
        "portrait": champions.image(me["championId"]),
        "kda": _kda(stats),
        "cs": f"{_cs(stats)} ({fr(_cs(stats) / minutes, 1)}/min)",
        "duration": clock(game["gameDuration"]),
        "queue": _queue(game),
        "date": date_fr(moment),
        "ago": ago(moment, now),
        "captured": game["gameId"] in captured,
    }


def history_view(
    matches: Dict[str, Any], captured: Set[int], champions: Champions, now: datetime
) -> dict:
    """La liste des parties, de la plus récente à la plus ancienne. Une entrée illisible est passée :
    elle ne doit pas masquer les autres."""
    rows: List[dict] = []
    for game in matches["games"]["games"]:
        try:
            rows.append(_row(game, captured, champions, now))
        except (KeyError, TypeError, IndexError):
            continue
    wins = sum(r["win"] for r in rows)
    return {
        "empty": not rows,
        "rows": rows,
        "summary": f"{plural(len(rows), 'partie')} · {wins} V · {len(rows) - wins} D",
        "captured": sum(r["captured"] for r in rows),
    }


def read_history(
    proxy: LcuProxy, captured: Set[int], champions: Champions, now: datetime
) -> Optional[dict]:
    """La liste lue dans le LCU ; None s'il ne la sert pas."""
    matches = proxy.get(MATCHES.format(last=client_config.HISTORY_COUNT - 1))
    return None if matches is None else history_view(matches, captured, champions, now)


# ---------- détail ----------


def _player(
    participant: Dict[str, Any],
    identity: Dict[str, Any],
    mine: bool,
    most_damage: int,
    champions: Champions,
    minutes: float,
) -> dict:
    stats = participant["stats"]
    player = identity["player"]
    damage = stats["totalDamageDealtToChampions"]
    return {
        "mine": mine,
        "name": player.get("gameName") or player["summonerName"],
        "tag": player.get("tagLine") or "",
        "champion": champions.name(participant["championId"]),
        "portrait": champions.image(participant["championId"]),
        "level": stats["champLevel"],
        "kda": _kda(stats),
        "cs": _cs(stats),
        "cs_min": fr(_cs(stats) / minutes, 1),
        "gold": thousands(stats["goldEarned"]),
        "damage": thousands(damage),
        "damage_percent": round(100 * damage / most_damage) if most_damage else 0,
        "vision": stats["visionScore"],
        "build": [stats[slot] for slot in SLOTS if stats[slot]],
    }


def read_game(
    proxy: LcuProxy, game_id: int, captured: Set[int], champions: Champions, now: datetime
) -> Optional[dict]:
    """Le détail d'une partie lu dans le LCU ; None s'il l'ignore. `puuid` repère le joueur parmi les dix."""
    game = proxy.get(GAME.format(id=game_id))
    me = proxy.get(SUMMONER) if game is not None else None
    if game is None or me is None:
        return None
    return game_view(game, me["puuid"], captured, champions, now)


def game_view(
    game: Dict[str, Any], puuid: str, captured: Set[int], champions: Champions, now: datetime
) -> dict:
    """Le détail d'une partie : les deux équipes, leurs objectifs, leurs bannissements, les dix joueurs."""
    identities = {i["participantId"]: i for i in game["participantIdentities"]}
    participants = game["participants"]
    minutes = max(game["gameDuration"], 1) / 60
    most_damage = max(p["stats"]["totalDamageDealtToChampions"] for p in participants)
    mine = next(
        (
            p["participantId"]
            for p in participants
            if identities[p["participantId"]]["player"].get("puuid") == puuid
        ),
        None,
    )
    teams = []
    for team in game["teams"]:
        members = [
            _player(
                p,
                identities[p["participantId"]],
                p["participantId"] == mine,
                most_damage,
                champions,
                minutes,
            )
            for p in participants
            if p["teamId"] == team["teamId"]
        ]
        teams.append(
            {
                "name": TEAM_NAMES.get(team["teamId"], f"Équipe {team['teamId']}"),
                "win": team["win"] == "Win",
                "has_me": any(m["mine"] for m in members),
                "players": members,
                "objectives": [(team[key], label) for key, label in OBJECTIVES],
                "bans": [
                    {
                        "name": champions.name(b["championId"]),
                        "portrait": champions.image(b["championId"]),
                    }
                    for b in team["bans"]
                    if b["championId"] > 0
                ],
            }
        )
    mine_team = next((t for t in teams if t["has_me"]), None)
    moment = _moment(game)
    return {
        "game_id": game["gameId"],
        "result": None if mine_team is None else ("Victoire" if mine_team["win"] else "Défaite"),
        "win": bool(mine_team and mine_team["win"]),
        "queue": _queue(game),
        "duration": clock(game["gameDuration"]),
        "date": date_fr(moment),
        "ago": ago(moment, now),
        "captured": game["gameId"] in captured,
        "teams": teams,
    }
