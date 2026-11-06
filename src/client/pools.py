"""Écran Pool : le pool par défaut du Live Coach, la désignation d'un pool par poste et l'édition des
pools perso.

Les pools système (« All Top Champions », « Meta Picks ») se choisissent mais ne s'éditent pas : on les
duplique. Le pool par défaut et les désignations par poste (`pools_by_role`) sont mémorisés dans
`user_prefs.json`. Un changement ou une édition du pool par défaut est aussi déposé chez le Live Coach
(commande `pool <nom>`), qui le recharge dès sa prochaine draft ; une désignation de poste n'y dépose
rien, elle s'applique à la prochaine draft. Les bans précalculés d'un pool édité sont effacés : sans
eux, le Live Coach recalcule à la volée au lieu de servir une liste périmée.
"""

import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple, Union

from ..pool_manager import PoolManager, resolve_pool_for_lane
from ..user_prefs import load_user_prefs, save_pool_name, save_role_pool
from .db import read_only, writable
from .draft_actions import Refusal

SYSTEM_HINT = "Pool système : duplique-le pour le modifier"

# Textes d'interface des postes (pas un réglage) ; l'ordre est celui de l'écran.
ROLE_LABELS = {
    "top": "Top",
    "jungle": "Jungle",
    "middle": "Mid",
    "bottom": "ADC",
    "support": "Support",
}


def champion_names(db_path: Union[str, Path]) -> List[str]:
    """Les champions connus de la base, ordre alphabétique ; vide si la base est absente ou corrompue."""
    try:
        with read_only(db_path) as db:
            rows = db.connection.execute("SELECT name FROM champions ORDER BY name").fetchall()
    except sqlite3.Error:
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
    """La liste des pools, le pool ouvert (le pool par défaut à défaut) et sa grille de champions.

    `roles` donne le pool résolu pour chaque poste (`ROLE_LABELS`, dans l'ordre de l'écran) ; le
    détail ouvert ajoute `roles_on` (postes où il est désigné) et chaque entrée de `pools` ajoute
    `roles` (libellés des postes qui le désignent).
    """
    active = active_pool_name(manager)
    prefs = load_user_prefs()
    pools_by_role = prefs.pools_by_role if prefs else {}
    roles = []
    for lane, label in ROLE_LABELS.items():
        pool, source = resolve_pool_for_lane(manager, lane, pools_by_role, active)
        roles.append(
            {
                "lane": lane,
                "label": label,
                "pool": pool.name if pool else None,
                "source": source,
            }
        )
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
            "roles_on": [
                r["lane"] for r in roles if r["pool"] == pool.name and r["source"] == "poste"
            ],
        }
    return {
        "notice": notice,
        "active": active,
        "roles": roles,
        "selected": detail,
        "pools": [
            {
                "name": p.name,
                "size": p.size(),
                "system": p.created_by == "system",
                "active": p.name == active,
                "open": bool(detail) and p.name == detail["name"],
                "roles": [
                    ROLE_LABELS[lane]
                    for lane, name in pools_by_role.items()
                    if name == p.name and lane in ROLE_LABELS
                ],
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
        return f"Pool actif : « {name} » (appliqué dès la prochaine draft)", name
    if action == "role":
        if arg not in ROLE_LABELS:
            raise Refusal("Poste inconnu")
        label = ROLE_LABELS[arg]
        designated = load_user_prefs()
        already = designated is not None and designated.pools_by_role.get(arg) == name
        if not save_role_pool(arg, None if already else name):
            raise Refusal("Préférences non enregistrées")
        if already:
            return f"Poste {label} : plus de pool désigné", name
        return f"Pool « {name} » pour le poste {label} (appliqué dès la prochaine draft)", name
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
