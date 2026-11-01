"""Blindabilité : ce dont un poste dépend, et comment un champion est tiré dans la draft.

Reconstruit deux figures de la vidéo MachineLoLing « The math behind champion blindability » à partir
des tables de paires, sans donnée d'ordre de pick (Riot n'en donne pas) :

- **Matrice des postes** : pour un poste et un autre, l'écart-type du signal des paires, hors bruit
  d'échantillonnage (MLE de SPEC-13). L'écran le rapporte à la moyenne de la ligne.
- **Tirage** : ce que les adversaires réellement rencontrés rapportent à un champion, par rapport à ceux
  de la méta. Positif : il est plutôt pris en contre-pick. Négatif : il se fait contrer.

    tirage(c) = Σ_e (P(e | c) − P(e)) · delta2(c, e)

``delta2`` ayant une moyenne nulle sur les adversaires du champion, seul l'écart de distribution porte
de l'information. L'estimateur reste brut : le lissage de SPEC-13 ne change pas le classement (stabilité
de 0,69 à 0,71 entre deux scrapes, 2026-11-01), mais divise l'effet par trois.

Les lignes de ``matchups`` ne portent pas la lane de l'adversaire : chaque champion est rangé à son poste
principal, et un champion trop partagé entre deux postes est écarté. La même raison exclut de la matrice
des synergies les paires à poste égal, qui ne sont pas de vrais duos.

Le classement de pick retire le tirage de la force, qui le contient déjà (ADR-004,
``WeightedEvaluator.draw_correction``).
"""

import math
import sqlite3
from typing import Dict, List, Set, Tuple

from ..config_constants import analysis_config
from .shrink import Sample, estimate_signal_variance

# Requêtes littérales plutôt qu'un nom de table interpolé (CLAUDE.md « Code »).
_PAIRS = {
    "matchups": (
        "SELECT champion, enemy, delta2, winrate, games, lane FROM matchups "
        "WHERE games > 0 AND lane IS NOT NULL"
    ),
    "synergies": (
        "SELECT champion, ally, delta2, winrate, games, lane FROM synergies "
        "WHERE games > 0 AND lane IS NOT NULL"
    ),
}
_LANE_GAMES = "SELECT champion, lane, SUM(games) FROM matchups WHERE lane IS NOT NULL GROUP BY 1, 2"

LaneGames = Dict[Tuple[int, str], int]
Played = Set[Tuple[int, str]]


def _main_roles(lane_games: LaneGames) -> Dict[int, str]:
    """Poste principal de chaque champion ; absent s'il n'atteint pas `BLINDABILITY_MAIN_SHARE`."""
    totals: Dict[int, int] = {}
    for (champion, _), games in lane_games.items():
        totals[champion] = totals.get(champion, 0) + games
    return {
        champion: lane
        for (champion, lane), games in lane_games.items()
        if games >= analysis_config.BLINDABILITY_MAIN_SHARE * totals[champion]
    }


def _role_spreads(
    connection: sqlite3.Connection,
    table: str,
    main_roles: Dict[int, str],
    played: Played,
) -> Dict[str, Dict[str, float]]:
    """{poste: {autre poste: écart-type du signal en points de winrate}} d'une table de paires."""
    samples: Dict[str, Dict[str, List[Sample]]] = {}
    for champion, other, delta2, winrate, games, lane in connection.execute(_PAIRS[table]):
        role = main_roles.get(other)
        if role is None or (champion, lane) not in played:
            continue
        if table == "synergies" and role == lane:
            continue
        samples.setdefault(lane, {}).setdefault(role, []).append((delta2, winrate, games))
    return {
        lane: {
            role: math.sqrt(estimate_signal_variance(cell)) for role, cell in sorted(roles.items())
        }
        for lane, roles in samples.items()
    }


def _draws(
    connection: sqlite3.Connection,
    lane_games: LaneGames,
    main_roles: Dict[int, str],
    played: Played,
) -> Dict[str, Dict[str, float]]:
    """{lane: {nom du champion: tirage en points de winrate}}, pour les champions assez joués."""
    pairs: Dict[Tuple[int, str], List[Tuple[int, float, int]]] = {}
    for champion, enemy, delta2, _, games, lane in connection.execute(_PAIRS["matchups"]):
        if (champion, lane) in played and main_roles.get(enemy) == lane and enemy != champion:
            pairs.setdefault((champion, lane), []).append((enemy, delta2, games))

    names = dict(connection.execute("SELECT id, name FROM champions"))
    draws: Dict[str, Dict[str, float]] = {}
    for (champion, lane), rows in pairs.items():
        faced = sum(games for _, _, games in rows)
        meta = sum(lane_games[(enemy, lane)] for enemy, _, _ in rows)
        if champion in names:
            draws.setdefault(lane, {})[names[champion]] = sum(
                (games / faced - lane_games[(enemy, lane)] / meta) * delta2
                for enemy, delta2, games in rows
            )
    return draws


def compute_blindability(connection: sqlite3.Connection) -> dict:
    """Matrices des postes et tirages, lus dans `connection`.

    Calcul à la lecture (~0,4 s sur la base réelle) : rien à stocker ni à tenir à jour.

    Returns:
        `{"matchups": matrice, "synergies": matrice, "draws": tirages}`, vides sur une base sans paires.

    Raises:
        sqlite3.Error: base sans tables de paires.
    """
    lane_games, main_roles, played = _context(connection)
    return {
        "matchups": _role_spreads(connection, "matchups", main_roles, played),
        "synergies": _role_spreads(connection, "synergies", main_roles, played),
        "draws": _draws(connection, lane_games, main_roles, played),
    }


def draw_shifts(connection: sqlite3.Connection) -> Dict[str, Dict[str, float]]:
    """Tirages seuls, pour le classement de pick : `{lane: {nom du champion: points de winrate}}`."""
    return _draws(connection, *_context(connection))


def _context(connection: sqlite3.Connection) -> Tuple[LaneGames, Dict[int, str], Played]:
    """Parties par (champion, lane), postes principaux et (champion, lane) assez joués."""
    lane_games: LaneGames = {
        (champion, lane): games for champion, lane, games in connection.execute(_LANE_GAMES)
    }
    played = {
        key for key, games in lane_games.items() if games >= analysis_config.BLINDABILITY_MIN_GAMES
    }
    return lane_games, _main_roles(lane_games), played
