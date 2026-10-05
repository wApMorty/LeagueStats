"""Écran Collection : champions possédés, pages de runes, sets d'objets, lus dans le LCU (SPEC-21 tâche 79).

Lecture seule : l'import de pages et de sets reste le chemin de SPEC-15. Une seule vue est lue à la fois
(`?vue=`), la lecture d'un onglet n'est donc jamais payée par les autres. Fonctions pures, comme `profil.py`.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from .data import date_fr, plural
from .draft_view import Champions
from .lcu_proxy import LcuProxy
from .profil import SUMMONER

OWNED = "/lol-champions/v1/owned-champions-minimal"
PAGES = "/lol-perks/v1/pages"
SETS = "/lol-item-sets/v1/item-sets/{summoner_id}/sets"

VIEWS = (("champions", "Champions"), ("runes", "Pages de runes"), ("objets", "Sets d'objets"))
ROLES = (
    ("assassin", "Assassin"),
    ("fighter", "Combattant"),
    ("mage", "Mage"),
    ("marksman", "Tireur"),
    ("support", "Support"),
    ("tank", "Tank"),
)
# Le LCU sert les images de runes sous ce préfixe ; Data Dragon les a sous le même chemin relatif.
_PERK_ICON = re.compile(
    r"/lol-game-data/assets/v1/(perk-images/(?:[A-Za-z0-9_\-]+/)*[A-Za-z0-9_\-]+\.png)"
)


def _tabs(active: str) -> List[dict]:
    return [{"key": key, "label": label, "active": key == active} for key, label in VIEWS]


def champions_view(
    owned: Sequence[Dict[str, Any]], role: Optional[str], champions: Champions
) -> dict:
    """Les champions possédés par ordre alphabétique, filtrés par `role` (clé du LCU) s'il en est un."""
    role = role if role in dict(ROLES) else None
    ordered = sorted(owned, key=lambda c: c["name"].casefold())
    shown = [c for c in ordered if role is None or role in c["roles"]]
    labels = dict(ROLES)
    return {
        "view": "champions",
        "tabs": _tabs("champions"),
        "role": role,
        "roles": [{"key": k, "label": label, "active": k == role} for k, label in ROLES],
        "summary": f"{plural(len(shown), 'champion')} sur {len(owned)} possédés",
        "champions": [
            {
                "name": c["name"],
                "portrait": champions.image(c["id"]),
                "roles": [labels[r] for r in c["roles"] if r in labels],
                "free": bool(c.get("freeToPlay")) and not c["ownership"].get("owned"),
            }
            for c in shown
        ],
    }


def _icon(path: str) -> Optional[str]:
    match = _PERK_ICON.fullmatch(path or "")
    return f"/assets/perk/{match.group(1)}" if match else None


def runes_view(pages: Sequence[Dict[str, Any]]) -> dict:
    """Les pages de runes, la page active d'abord."""
    ordered = sorted(pages, key=lambda p: (not p["isActive"], p["name"].casefold()))
    return {
        "view": "runes",
        "tabs": _tabs("runes"),
        "summary": plural(len(pages), "page") + " de runes",
        "pages": [
            {
                "name": p["name"],
                "active": bool(p["isActive"]),
                "valid": bool(p["isValid"]),
                "keystone": p["pageKeystone"]["name"],
                "icon": _icon(p["pageKeystone"]["iconPath"]),
                "primary": p["primaryStyleName"],
                "secondary": p["secondaryStyleName"],
                "modified": date_fr(datetime.fromtimestamp(p["lastModified"] / 1000, timezone.utc)),
            }
            for p in ordered
        ],
    }


def items_view(item_sets: Dict[str, Any], champions: Champions) -> dict:
    """Les sets d'objets du compte : titre, champions associés, blocs et objets."""
    sets = []
    for entry in item_sets["itemSets"]:
        blocks = [
            {
                "type": block["type"],
                "items": [int(i["id"]) for i in block["items"] if str(i["id"]).isdigit()],
            }
            for block in entry["blocks"]
        ]
        sets.append(
            {
                "title": entry["title"],
                "champions": [
                    {"name": champions.name(c), "portrait": champions.image(c)}
                    for c in entry["associatedChampions"]
                ],
                "blocks": blocks,
                "count": sum(len(b["items"]) for b in blocks),
            }
        )
    return {
        "view": "objets",
        "tabs": _tabs("objets"),
        "summary": plural(len(sets), "set") + " d'objets",
        "sets": sets,
    }


def read_collection(
    proxy: LcuProxy, view: str, role: Optional[str], champions: Champions
) -> Optional[dict]:
    """Lit l'onglet demandé ; None si le LCU ne le sert pas."""
    if view == "runes":
        pages = proxy.get(PAGES)
        return None if pages is None else runes_view(pages)
    if view == "objets":
        me = proxy.get(SUMMONER)
        item_sets = proxy.get(SETS.format(summoner_id=int(me["summonerId"]))) if me else None
        return None if item_sets is None else items_view(item_sets, champions)
    owned = proxy.get(OWNED)
    return None if owned is None else champions_view(owned, role, champions)
