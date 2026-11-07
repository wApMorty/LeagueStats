"""Photos de classement (SPEC-19 §8, tâche 30b).

Deux sources LCU, relevées par le spike du 2026-09-28 :
- `current-ranked-stats` : rang courant par file, photo sans partie
  (`game_id` NULL) prise au démarrage ;
- `current-lp-change-notification` : rang et variation de LP de la dernière
  partie classée, lisible pendant l'écran de fin seulement (lue par `PostGameWatcher`, SPEC-25,
  puis écrite par `snapshot_after_game`). Une partie
  récupérée au rattrapage n'a donc jamais de variation inventée.
"""

from typing import Optional

from ..config_constants import coaching_config

# L'événement WebSocket de cet URI porte la même notification que le GET, à l'instant où elle naît.
LP_NOTIFICATION_URI = "/lol-ranked/v1/current-lp-change-notification"
CURRENT_SUMMONER = "/lol-summoner/v1/current-summoner"


def current_puuid(lcu) -> Optional[str]:
    """Le puuid du compte connecté au client (SPEC-52), None s'il ne répond pas."""
    summoner = lcu._make_request(CURRENT_SUMMONER)
    puuid = summoner.get("puuid") if isinstance(summoner, dict) else None
    return puuid if isinstance(puuid, str) and puuid else None


def snapshot_current(lcu, db) -> int:
    """Une photo par file classée où le joueur a un rang, au compte connecté. Retourne leur nombre ;
    0 sans compte connu (une photo sans compte ne s'afficherait nulle part)."""
    puuid = current_puuid(lcu)
    if puuid is None:
        return 0
    count = 0
    for queue in (lcu.get_ranked_stats() or {}).get("queues") or []:
        if queue.get("queueType") not in coaching_config.RANKED_QUEUES or not queue.get("tier"):
            continue
        db.insert_rank_snapshot(
            queue=queue["queueType"],
            tier=queue["tier"],
            division=queue.get("division"),
            lp=queue.get("leaguePoints", 0),
            wins=queue.get("wins"),
            losses=queue.get("losses"),
            puuid=puuid,
        )
        count += 1
    return count


def valid_notification(note) -> Optional[dict]:
    """La notification de LP d'une partie classée, None pour `{}`, `null` ou une autre file."""
    if not isinstance(note, dict) or not note.get("gameId"):
        return None
    return note if note.get("queueType") in coaching_config.RANKED_QUEUES else None


def snapshot_after_game(note: dict, db, puuid: Optional[str] = None) -> bool:
    """Photo de la partie classée qui vient de finir (`note` : sa notification de LP, lue pendant
    l'écran de fin et mise de côté), une seule fois par partie, au compte `puuid`."""
    game_id = note["gameId"]
    inserted = db.insert_rank_snapshot(
        queue=note["queueType"],
        tier=note.get("tier", ""),
        division=note.get("division"),
        lp=note.get("leaguePoints", 0),
        wins=note.get("wins"),
        losses=note.get("losses"),
        lp_delta=note.get("leaguePointsDelta"),
        game_id=game_id,
        puuid=puuid,
    )
    if inserted:
        print(
            f"[DATA] Classement : {note.get('leaguePointsDelta', 0):+d} LP "
            f"-> {note.get('tier', '')} {note.get('division', '')} {note.get('leaguePoints', 0)} LP"
        )
    return inserted
