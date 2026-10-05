"""Écran Social, en lecture seule : amis, statuts et conversations du client LoL (SPEC-21 tâche 82).

Aucun message, aucune invitation, aucune gestion d'amis (SPEC-21 §2, §7) : ce module ne lit que `me`,
`friends` et `conversations`, et la liste blanche n'ouvre aucune écriture sur `/lol-chat`. Fonctions pures.
Les pseudos, statuts et messages viennent d'autres joueurs : Jinja les échappe, rien d'autre n'en est fait.
"""

from typing import Any, Dict, List, Optional, Sequence

from ..config_client import client_config
from .draft_view import Champions
from .lcu_proxy import LcuProxy
from .profil import _tier

ME = "/lol-chat/v1/me"
FRIENDS = "/lol-chat/v1/friends"
CONVERSATIONS = "/lol-chat/v1/conversations"

# disponibilité du LCU -> (libellé, classe de la pastille)
AVAILABILITY = {
    "chat": ("En ligne", "ok"),
    "away": ("Absent", "away"),
    "dnd": ("Ne pas déranger", "dnd"),
    "mobile": ("Sur mobile", "mobile"),
    "offline": ("Hors ligne", "off"),
}
QUEUE_TYPES = {"RANKED_SOLO_5x5": "Classée solo/duo", "RANKED_FLEX_SR": "Classée flexible"}
IN_GAME = "inGame"


def _name(person: Dict[str, Any]) -> str:
    return person.get("gameName") or person.get("name") or "Inconnu"


def _rank(lol: Dict[str, Any]) -> Optional[str]:
    tier = lol.get("rankedLeagueTier") or ""
    return _tier(tier, lol.get("rankedLeagueDivision") or "") if tier else None


def _activity(person: Dict[str, Any], champions: Champions) -> str:
    """Ce que fait l'ami : la partie en cours, un lobby, ou son message de statut."""
    lol = person.get("lol") or {}
    status = lol.get("gameStatus") or ""
    if status == IN_GAME:
        queue = QUEUE_TYPES.get(
            lol.get("gameQueueType") or ""
        ) or client_config.GAME_QUEUE_NAMES.get(
            int(lol["queueId"]) if str(lol.get("queueId", "")).isdigit() else 0, "En partie"
        )
        champion = lol.get("championId") or ""
        return f"En partie · {queue}" + (
            f" · {champions.name(int(champion))}"
            if str(champion).isdigit() and champion != "0"
            else ""
        )
    if status.startswith("hosting_") or status in ("championSelect", "inQueue", "teamSelect"):
        return "Dans un lobby"
    if status == "spectating":
        return "Regarde une partie"
    return person.get("statusMessage") or ""


def _friend(person: Dict[str, Any], champions: Champions) -> dict:
    label, kind = AVAILABILITY.get(person.get("availability") or "offline", AVAILABILITY["offline"])
    lol = person.get("lol") or {}
    return {
        "name": _name(person),
        "tag": person.get("gameTag") or "",
        "icon": f"/assets/profileicon/{person['icon']}.png" if person.get("icon") else None,
        "status": label,
        "kind": kind,
        "activity": _activity(person, champions),
        "rank": _rank(lol),
        "in_game": lol.get("gameStatus") == IN_GAME and kind != "off",
        "group": person.get("groupName") or "",
    }


def _conversation(conversation: Dict[str, Any]) -> dict:
    message = (conversation.get("lastMessage") or "").strip()
    limit = client_config.SOCIAL_MESSAGE_CHARS
    return {
        "name": _name(conversation),
        "unread": int(conversation.get("unreadMessageCount") or 0),
        "muted": bool(conversation.get("isMuted")),
        "last": message if len(message) <= limit else message[: limit - 1] + "…",
    }


def social_view(
    me: Dict[str, Any],
    friends: Sequence[Dict[str, Any]],
    conversations: Sequence[Dict[str, Any]],
    champions: Champions,
) -> dict:
    """Le profil de chat, les amis par état (en partie, en ligne, hors ligne) et les conversations."""
    rows = sorted((_friend(f, champions) for f in friends), key=lambda r: r["name"].casefold())
    in_game = [r for r in rows if r["in_game"]]
    online = [r for r in rows if r["kind"] != "off" and not r["in_game"]]
    offline: List[dict] = [r for r in rows if r["kind"] == "off"]
    label, kind = AVAILABILITY.get(me.get("availability") or "chat", AVAILABILITY["chat"])
    return {
        "me": {
            "name": _name(me),
            "tag": me.get("gameTag") or "",
            "icon": f"/assets/profileicon/{me['icon']}.png" if me.get("icon") else None,
            "status": label,
            "kind": kind,
            "message": me.get("statusMessage") or "",
            "rank": _rank(me.get("lol") or {}),
        },
        "summary": f"{len(rows)} amis · {len(in_game) + len(online)} connectés · {len(in_game)} en partie",
        "in_game": in_game,
        "online": online,
        "offline": offline,
        "conversations": [_conversation(c) for c in conversations],
        "unread": sum(int(c.get("unreadMessageCount") or 0) for c in conversations),
    }


def read_social(proxy: LcuProxy, champions: Champions) -> Optional[dict]:
    """Lit le chat du client ; None si son profil n'est pas servi (amis et conversations peuvent manquer)."""
    me = proxy.get(ME)
    if me is None:
        return None
    return social_view(me, proxy.get(FRIENDS) or [], proxy.get(CONVERSATIONS) or [], champions)
