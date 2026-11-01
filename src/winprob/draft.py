"""A priori de draft de la win chance (SPEC-33 §7, ADR-004).

Le logit de draft (`GameEvaluator.team_logit`, point de vue bleu) entre dans le modèle comme une
variable d'état, `draft`, constante sur la partie. Elle vaut 0 quand la draft n'est pas connue : pas de
postes incomplets, autre file, base illisible. La win chance retombe alors sur l'état de partie
seul.

`impact.py` ne la renseigne pas : un impact mesure ce qu'un événement change, pas la draft.

Les tables sont chargées une fois, en lecture seule, et gardées en mémoire tant que `db.db` ne change
pas. La connexion est refermée aussitôt : ces lectures viennent de fils du client et d'un processus à
part (l'overlay).
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from ..analysis.game_eval import GameEvaluator, Placed
from ..coaching.metrics import EOG_POSITIONS, participant_roles
from ..config import config
from ..config_constants import analysis_config, scraping_config
from ..db import Database
from .state import BLUE, RED

RAW_CHAMPION_PREFIX = "game_character_displayname_"  # format de `rawChampionName`
_LIVE_TEAMS = {"ORDER": BLUE, "CHAOS": RED}

Reader = Tuple[GameEvaluator, Dict[int, str]]
Teams = Dict[int, List[Placed]]


@lru_cache(maxsize=1)
def _load(path: str, _stamp: int) -> Reader:
    """Évaluateur et noms des champions, lus une fois par version de la base."""
    db = Database(path)
    db.connect_read_only()
    try:
        evaluator = GameEvaluator(db)
        evaluator.warm(scraping_config.LANES)
        return evaluator, db.get_all_champion_names()
    finally:
        db.close()


def reader(path: Union[str, Path, None] = None) -> Reader:
    """Évaluateur et noms de `path`, `db.db` par défaut. Lève si la base ne se lit pas."""
    path = str(path or config.DATABASE_PATH)
    return _load(path, os.stat(path).st_mtime_ns)


def _complete(teams: Teams) -> bool:
    """Cinq joueurs par équipe, à cinq postes distincts : sinon le logit ne veut rien dire."""
    return all(len(team) == 5 and len({lane for _, lane in team}) == 5 for team in teams.values())


def game_draft(game: dict, source: Reader, roles: Optional[dict] = None) -> float:
    """Logit de draft d'une partie enregistrée, 0.0 hors file classée ou sans ses dix postes.
    `roles` : participant -> poste ; sans lui, `participant_roles`."""
    evaluator, names = source
    roles = roles or participant_roles(game)
    if game.get("queueId") not in analysis_config.BACKTEST_QUEUE_IDS:
        return 0.0
    teams: Teams = {BLUE: [], RED: []}
    for player in game["participants"]:
        lane = roles.get(player["participantId"])
        if lane is None:
            return 0.0
        name = names.get(player["championId"], str(player["championId"]))
        teams[player["teamId"]].append((name, lane))
    return evaluator.team_logit(teams[BLUE], teams[RED]) if _complete(teams) else 0.0


def recorded_draft(
    game: dict, path: Union[str, Path, None] = None, roles: Optional[dict] = None
) -> float:
    """`game_draft` lu dans `path` ; 0.0 si la base ne se lit pas : la courbe reste tracée."""
    try:
        return game_draft(game, reader(path), roles)
    except Exception:  # pylint: disable=broad-exception-caught
        return 0.0


def _live_teams(data: dict) -> Optional[Teams]:
    """Les deux équipes de la Live Client API, None tant que les dix postes ne sont pas connus."""
    teams: Teams = {BLUE: [], RED: []}
    for player in data["allPlayers"]:
        raw = (player.get("rawChampionName") or "").removeprefix(RAW_CHAMPION_PREFIX)
        lane = EOG_POSITIONS.get(player.get("position") or "")
        if not raw or lane is None:
            return None
        teams[_LIVE_TEAMS[player["team"]]].append((raw, lane))
    return teams if _complete(teams) else None


def live_draft(data: dict, path: Union[str, Path, None] = None) -> Optional[float]:
    """Logit de draft de la partie en cours ; None si les postes manquent encore, à relire au tour
    suivant ; 0.0 si la base ne se lit pas (best-effort : la win chance reste affichée)."""
    try:
        teams = _live_teams(data)
        if teams is None:
            return None
        return reader(path)[0].team_logit(teams[BLUE], teams[RED])
    except Exception:  # pylint: disable=broad-exception-caught
        return 0.0
