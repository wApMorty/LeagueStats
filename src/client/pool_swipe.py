"""Écran Suggestions de pool (SPEC-49) : la pile d'échanges de `analysis/pool_swipe.py`, lue et
acceptée ou passée depuis le client.

La pile d'un poste se recalcule à chaque requête, sur le pool résolu pour ce poste (même règle que
l'écran Pool) et sur les passes de la version des données. Accepter remplace le sortant par
l'entrant dans le pool, puis l'enregistrement est fait par la route. Aucune maîtrise n'entre ici.
"""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from ..analysis.blindability import draw_shifts
from ..analysis.pool_swipe import PoolScorer, SwapCard, swap_cards
from ..analysis.pool_value import PoolEvaluator
from ..config_constants import pool_stats_config
from ..data_freshness import get_freshness_info
from ..db import Database
from ..pool_manager import ChampionPool, PoolManager, resolve_pool_for_lane
from ..user_prefs import load_swipe_passes, load_user_prefs, save_swipe_pass
from .data import date_fr
from .draft_actions import Refusal
from .draft_view import Champions, signed
from .pools import ROLE_LABELS, active_pool_name

DEFAULT_LANE = "top"


def data_version(db_path: Union[str, Path]) -> str:
    """Version des données (date du dernier scrape, ISO) ; « inconnue » si la base ne la donne pas."""
    last_update = get_freshness_info(str(db_path)).last_update
    return last_update.isoformat() if last_update else "inconnue"


def _lane(lane: Optional[str]) -> str:
    """Le poste demandé, ou le poste par défaut s'il est inconnu."""
    return lane if lane in ROLE_LABELS else DEFAULT_LANE


def _pool_for(manager: PoolManager, lane: str) -> Optional[ChampionPool]:
    """Pool résolu pour le poste, comme sur l'écran Pool."""
    prefs = load_user_prefs()
    pools_by_role = prefs.pools_by_role if prefs else {}
    pool, _ = resolve_pool_for_lane(manager, lane, pools_by_role, active_pool_name(manager))
    return pool


def _stack(
    db_path: Union[str, Path], lane: str, champions: Sequence[str], passed: Sequence[str]
) -> Tuple[List[SwapCard], Optional[str]]:
    """Pile d'échanges du pool sur le poste ; (pile, message) avec un message si la base est illisible."""
    db = Database(str(db_path))
    try:
        db.connect_read_only()
        scorer = PoolScorer(PoolEvaluator(db, lane), draw_shifts(db.connection).get(lane, {}))
        return swap_cards(scorer, list(champions), passed), None
    except sqlite3.Error:
        return [], "Base de données indisponible"
    finally:
        db.close()


def _portrait(champions: Champions, name: str) -> Dict[str, Any]:
    """Nom et portrait d'un champion (portrait absent : `img` None)."""
    return {"name": name, "img": (champions.by_name(name) or {}).get("img")}


def _card_view(card: SwapCard, champions: Champions) -> Dict[str, Any]:
    """Une carte prête pour le gabarit : valeurs formatées, duels en texte."""
    return {
        "incoming": _portrait(champions, card.incoming),
        "outgoing": _portrait(champions, card.outgoing),
        "gain": signed(card.gain, 2),
        "counter_gain": signed(card.counter_gain, 2),
        "blind_gain": signed(card.blind_gain, 2),
        "below_noise": card.below_noise,
        "wins": [{"name": enemy, "delta": signed(delta, 2)} for enemy, delta in card.wins],
        "losses": [{"name": enemy, "delta": signed(delta, 2)} for enemy, delta in card.losses],
    }


def swipe_view(
    manager: PoolManager,
    db_path: Union[str, Path],
    lane: Optional[str],
    champions: Champions,
    notice: Optional[str] = None,
) -> Dict[str, Any]:
    """Ce que l'écran affiche pour le poste `lane` : onglets, pool, première carte et ce qui reste.

    Un poste inconnu revient au poste par défaut. `message` explique l'absence de carte (pas de pool,
    pool système, pile vide, base illisible) ; `notice` est un message d'action ou d'erreur.
    """
    lane = _lane(lane)
    pool = _pool_for(manager, lane)
    info = get_freshness_info(str(db_path))
    version = data_version(db_path)
    version_label = f"du {date_fr(info.last_update)}" if info.last_update else "inconnues"

    cards: List[SwapCard] = []
    message = None
    shown_notice = notice
    if pool is None:
        message = "Aucun pool pour ce poste"
    elif pool.created_by == "system":
        message = "Pool système : duplique-le sur l'écran Pool pour recevoir des suggestions"
    else:
        cards, stack_error = _stack(
            db_path, lane, pool.champions, load_swipe_passes(version).get(lane, [])
        )
        shown_notice = shown_notice or stack_error
        if not cards and stack_error is None:
            message = f"Aucun échange ne fait gagner ce pool sur les données {version_label}"

    return {
        "lane": lane,
        "tabs": [
            {"lane": key, "label": label, "on": key == lane} for key, label in ROLE_LABELS.items()
        ],
        "pool": (
            {
                "name": pool.name,
                "champions": [_portrait(champions, name) for name in pool.champions],
                "editable": pool.created_by == "user",
            }
            if pool is not None
            else None
        ),
        "card": _card_view(cards[0], champions) if cards else None,
        "remaining": len(cards),
        "message": message,
        "version_label": version_label,
        "notice": shown_notice,
        "drag_px": pool_stats_config.POOL_SWIPE_DRAG_PX,
    }


def accept(
    manager: PoolManager,
    db_path: Union[str, Path],
    lane: str,
    incoming: str,
    outgoing: str,
) -> Tuple[str, Optional[str]]:
    """Remplace `outgoing` par `incoming` dans le pool du poste, en mémoire.

    Returns:
        (message affiché, nom du pool modifié). L'enregistrement est fait par l'appelant.

    Raises:
        Refusal: pas de pool ou pool système, base illisible, ou échange absent de la pile
        recalculée (suggestion périmée).
    """
    lane = _lane(lane)
    pool = _pool_for(manager, lane)
    if pool is None:
        raise Refusal("Aucun pool pour ce poste")
    if pool.created_by == "system":
        raise Refusal("Pool système : duplique-le sur l'écran Pool pour recevoir des suggestions")
    passed = load_swipe_passes(data_version(db_path)).get(lane, [])
    cards, stack_error = _stack(db_path, lane, pool.champions, passed)
    if stack_error is not None:
        raise Refusal(stack_error)
    card = next(
        (
            c
            for c in cards
            if c.incoming.casefold() == incoming.casefold()
            and c.outgoing.casefold() == outgoing.casefold()
        ),
        None,
    )
    if card is None:
        raise Refusal("Suggestion périmée, la pile a été recalculée")
    pool.champions[pool.champions.index(card.outgoing)] = card.incoming
    return f"{card.incoming} remplace {card.outgoing} dans « {pool.name} »", pool.name


def pass_card(db_path: Union[str, Path], lane: str, incoming: str) -> str:
    """Passe `incoming` pour le poste jusqu'à la prochaine mise à jour des données.

    Raises:
        Refusal: préférences non enregistrées.
    """
    lane = _lane(lane)
    if not save_swipe_pass(lane, incoming, data_version(db_path)):
        raise Refusal("Préférences non enregistrées")
    return f"{incoming} passé jusqu'à la prochaine mise à jour"
