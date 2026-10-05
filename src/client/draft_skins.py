"""Skins du champion verrouillé : possession lue dans le LCU, choix écrit dans le champ select (SPEC-21 tâche 90).

Le LCU liste les skins d'un champion avec leur possession (`ownership.owned`) ; l'identifiant d'un skin est
`champion × 1000 + numéro`. La liste change rarement (un achat) : elle est gardée `SKINS_TTL_S` secondes
par champion. Les lectures et l'écriture passent par `LcuProxy` (liste blanche).
"""

import threading
import time
from typing import Any, Dict, List, Optional

from ..config_client import client_config
from .draft_actions import Refusal
from .lcu_proxy import LcuProxy

SELECTION = "/lol-champ-select/v1/session/my-selection"


class SkinBook:
    """Les skins par champion, avec leur possession, gardés quelques secondes."""

    def __init__(self, proxy: LcuProxy) -> None:
        self._proxy = proxy
        self._lock = threading.Lock()
        self._cache: Dict[int, tuple] = {}

    def skins(self, champion_id: int) -> Optional[List[Dict[str, Any]]]:
        """`[{id, num, name, owned, base}]`, ou None si le client LoL ne répond pas."""
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(champion_id)
            if cached and cached[0] > now:
                return cached[1]
        listed = self._read(champion_id)
        if listed is None:
            return None
        with self._lock:
            self._cache[champion_id] = (now + client_config.SKINS_TTL_S, listed)
        return listed

    def _read(self, champion_id: int) -> Optional[List[Dict[str, Any]]]:
        me = self._proxy.get("/lol-summoner/v1/current-summoner") or {}
        summoner_id = me.get("summonerId")
        if summoner_id is None:
            return None
        raw = self._proxy.get(
            f"/lol-champions/v1/inventories/{summoner_id}/champions/{champion_id}/skins"
        )
        if not isinstance(raw, list):
            return None
        skins = [
            {
                "id": skin["id"],
                "num": skin["id"] - champion_id * 1000,
                "name": skin.get("name") or "",
                "owned": bool((skin.get("ownership") or {}).get("owned")),
                "base": bool(skin.get("isBase")),
            }
            for skin in raw
            if isinstance(skin.get("id"), int) and not skin.get("isChromaVariant")
        ]
        return sorted(skins, key=lambda skin: skin["num"])


def select_skin(proxy: LcuProxy, book: SkinBook, champion_id: int, skin_id: int) -> Dict[str, Any]:
    """Écrit le skin choisi dans le champ select ; `Refusal` s'il n'est pas possédé ou hors de propos."""
    if champion_id <= 0 or skin_id // 1000 != champion_id:
        raise Refusal("Ce skin n'est pas celui de ton champion")
    skins = book.skins(champion_id)
    skin = next((s for s in skins or [] if s["id"] == skin_id), None)
    if skin is None:
        raise Refusal("Skin inconnu ou liste des skins indisponible")
    if not skin["owned"]:
        raise Refusal("Tu ne possèdes pas ce skin")
    if proxy.send("PATCH", SELECTION, {"selectedSkinId": skin_id}) is None:
        raise Refusal("Le client LoL a refusé le skin")
    return {"skin_id": skin_id}
