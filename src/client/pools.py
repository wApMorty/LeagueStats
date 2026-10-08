"""Écran Pool : le pool actif du Live Coach et l'édition des pools perso.

Les pools système (« All Top Champions », « Meta Picks ») se choisissent mais ne s'éditent pas : on les
duplique. Le pool actif est lu au lancement du Live Coach (`user_prefs.json`) ; un changement vaut donc
dès son prochain démarrage. Les bans précalculés d'un pool édité sont effacés : sans eux, le Live Coach
recalcule à la volée au lieu de servir une liste périmée.
"""

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple, Union

from ..pool_manager import PoolManager
from ..user_prefs import load_user_prefs, save_pool_name
from .db import read_only, writable
from .draft_actions import Refusal

SYSTEM_HINT = "Pool système : duplique-le pour le modifier"


def champion_names(db_path: Union[str, Path]) -> List[str]:
    """Les champions connus de la base, ordre alphabétique ; vide si la base est absente."""
    try:
        with read_only(db_path) as db:
            rows = db.connection.execute("SELECT name FROM champions ORDER BY name").fetchall()
    except sqlite3.OperationalError:
        return []
    return [row[0] for row in rows]


def active_pool_name(manager: PoolManager) -> Optional[str]:
    """Le pool mémorisé s'il existe encore (même règle que le lancement du Live Coach)."""
    prefs = load_user_prefs()
    name = prefs.pool_name if prefs else None
    return name if name and manager.get_pool(name) else None


def pools_view(
    manager: PoolManager,
    selected: Optional[str],
    names: List[str],
    notice: Optional[str] = None,
) -> dict:
    """La liste des pools, le pool ouvert (le pool actif à défaut) et sa grille de champions."""
    active = active_pool_name(manager)
    ordered = sorted(
        manager.get_all_pools().values(),
        key=lambda p: (p.created_by == "system", p.name.casefold()),
    )
    pool = manager.get_pool(selected or "") or manager.get_pool(active or "")
    pool = pool or (ordered[0] if ordered else None)
    detail = None
    if pool:
        members = set(pool.champions)
        # Un champion du pool absent de la base (renommé, retiré) reste visible, donc retirable.
        universe = sorted(set(names) | members, key=str.casefold)
        detail = {
            "name": pool.name,
            "description": pool.description,
            "editable": pool.created_by == "user",
            "active": pool.name == active,
            "size": len(members),
            "champions": [{"name": n, "on": n in members} for n in universe],
        }
    return {
        "notice": notice,
        "active": active,
        "selected": detail,
        "pools": [
            {
                "name": p.name,
                "size": p.size(),
                "system": p.created_by == "system",
                "active": p.name == active,
                "open": bool(detail) and p.name == detail["name"],
            }
            for p in ordered
        ],
    }


def edit(
    manager: PoolManager, action: str, name: str, names: List[str], arg: str = ""
) -> Tuple[str, Optional[str]]:
    """Applique `action` en mémoire.

    Returns:
        (note affichée, pool à ouvrir ensuite ; None après une suppression).

    Raises:
        Refusal: action inconnue, pool inconnu ou système, nom vide ou déjà pris, champion inconnu.
    """
    arg = arg.strip()
    if action == "creer":
        if not arg or not manager.create_pool(arg, []):
            raise Refusal("Nom de pool vide ou déjà pris")
        return f"Pool « {arg} » créé", arg
    pool = manager.get_pool(name)
    if pool is None:
        raise Refusal("Pool inconnu")
    if action == "actif":
        if not save_pool_name(name):
            raise Refusal("Préférences non enregistrées")
        return f"Pool actif : « {name} » (pris en compte au prochain lancement du Live Coach)", name
    if action == "dupliquer":
        if not arg or not manager.duplicate_pool(name, arg):
            raise Refusal("Nom de pool vide ou déjà pris")
        return f"« {name} » dupliqué en « {arg} »", arg
    if pool.created_by == "system":
        raise Refusal(SYSTEM_HINT)
    if action == "supprimer":
        manager.delete_pool(name)
        return f"Pool « {name} » supprimé", None
    if action in ("ajouter", "retirer"):
        known = {n.casefold(): n for n in names} | {n.casefold(): n for n in pool.champions}
        champion = known.get(arg.casefold())
        if champion is None:
            raise Refusal(f"Champion inconnu : « {arg} »")
        done = (
            pool.add_champion(champion) if action == "ajouter" else pool.remove_champion(champion)
        )
        verb = "ajouté à" if action == "ajouter" else "retiré de"
        return (f"{champion} {verb} « {name} »" if done else f"{champion} : rien à changer"), name
    raise Refusal("Action inconnue")


def forget_bans(db_path: Union[str, Path], pool_name: str) -> None:
    """Efface les bans précalculés du pool (best-effort : table ou base absente, on passe)."""
    try:
        with writable(db_path) as db:
            db.connection.execute(
                "DELETE FROM pool_ban_recommendations WHERE pool_name = ?", (pool_name,)
            )
            db.connection.commit()
    except sqlite3.Error:
        pass
