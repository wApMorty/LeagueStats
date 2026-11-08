"""Arbre de décision du pool côté client (SPEC-54) : vues de `partials/pool_tree.html`.

L'arbre (`analysis/pool_tree.py`) se calcule sur les matrices du scrape actuel, sans maîtrise,
pour le poste du pool. Le calcul de l'écran Pool est gardé en cache sur la version des données.
"""

import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from ..analysis.blindability import draw_shifts
from ..analysis.pool_swipe import PoolScorer
from ..analysis.pool_tree import PoolTree, build_tree
from ..analysis.pool_value import PoolEvaluator, dominant_lane
from ..config_constants import pool_stats_config
from ..data_freshness import get_freshness_info
from ..db import Database
from ..pool_manager import ChampionPool, pool_role_to_lane
from ..user_prefs import load_user_prefs
from .draft_view import Champions, fr, signed
from .pools import ROLE_LABELS


def data_version(db_path: Union[str, Path]) -> str:
    """Version des données (date du dernier scrape, ISO) ; « inconnue » si la base ne la donne pas."""
    last_update = get_freshness_info(str(db_path)).last_update
    return last_update.isoformat() if last_update else "inconnue"


def portrait(champions: Champions, name: str) -> Dict[str, Any]:
    """Nom et portrait d'un champion (portrait absent : `img` None)."""
    return {"name": name, "img": (champions.by_name(name) or {}).get("img")}


def tree_payload(tree: PoolTree, portraits: Champions) -> Dict[str, Any]:
    """L'arbre prêt pour le gabarit : ordre de blind, puis une ligne par adversaire joué à
    `POOL_SWIPE_MIN_POPULARITY` au moins (déjà triés par popularité), valeurs formatées.

    Chaque ligne donne le choix (meilleur champion du pool contre lui) et le premier repli
    (`None` si le pool n'a qu'un champion).
    """
    rows = []
    for enemy, popularity, table in tree.counters:
        if popularity < pool_stats_config.POOL_SWIPE_MIN_POPULARITY or not table:
            continue
        choice = table[0]
        fallback = table[1] if len(table) > 1 else None
        rows.append(
            {
                "enemy": portrait(portraits, enemy),
                "popularity": fr(popularity * 100, 1) + " %",
                "choice": portrait(portraits, choice.champion),
                "value": signed(choice.value, 2),
                "fallback": portrait(portraits, fallback.champion) if fallback else None,
                "fallback_value": signed(fallback.value, 2) if fallback else None,
            }
        )
    return {
        "blind": [
            {**portrait(portraits, choice.champion), "value": signed(choice.value, 2)}
            for choice in tree.blind
        ],
        "rows": rows,
    }


@lru_cache(maxsize=32)
def _tree(db_path: str, lane: str, champions: Tuple[str, ...], version: str) -> PoolTree:
    """Arbre du pool sur les matrices du scrape actuel ; `version` ne sert qu'à la clé du cache.

    Raises:
        sqlite3.Error: base illisible.
    """
    db = Database(db_path)
    try:
        db.connect_read_only()
        scorer = PoolScorer(PoolEvaluator(db, lane), draw_shifts(db.connection).get(lane, {}))
        return build_tree(scorer, list(champions))
    finally:
        db.close()


def tree_view(
    db_path: Union[str, Path], lane: Optional[str], champions: Sequence[str], portraits: Champions
) -> Optional[Dict[str, Any]]:
    """L'arbre prêt pour `partials/pool_tree.html` ; None sans lane, sans champion ou sur une base
    illisible."""
    if not lane or not champions:
        return None
    try:
        tree = _tree(str(db_path), lane, tuple(champions), data_version(db_path))
    except sqlite3.Error:
        return None
    return tree_payload(tree, portraits)


def pool_lane(pool: ChampionPool, db_path: Union[str, Path]) -> Optional[str]:
    """Poste de l'arbre d'un pool : son rôle, sinon le premier poste où il est désigné, sinon le
    poste dominant de ses champions sur la base (None si la base est illisible ou vide)."""
    lane = pool_role_to_lane(pool.role)
    if lane:
        return lane
    prefs = load_user_prefs()
    pools_by_role = prefs.pools_by_role if prefs else {}
    for candidate in ROLE_LABELS:
        if pools_by_role.get(candidate) == pool.name:
            return candidate
    db = Database(str(db_path))
    try:
        db.connect_read_only()
        return dominant_lane(db, pool.champions)
    except sqlite3.Error:
        return None
    finally:
        db.close()
