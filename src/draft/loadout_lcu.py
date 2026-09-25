"""Écritures de la build dans le client au lock-in (SPEC-15 §3.3).

Runes, set d'items et sorts, chacun best-effort : seuls la page et le set
préfixés ``draft_config.LOADOUT_PREFIX`` sont jamais remplacés.
"""

import uuid
from collections import Counter
from typing import Dict, List, Optional

from ..config_constants import draft_config
from .loadout import Build

FLASH_SPELL_ID = 4


def _owned_by_coach(name) -> bool:
    return str(name or "").startswith(draft_config.LOADOUT_PREFIX)


def _ordered_perks(lcu, build: Build) -> List[int]:
    """Runes rangées par emplacement (principal puis secondaire).

    OneTricks les donne triées par id ; l'ordre attendu par le LCU se lit dans
    /lol-perks/v1/styles. Faute de styles lisibles, on garde l'ordre reçu.
    """
    try:
        styles = {style["id"]: style for style in lcu._make_request("/lol-perks/v1/styles")}
        ordered = [
            perk
            for style_id in (build.primary_style, build.sub_style)
            for slot in styles[style_id]["slots"]
            for perk in slot["perks"]
            if perk in build.perks
        ]
    except (KeyError, TypeError):
        return list(build.perks)
    return ordered if sorted(ordered) == sorted(build.perks) else list(build.perks)


def _apply_runes(lcu, build: Build, name: str) -> Optional[str]:
    """Remplace la page « LS » ; ne touche jamais aux pages du joueur."""
    pages = lcu._make_request("/lol-perks/v1/pages")
    if pages is None:
        return "pages de runes illisibles"
    for page in pages:
        if _owned_by_coach(page.get("name")):
            lcu._make_request(f"/lol-perks/v1/pages/{page['id']}", "DELETE")
    player_pages = [p for p in pages if p.get("isDeletable") and not _owned_by_coach(p.get("name"))]
    owned = (lcu._make_request("/lol-perks/v1/inventory") or {}).get("ownedPageCount")
    if owned is not None and len(player_pages) >= owned:
        return "aucun emplacement de page de runes libre"
    created = lcu._make_request(
        "/lol-perks/v1/pages",
        "POST",
        {
            "name": draft_config.LOADOUT_PREFIX + name,
            "primaryStyleId": build.primary_style,
            "subStyleId": build.sub_style,
            "selectedPerkIds": _ordered_perks(lcu, build) + list(build.shards),
            "current": True,
        },
    )
    return None if created is not None else "page de runes refusée par le client"


def _apply_items(lcu, build: Build, champion_id: int, name: str) -> Optional[str]:
    """Remplace le set « LS » ; les sets du joueur sont renvoyés à l'identique."""
    summoner_id = (lcu._make_request("/lol-summoner/v1/current-summoner") or {}).get("summonerId")
    if summoner_id is None:
        return "invocateur inconnu"
    endpoint = f"/lol-item-sets/v1/item-sets/{summoner_id}/sets"
    current = lcu._make_request(endpoint)
    if current is None:
        return "sets d'items illisibles"
    item_set = {
        "uid": str(uuid.uuid4()),
        "title": draft_config.LOADOUT_PREFIX + name,
        "type": "custom",
        "map": "any",
        "mode": "any",
        "priority": False,
        "sortrank": 0,
        "startedFrom": "blank",
        "associatedChampions": [champion_id],
        "associatedMaps": [],
        "blocks": [
            {
                "type": title,
                "items": [{"id": str(item), "count": n} for item, n in Counter(items).items()],
            }
            for title, items in build.item_blocks
            if items
        ],
    }
    kept = [s for s in current.get("itemSets", []) if not _owned_by_coach(s.get("title"))]
    saved = lcu._make_request(endpoint, "PUT", {**current, "itemSets": kept + [item_set]})
    return None if saved is not None else "set d'items refusé par le client"


def _local_player(session: dict) -> dict:
    cell_id = session.get("localPlayerCellId")
    return next((m for m in session.get("myTeam", []) if m.get("cellId") == cell_id), {})


def _apply_spells(lcu, build: Build) -> Optional[str]:
    """Pose les sorts en gardant Flash sur la touche où le joueur l'avait."""
    spell1, spell2 = build.spells
    me = _local_player(lcu.get_champion_select_session() or {})
    if FLASH_SPELL_ID in build.spells:
        other = spell2 if spell1 == FLASH_SPELL_ID else spell1
        if me.get("spell1Id") == FLASH_SPELL_ID:
            spell1, spell2 = FLASH_SPELL_ID, other
        elif me.get("spell2Id") == FLASH_SPELL_ID:
            spell1, spell2 = other, FLASH_SPELL_ID
    done = lcu._make_request(
        "/lol-champ-select/v1/session/my-selection",
        "PATCH",
        {"spell1Id": spell1, "spell2Id": spell2},
    )
    if done is None:
        return "sorts refusés par le client"
    # Relu dans la session : un PATCH accepté puis ignoré (fin de draft) doit
    # se voir en console plutôt que passer pour un succès.
    me = _local_player(lcu.get_champion_select_session() or {})
    if (me.get("spell1Id"), me.get("spell2Id")) != (spell1, spell2):
        return "sorts ignorés par le client"
    return None


def apply_build(lcu, build: Build, champion_id: int, name: str) -> Dict[str, Optional[str]]:
    """Les trois écritures, indépendantes et best-effort.

    Renvoie, par écriture (``runes``, ``items``, ``sorts``), None si elle a
    réussi, sinon la raison de l'échec. Ne lève jamais : une erreur du client
    ne doit pas interrompre la boucle de draft.
    """
    writes = {
        "runes": lambda: _apply_runes(lcu, build, name),
        "items": lambda: _apply_items(lcu, build, champion_id, name),
        "sorts": lambda: _apply_spells(lcu, build),
    }
    outcome: Dict[str, Optional[str]] = {}
    for part, write in writes.items():
        try:
            outcome[part] = write()
        except Exception as error:  # best-effort : aucune erreur ne remonte
            outcome[part] = f"erreur inattendue ({type(error).__name__})"
    return outcome
