"""État de partie depuis la Live Client API (SPEC-20 §4.1 et §6, tâche 47).

Champs vérifiés au spike du 2026-10-02 (`scripts/spike_live_client.py`, 27 min) :
`gameData.gameTime`, `allPlayers[*]` (`team` ORDER/CHAOS, `level`, `scores.creepScore`,
`isDead`, `respawnTimer`, pas d'or pour les adversaires) et `events.Events` (`ChampionKill`,
`TurretKilled`, `InhibKilled`, `DragonKill`, `HeraldKill`, `HordeKill`, `BaronKill`).

Les événements sont convertis en événements de timeline LCU et rejoués par le même
`_Replay` que `state.py` : un même état donne la même win chance, d'où qu'il vienne (§11.3).
"""

import json
import ssl
import urllib.request
from typing import Dict, List, Optional

from ..config_winprob import winprob_config as cfg
from .state import BLUE, RED, _Replay

URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"
TEAMS = {"ORDER": BLUE, "CHAOS": RED}

# Le jeu sert un certificat auto-signé sur localhost.
_CONTEXT = ssl.create_default_context()
_CONTEXT.check_hostname = False
_CONTEXT.verify_mode = ssl.CERT_NONE


def fetch(timeout: float = 2.0) -> Optional[dict]:
    """`allgamedata`, ou None s'il n'y a pas de partie (ou pas de réponse) : jamais d'exception."""
    try:
        with urllib.request.urlopen(URL, context=_CONTEXT, timeout=timeout) as response:
            return json.load(response)
    except (OSError, ValueError):
        return None


def player_names(player: dict) -> List[str]:
    """Formes sous lesquelles les événements nomment ce joueur."""
    riot_id = player.get("riotId") or ""
    names = (
        player.get("summonerName"),
        player.get("riotIdGameName"),
        riot_id,
        riot_id.split("#")[0],
    )
    return [n for n in names if n]


def _timeline_event(e: dict, pid_of: Dict[str, int], teams: Dict[int, int]) -> Optional[dict]:
    """Événement Live Client → événement de timeline LCU, None s'il n'est pas suivi."""
    name, killer = e["EventName"], pid_of.get(e.get("KillerName", ""), 0)
    base = {
        "timestamp": int(e["EventTime"] * 1000),
        "killerId": killer,
        "victimId": 0,
        "assistingParticipantIds": [pid_of[a] for a in e.get("Assisters", []) if a in pid_of],
        "buildingType": "",
        "teamId": 0,
        "monsterType": "",
        "monsterSubType": "",
    }
    if name == "ChampionKill":
        return {**base, "type": "CHAMPION_KILL", "victimId": pid_of.get(e.get("VictimName", ""), 0)}
    for key, building in (
        ("TurretKilled", "TOWER_BUILDING"),
        ("InhibKilled", "INHIBITOR_BUILDING"),
    ):
        if name == key:
            owner = RED if "TChaos" in e[key] else BLUE
            return {**base, "type": "BUILDING_KILL", "buildingType": building, "teamId": owner}
    monster = {"HeraldKill": "RIFTHERALD", "HordeKill": "HORDE", "BaronKill": "BARON_NASHOR"}.get(
        name
    )
    if name == "DragonKill":
        elder = e.get("DragonType") == "Elder"
        monster, sub = "DRAGON", "ELDER_DRAGON" if elder else ""
        return {**base, "type": "ELITE_MONSTER_KILL", "monsterType": monster, "monsterSubType": sub}
    if monster:
        return {**base, "type": "ELITE_MONSTER_KILL", "monsterType": monster}
    return None


def state_from_live(data: dict) -> dict:
    """Vecteur d'état (différences bleu − rouge) à l'instant `gameData.gameTime`.

    Joueurs morts et temps restant viennent de `isDead` et `respawnTimer`, exacts, là où la
    timeline doit les déduire. Pas d'or : l'API ne le sert pas pour les adversaires.
    """
    t_ms = data["gameData"]["gameTime"] * 1000
    players = data["allPlayers"]
    teams = {i: TEAMS[p["team"]] for i, p in enumerate(players, 1)}
    pid_of = {form: i for i, p in enumerate(players, 1) for form in player_names(p)}
    replay = _Replay(teams)
    for i, p in enumerate(players, 1):
        replay.level[i] = p["level"]
        replay.cs[i] = p["scores"]["creepScore"]
        if p["isDead"]:
            replay.deaths[i] = (t_ms, p["respawnTimer"])
    for e in data["events"]["Events"]:
        event = _timeline_event(e, pid_of, teams)
        if event:
            _apply(replay, event)
    state = replay.state(t_ms)
    state.pop("gold")
    return state


def _apply(replay: _Replay, event: dict) -> None:
    """Rejoue l'événement sans toucher aux morts : la partie sait déjà qui est mort."""
    deaths = dict(replay.deaths)
    replay.event(event)
    replay.deaths = deaths
