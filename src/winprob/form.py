"""Forme récente et impact par fenêtre des joueurs en partie (SPEC-33 §4.2, tâche 152).

Fonctions pures : historique brut LCU -> parties classées ; parties -> forme sur une fenêtre.
Aucune base, aucun réseau. Les fenêtres et les files sont passées en paramètres.
"""

from statistics import mean
from typing import Any, Dict, List, Optional

from ..coaching.metrics import participant_roles
from .impact import impacts as game_impacts
from .model import WinModel


def ranked_games(history: Any, queue_ids: tuple) -> List[Dict[str, Any]]:
    """Entrées brutes de l'historique LCU -> parties des files `queue_ids`, plus récentes d'abord.

    `history` est `payload["games"]["games"]` de `/lol-match-history/v1/products/lol/{puuid}/matches`.
    Une entrée mal formée est ignorée ; un historique qui n'est pas une liste donne [].
    """
    if not isinstance(history, list):
        return []
    games = []
    for entry in history:
        try:
            game = _game(entry, queue_ids)
        except (KeyError, TypeError, IndexError, AttributeError):
            continue
        if game:
            games.append(game)
    return sorted(games, key=lambda g: g["creation_ms"], reverse=True)


def _game(entry: Any, queue_ids: tuple) -> Optional[Dict[str, Any]]:
    """Une entrée de l'historique -> partie normalisée, None si hors des files demandées."""
    if entry["queueId"] not in queue_ids:
        return None
    participant = entry["participants"][0]
    stats = participant["stats"]
    return {
        "game_id": entry["gameId"],
        "creation_ms": entry["gameCreation"],
        "queue_id": entry["queueId"],
        "champion_id": participant["championId"],
        "win": bool(stats["win"]),
        "kills": stats["kills"],
        "deaths": stats["deaths"],
        "assists": stats["assists"],
        "cs": stats["totalMinionsKilled"] + stats["neutralMinionsKilled"],
        "duration_s": entry["gameDuration"],
    }


def form(
    games: List[Dict[str, Any]], impacts: Dict[Any, float], champion_id: int, window: int
) -> Dict[str, Any]:
    """Forme sur les `window` premières parties (déjà classées) : {n, win_rate, kda, cs_min,
    on_champion, impact, impact_n}.

    `win_rate` est dans 0..1 ; `kda` = (Σkills + Σassists) / max(Σdeaths, 1) ; `cs_min` = CS par
    minute de jeu. `impacts` = {game_id: points} ; `impact` est la moyenne des parties de la
    fenêtre qui y figurent (None si aucune), `impact_n` leur nombre. None quand le dénominateur
    est nul (aucune partie, durée nulle).
    """
    recent = games[:window]
    n = len(recent)
    duration_min = sum(g["duration_s"] for g in recent) / 60
    points = [impacts[g["game_id"]] for g in recent if g["game_id"] in impacts]
    deaths = sum(g["deaths"] for g in recent)
    return {
        "n": n,
        "win_rate": sum(g["win"] for g in recent) / n if n else None,
        "kda": (sum(g["kills"] + g["assists"] for g in recent) / max(deaths, 1)) if n else None,
        "cs_min": sum(g["cs"] for g in recent) / duration_min if duration_min else None,
        "on_champion": sum(g["champion_id"] == champion_id for g in recent),
        "impact": mean(points) if points else None,
        "impact_n": len(points),
    }


def player_impact(
    model: WinModel, game: dict, timeline: Optional[dict], puuid: str
) -> Optional[float]:
    """Impact du joueur `puuid` sur une partie, en points (100 × Σ ΔP de ses lignes d'impact).

    Calculé comme `impacts` (SPEC-20) avec les rôles de `participant_roles`. None si le joueur
    n'est pas dans `participantIdentities` ou si la timeline n'a pas de `frames`.
    """
    if not (timeline or {}).get("frames"):
        return None
    pid = next(
        (
            i["participantId"]
            for i in game.get("participantIdentities") or []
            if (i.get("player") or {}).get("puuid") == puuid
        ),
        None,
    )
    if pid is None:
        return None
    rows = game_impacts(model, game, timeline, participant_roles(game))["rows"]
    return 100 * float(sum(r["delta_p"] for r in rows if r["participant_id"] == pid))
