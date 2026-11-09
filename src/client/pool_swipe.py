"""Panneau latéral de la Méta du poste (SPEC-49, SPEC-50, SPEC-51) : la pile d'échanges de
`analysis/pool_swipe.py`, lue et acceptée ou passée depuis le client, et le générateur de pool
(`analysis/pool_generator.py`).

La pile d'un poste se recalcule à chaque requête, sur le pool résolu pour ce poste (même règle que
l'écran Pool) et sur les passes de la version des données. Accepter remplace le sortant par
l'entrant dans le pool, puis l'enregistrement est fait par la route. Aucune maîtrise n'entre ici.

Le générateur calcule un pool sur les scrapes (mode moyenne) ou sur la base seule (mode actuel),
hors champions exclus du poste. Son résultat est gardé dans un cache de module, clé sur les entrées
(scrapes, exclusions, pool du poste) : un second calcul sans changement n'a pas lieu.
"""

import sqlite3
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from ..analysis.blindability import draw_shifts
from ..analysis.exposure import exposure_tree, lane_popularity
from ..analysis.game_eval import GameEvaluator
from ..analysis.pool_generator import GeneratedPool, generate_pool, mean_score
from ..analysis.pool_swipe import PoolScorer, SwapCard, swap_cards
from ..analysis.pool_tree import PoolTree
from ..analysis.pool_value import PoolEvaluator
from ..config_constants import pool_stats_config
from ..data_freshness import get_freshness_info
from ..db import Database
from ..db_backup import distinct_snapshots
from ..pool_manager import ChampionPool, PoolManager, resolve_pool_for_lane
from ..user_prefs import (
    load_pool_exclusions,
    load_swipe_passes,
    load_user_prefs,
    save_pool_exclusion,
    save_swipe_pass,
)
from .data import date_fr
from .draft_actions import Refusal
from .draft_view import Champions, fr, signed
from .pool_tree import data_version, portrait, tree_payload
from .pools import ROLE_LABELS, active_pool_name, champion_names

DEFAULT_LANE = "top"
MODE_SNAPSHOTS = "moyenne"  # moyenne des scrapes distincts
MODE_CURRENT = "actuel"  # la base seule
MODES = (MODE_SNAPSHOTS, MODE_CURRENT)
DB_UNAVAILABLE = "Base de données indisponible"
# Résultat du générateur par clé : (pool généré ou None, score moyen du pool du poste ou None).
_GENERATED: Dict[tuple, Tuple[Optional[GeneratedPool], Optional[float]]] = {}


def _lane(lane: Optional[str]) -> str:
    """Le poste demandé, ou le poste par défaut s'il est inconnu."""
    return lane if lane in ROLE_LABELS else DEFAULT_LANE


def _size(value: Any) -> int:
    """Taille de pool demandée ; `POOL_GEN_DEFAULT_SIZE` si elle n'est pas un entier dans la plage."""
    try:
        size = int(value)
    except (TypeError, ValueError):
        return pool_stats_config.POOL_GEN_DEFAULT_SIZE
    if pool_stats_config.POOL_GEN_MIN_SIZE <= size <= pool_stats_config.POOL_GEN_MAX_SIZE:
        return size
    return pool_stats_config.POOL_GEN_DEFAULT_SIZE


def _mode(value: Any) -> str:
    """Mode du générateur ; `moyenne` si le mode est inconnu."""
    return value if value in MODES else MODE_SNAPSHOTS


def _pool_for(manager: PoolManager, lane: str) -> Optional[ChampionPool]:
    """Pool résolu pour le poste, comme sur l'écran Pool."""
    prefs = load_user_prefs()
    pools_by_role = prefs.pools_by_role if prefs else {}
    pool, _ = resolve_pool_for_lane(manager, lane, pools_by_role, active_pool_name(manager))
    return pool


def _stack(
    db_path: Union[str, Path],
    lane: str,
    champions: Sequence[str],
    passed: Sequence[str],
    excluded: Sequence[str],
    cards: bool = True,
) -> Tuple[List[SwapCard], Optional[PoolTree], Optional[str]]:
    """Pile d'échanges et arbre du pool sur le poste, sur un seul `PoolScorer` ; `cards` à False :
    arbre seul. Renvoie (pile, arbre, message) ; message et arbre None si la base est illisible.
    """
    db = Database(str(db_path))
    try:
        db.connect_read_only()
        scorer = PoolScorer(PoolEvaluator(db, lane), draw_shifts(db.connection).get(lane, {}))
        stack = swap_cards(scorer, list(champions), passed, excluded) if cards else []
        tree = exposure_tree(GameEvaluator(db), lane, list(champions), lane_popularity(db))
        return stack, tree, None
    except sqlite3.Error:
        return [], None, DB_UNAVAILABLE
    finally:
        db.close()


def _card_view(card: SwapCard, champions: Champions) -> Dict[str, Any]:
    """Une carte prête pour le gabarit : valeurs formatées, duels en texte."""
    return {
        "incoming": portrait(champions, card.incoming),
        "outgoing": portrait(champions, card.outgoing),
        "gain": signed(card.gain, 2),
        "counter_gain": signed(card.counter_gain, 2),
        "blind_gain": signed(card.blind_gain, 2),
        "below_noise": card.below_noise,
        "wins": [{"name": enemy, "delta": signed(delta, 2)} for enemy, delta in card.wins],
        "losses": [{"name": enemy, "delta": signed(delta, 2)} for enemy, delta in card.losses],
    }


def _stamp(path: Path) -> Tuple[str, Optional[int]]:
    """Chemin et date de modification du fichier ; date None si le fichier est absent."""
    try:
        return str(path), path.stat().st_mtime_ns
    except OSError:
        return str(path), None


def _snapshots(db_path: Union[str, Path], mode: str) -> List[Path]:
    """Fichiers à scorer : les scrapes distincts (moyenne) ou la base seule (actuel)."""
    if mode == MODE_SNAPSHOTS:
        return distinct_snapshots(str(db_path))
    return [Path(db_path)]


def _generation_inputs(lane: str) -> Tuple[List[str], List[str]]:
    """Champions exclus du poste, et champions du pool résolu pour le poste (vide sans pool)."""
    excluded = load_pool_exclusions().get(lane, [])
    pool = _pool_for(PoolManager(), lane)
    return excluded, list(pool.champions) if pool else []


def _key(
    db_path: Union[str, Path],
    lane: str,
    size: int,
    mode: str,
    excluded: Sequence[str],
    champions: Sequence[str],
    snapshots: Sequence[Path],
) -> tuple:
    """Clé du cache : poste, taille, mode, exclus (sans casse), pool du poste, (chemin, mtime) des scrapes."""
    return (
        str(db_path),
        lane,
        size,
        mode,
        tuple(sorted(name.casefold() for name in excluded)),
        tuple(champions),
        tuple(_stamp(path) for path in snapshots),
    )


def _compute(
    snapshots: Sequence[Path],
    lane: str,
    size: int,
    excluded: Sequence[str],
    champions: Sequence[str],
) -> Tuple[Optional[GeneratedPool], Optional[float]]:
    """Calcule le pool généré et le score moyen du pool du poste, un `PoolScorer` par scrape.

    Raises:
        Refusal: aucun scrape lisible, ou base illisible.
    """
    if not snapshots:
        raise Refusal(DB_UNAVAILABLE)
    databases: List[Database] = []
    try:
        scorers: List[PoolScorer] = []
        for path in snapshots:
            db = Database(str(path))
            databases.append(db)
            db.connect_read_only()
            scorers.append(
                PoolScorer(PoolEvaluator(db, lane), draw_shifts(db.connection).get(lane, {}))
            )
        generated = generate_pool(scorers, size, excluded)
        current = mean_score(scorers, champions) if champions else None
        if generated is not None:
            tree = exposure_tree(
                GameEvaluator(databases[0]),
                lane,
                generated.champions,
                lane_popularity(databases[0]),
            )
            generated = replace(generated, tree=tree)
        return generated, current
    except sqlite3.Error:
        raise Refusal(DB_UNAVAILABLE)
    finally:
        for db in databases:
            db.close()


def generate(
    db_path: Union[str, Path], lane: Optional[str], size: Any, mode: Any
) -> Tuple[Optional[GeneratedPool], Optional[float]]:
    """Pool généré pour le poste, en cache ; second élément : score moyen du pool du poste.

    `size` et `mode` invalides reviennent au défaut ; `lane` inconnu au poste par défaut.
    Le générateur renvoie `None` s'il manque des candidats pour la taille demandée.

    Raises:
        Refusal: base illisible.
    """
    lane, size, mode = _lane(lane), _size(size), _mode(mode)
    excluded, champions = _generation_inputs(lane)
    snapshots = _snapshots(db_path, mode)
    key = _key(db_path, lane, size, mode, excluded, champions, snapshots)
    if key not in _GENERATED:
        if len(_GENERATED) >= pool_stats_config.POOL_GEN_CACHE_MAX:
            _GENERATED.clear()
        _GENERATED[key] = _compute(snapshots, lane, size, excluded, champions)
    return _GENERATED[key]


def cached_generation(
    db_path: Union[str, Path], lane: Optional[str], size: Any, mode: Any
) -> Optional[Tuple[Optional[GeneratedPool], Optional[float]]]:
    """Résultat déjà en cache pour ces paramètres ; `None` sans calcul si rien n'est en cache."""
    lane, size, mode = _lane(lane), _size(size), _mode(mode)
    excluded, champions = _generation_inputs(lane)
    snapshots = _snapshots(db_path, mode)
    return _GENERATED.get(_key(db_path, lane, size, mode, excluded, champions, snapshots))


def require_generated(
    db_path: Union[str, Path], lane: Optional[str], size: Any, mode: Any
) -> Tuple[GeneratedPool, Optional[float]]:
    """Comme `generate`, mais refuse s'il n'y a pas de pool généré.

    Raises:
        Refusal: pas assez de champions pour la taille, ou base illisible.
    """
    generated, current = generate(db_path, lane, size, mode)
    if generated is None:
        raise Refusal(f"Pas assez de champions pour un pool de {_size(size)}")
    return generated, current


def _generated_view(
    generated: GeneratedPool, current: Optional[float], champions: Champions
) -> Dict[str, Any]:
    """Le pool généré prêt pour le gabarit : valeurs formatées, portraits, arbre du pool."""
    blind = dict(generated.blind)
    share = dict(generated.counter_share)
    return {
        "champions": [
            {
                **portrait(champions, name),
                "blind": signed(blind[name], 2),
                "counter_share": fr(share[name] * 100, 0) + " %",
            }
            for name in generated.champions
        ],
        "score": signed(generated.score, 2),
        "per_scrape": [signed(score, 2) for score in generated.per_scrape],
        "gap": signed(generated.score - current, 2) if current is not None else None,
        "tree": tree_payload(generated.tree, champions) if generated.tree is not None else None,
        "candidates": generated.candidates,
    }


def aside_view(
    manager: PoolManager,
    db_path: Union[str, Path],
    lane: Optional[str],
    champions: Champions,
    notice: Optional[str] = None,
    size: Any = None,
    mode: Any = None,
) -> Dict[str, Any]:
    """Ce que le panneau affiche pour le poste `lane` : pool, première carte et ce qui reste.

    Un poste inconnu revient au poste par défaut. `message` explique l'absence de carte (pas de pool,
    pool système, pile vide, base illisible) ; `notice` est un message d'action ou d'erreur. Le
    générateur ajoute son résultat (`generated`) seulement s'il est déjà en cache : cette lecture ne
    calcule rien.
    """
    lane = _lane(lane)
    size, mode = _size(size), _mode(mode)
    pool = _pool_for(manager, lane)
    info = get_freshness_info(str(db_path))
    version = data_version(db_path)
    version_label = f"du {date_fr(info.last_update)}" if info.last_update else "inconnues"
    excluded = load_pool_exclusions().get(lane, [])

    cards: List[SwapCard] = []
    tree: Optional[PoolTree] = None
    message = None
    shown_notice = notice
    if pool is None:
        message = "Aucun pool pour ce poste"
    elif pool.created_by == "system":
        message = "Pool système : duplique-le sur l'écran Pool pour recevoir des suggestions"
        _, tree, stack_error = _stack(db_path, lane, pool.champions, [], excluded, False)
        shown_notice = shown_notice or stack_error
    else:
        cards, tree, stack_error = _stack(
            db_path,
            lane,
            pool.champions,
            load_swipe_passes(version).get(lane, []),
            excluded,
        )
        shown_notice = shown_notice or stack_error
        if not cards and stack_error is None:
            message = f"Aucun échange ne fait gagner ce pool sur les données {version_label}"

    cached = cached_generation(db_path, lane, size, mode)
    generated = None
    if cached is not None and cached[0] is not None:
        generated = _generated_view(cached[0], cached[1], champions)

    return {
        "lane": lane,
        "pool": (
            {
                "name": pool.name,
                "champions": [portrait(champions, name) for name in pool.champions],
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
        "tree": tree_payload(tree, champions) if tree is not None else None,
        "drag_px": pool_stats_config.POOL_SWIPE_DRAG_PX,
        "sizes": list(
            range(pool_stats_config.POOL_GEN_MIN_SIZE, pool_stats_config.POOL_GEN_MAX_SIZE + 1)
        ),
        "size": size,
        "mode": mode,
        "exclusions": [portrait(champions, name) for name in excluded],
        "champion_names": champion_names(db_path),
        "generated": generated,
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
    excluded = load_pool_exclusions().get(lane, [])
    cards, _, stack_error = _stack(db_path, lane, pool.champions, passed, excluded)
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


def create_generated(
    manager: PoolManager,
    db_path: Union[str, Path],
    lane: str,
    size: Any,
    mode: Any,
) -> Tuple[str, str]:
    """Ajoute au gestionnaire le pool généré pour le poste, sous « <POSTE> GÉNÉRÉ <date> ».

    Un nom pris reçoit « (2) », « (3) »… Ne fait ni l'enregistrement ni la désignation au poste :
    c'est le rôle de la route. Renvoie (nom du pool, message).

    Raises:
        Refusal: poste inconnu, pas de pool généré, ou base illisible.
    """
    if lane not in ROLE_LABELS:
        raise Refusal("Poste inconnu")
    generated, _ = require_generated(db_path, lane, size, mode)
    base = f"{ROLE_LABELS[lane].upper()} GÉNÉRÉ {date.today().isoformat()}"
    name, number = base, 2
    while manager.get_pool(name) is not None:
        name = f"{base} ({number})"
        number += 1
    manager.create_pool(name, list(generated.champions), "Généré sur la Méta du poste", role=lane)
    return name, f"« {name} » créé ; désigné au poste {ROLE_LABELS[lane]}"


def exclude(db_path: Union[str, Path], lane: str, champion: str, remove: bool) -> str:
    """Exclut `champion` du générateur du poste, ou le rétablit si `remove` ; sans casse.

    Raises:
        Refusal: champion inconnu de la base, ou préférences non enregistrées.
    """
    names = {name.casefold(): name for name in champion_names(db_path)}
    canonical = names.get(champion.strip().casefold())
    if canonical is None:
        raise Refusal("Champion inconnu")
    if not save_pool_exclusion(lane, canonical, not remove):
        raise Refusal("Préférences non enregistrées")
    if remove:
        return f"{canonical} rétabli dans le générateur"
    return f"{canonical} exclu du générateur"
