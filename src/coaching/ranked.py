"""Photos de classement (SPEC-19 §8, tâche 30b).

Deux sources LCU, relevées par le spike du 2026-09-28 :
- `current-ranked-stats` : rang courant par file, photo sans partie
  (`game_id` NULL) prise au démarrage ;
- `current-lp-change-notification` : rang et variation de LP de la dernière
  partie classée, lisible pendant l'après-partie seulement. Une partie
  récupérée au rattrapage n'a donc jamais de variation inventée.
"""

from ..config_constants import coaching_config


def snapshot_current(lcu, db) -> int:
    """Une photo par file classée où le joueur a un rang. Retourne leur nombre."""
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
        )
        count += 1
    return count


def snapshot_after_game(lcu, db) -> bool:
    """Photo de la partie classée qui vient de finir, une seule fois par partie."""
    note = lcu.get_lp_change_notification() or {}
    game_id = note.get("gameId")
    if not game_id or note.get("queueType") not in coaching_config.RANKED_QUEUES:
        return False
    inserted = db.insert_rank_snapshot(
        queue=note["queueType"],
        tier=note.get("tier", ""),
        division=note.get("division"),
        lp=note.get("leaguePoints", 0),
        wins=note.get("wins"),
        losses=note.get("losses"),
        lp_delta=note.get("leaguePointsDelta"),
        game_id=game_id,
    )
    if inserted:
        print(
            f"[DATA] Classement : {note.get('leaguePointsDelta', 0):+d} LP "
            f"-> {note.get('tier', '')} {note.get('division', '')} {note.get('leaguePoints', 0)} LP"
        )
    return inserted
