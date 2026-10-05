"""Lobby et file d'attente du client : voir, créer, choisir ses postes, quitter, lancer, annuler (SPEC-21 tâches 80 et 81).

Les lectures et les écritures passent par `LcuProxy` (liste blanche). Une action n'est acceptée que dans la
phase du client où elle a un sens, lue au moment de l'appel : sinon `Refusal`, avec une raison lisible et
aucune écriture sur le LCU (comme `draft_actions.py`). Les files proposées sont celles du LCU, réduites aux
files non personnalisées de la Faille et de l'ARAM (SPEC-21 §10) ; jamais une file que le front aurait inventée.
"""

from typing import Any, Dict, List, Optional, Sequence

from ..config_client import client_config
from ..user_prefs import load_user_prefs
from .draft_actions import Refusal
from .lcu_proxy import LcuProxy

PHASE = "/lol-gameflow/v1/gameflow-phase"
QUEUES = "/lol-game-queues/v1/queues"
LOBBY = "/lol-lobby/v2/lobby"
POSITIONS = f"{LOBBY}/members/localMember/position-preferences"
SEARCH = f"{LOBBY}/matchmaking/search"
SEARCH_STATE = f"{SEARCH}-state"
MATCHMAKING = "/lol-matchmaking/v1/search"

POSITION_LABELS = {
    "TOP": "Top",
    "JUNGLE": "Jungle",
    "MIDDLE": "Mid",
    "BOTTOM": "Bot",
    "UTILITY": "Support",
    "FILL": "Remplissage",
}
CATEGORIES = {"PvP": "Joueur contre joueur", "VersusAi": "Contre l'IA"}


def _clock(seconds: float) -> str:
    return f"{int(seconds) // 60}:{int(seconds) % 60:02d}"


def _position(code: Optional[str]) -> str:
    return POSITION_LABELS.get(code or "", "—")


# ---------- files proposées ----------


def queue_choices(queues: Sequence[Dict[str, Any]]) -> List[dict]:
    """Les files qu'on peut ouvrir, par catégorie : disponibles, visibles, non personnalisées, de la Faille
    ou de l'ARAM."""
    groups: Dict[str, List[dict]] = {}
    for queue in queues:
        if (
            queue["queueAvailability"] != "Available"
            or not queue["isVisible"]
            or queue["isCustom"]
            or queue["gameSelectModeGroup"] not in client_config.LOBBY_QUEUE_GROUPS
            or queue["category"] not in CATEGORIES
        ):
            continue
        name = (
            client_config.GAME_QUEUE_NAMES.get(queue["id"]) or queue["name"] or queue["shortName"]
        )
        if name:
            groups.setdefault(queue["category"], []).append(
                {"id": queue["id"], "name": name, "positions": bool(queue["showPositionSelector"])}
            )
    return [
        {"label": label, "queues": sorted(groups[key], key=lambda q: q["name"].casefold())}
        for key, label in CATEGORIES.items()
        if key in groups
    ]


# ---------- vue ----------


def _member(member: Dict[str, Any], mine: Optional[str]) -> dict:
    return {
        "name": member.get("summonerName") or "Inconnu",
        "icon": (
            f"/assets/profileicon/{member['summonerIconId']}.png"
            if member.get("summonerIconId")
            else None
        ),
        "level": member.get("summonerLevel"),
        "leader": bool(member.get("isLeader")),
        "ready": bool(member.get("ready")),
        "bot": bool(member.get("isBot")),
        "mine": member.get("puuid") == mine,
        "first": _position(member.get("firstPositionPreference")),
        "second": _position(member.get("secondPositionPreference")),
    }


def _queue_name(lobby: Dict[str, Any], queues: Sequence[Dict[str, Any]]) -> str:
    queue_id = lobby["gameConfig"]["queueId"]
    named = next((q["name"] for q in queues if q["id"] == queue_id), "")
    return client_config.GAME_QUEUE_NAMES.get(queue_id) or named or f"File {queue_id}"


def lobby_view(
    lobby: Optional[Dict[str, Any]],
    queues: Sequence[Dict[str, Any]],
    phase: Optional[str],
    search: Optional[Dict[str, Any]] = None,
) -> dict:
    """Sans lobby, les files à ouvrir ; dans un lobby, sa file, ses membres, mes postes et la recherche."""
    base = {"phase": phase, "choices": queue_choices(queues)}
    if lobby is None:
        return {**base, "in_lobby": False, "can_create": phase in client_config.LOBBY_CREATE_PHASES}
    local = lobby["localMember"]
    config = lobby["gameConfig"]
    members = [_member(m, local.get("puuid")) for m in lobby["members"]]
    restrictions = [str(r.get("restrictionCode", "?")) for r in lobby.get("restrictions") or []]
    return {
        **base,
        "in_lobby": True,
        "can_create": phase in client_config.LOBBY_CREATE_PHASES,
        "queue": _queue_name(lobby, queues),
        "members": members,
        "free_slots": max(0, config["maxLobbySize"] - len(members)),
        "positions": {
            "shown": bool(config.get("showPositionSelector")),
            "first": local.get("firstPositionPreference") or "",
            "second": local.get("secondPositionPreference") or "",
            "options": [(code, label) for code, label in POSITION_LABELS.items()],
            "editable": phase == "Lobby",
        },
        "leader": bool(local.get("isLeader")),
        "restrictions": restrictions,
        "searching": phase == "Matchmaking",
        "can_leave": phase == "Lobby",
        "can_start": phase == "Lobby"
        and bool(lobby["canStartActivity"])
        and bool(local.get("allowedStartActivity")),
        "search": search,
    }


def _search_info(proxy: LcuProxy, phase: Optional[str]) -> Optional[dict]:
    """La recherche en cours : état, temps écoulé et estimation (lus seulement pendant la file)."""
    if phase != "Matchmaking":
        return None
    state = proxy.get(SEARCH_STATE) or {}
    queue = proxy.get(MATCHMAKING) or {}
    info = {
        "state": state.get("searchState") or queue.get("searchState"),
        "elapsed": float(queue.get("timeInQueue") or 0.0),
        "estimated": float(queue.get("estimatedQueueTime") or 0.0),
        "errors": [str(e.get("message") or e.get("errorType")) for e in state.get("errors") or []],
    }
    info["elapsed_text"] = _clock(info["elapsed"])
    info["estimated_text"] = _clock(info["estimated"]) if info["estimated"] else None
    return info


def read_lobby(proxy: LcuProxy) -> dict:
    """L'écran Lobby ; le lobby est absent (404) hors lobby, c'est l'état normal."""
    phase = proxy.get(PHASE)
    phase = phase if isinstance(phase, str) else None
    queues = proxy.get(QUEUES) or []
    lobby = proxy.get(LOBBY) if phase in ("Lobby", "Matchmaking") else None
    return lobby_view(lobby, queues, phase, _search_info(proxy, phase))


# ---------- actions ----------


def _phase(proxy: LcuProxy) -> Optional[str]:
    phase = proxy.get(PHASE)
    return phase if isinstance(phase, str) else None


def _refused(result: Optional[Any], reason: str) -> Dict[str, Any]:
    if result is None:
        raise Refusal(reason)
    return {"ok": True}


def create(proxy: LcuProxy, queue_id: int) -> Dict[str, Any]:
    """Ouvre un lobby pour une file de la liste proposée ; `Refusal` sinon, sans écriture."""
    phase = _phase(proxy)
    if phase not in client_config.LOBBY_CREATE_PHASES:
        raise Refusal("Impossible d'ouvrir un lobby pendant la file, la draft ou une partie")
    allowed = {q["id"] for group in queue_choices(proxy.get(QUEUES) or []) for q in group["queues"]}
    if queue_id not in allowed:
        raise Refusal("Cette file n'est pas disponible")
    return _refused(
        proxy.send("POST", LOBBY, {"queueId": queue_id}), "Le client LoL a refusé d'ouvrir le lobby"
    )


def leave(proxy: LcuProxy) -> Dict[str, Any]:
    """Quitte le lobby ; pendant la file, il faut d'abord l'annuler."""
    phase = _phase(proxy)
    if phase == "Matchmaking":
        raise Refusal("Annule d'abord la recherche de partie")
    if phase != "Lobby":
        raise Refusal("Tu n'es dans aucun lobby")
    return _refused(proxy.send("DELETE", LOBBY), "Le client LoL a refusé de quitter le lobby")


def set_positions(proxy: LcuProxy, first: str, second: str) -> Dict[str, Any]:
    """Écrit mes deux postes préférés ; seulement dans un lobby dont la file en demande."""
    for code in (first, second):
        if code not in client_config.LOBBY_POSITIONS:
            raise Refusal(f"Poste inconnu : {code}")
    if first == second and first != "FILL":
        raise Refusal("Choisis deux postes différents")
    if _phase(proxy) != "Lobby":
        raise Refusal("Les postes se choisissent dans le lobby, hors recherche")
    lobby = proxy.get(LOBBY)
    if not lobby or not lobby["gameConfig"].get("showPositionSelector"):
        raise Refusal("Cette file n'a pas de choix de poste")
    return _refused(
        proxy.send("PUT", POSITIONS, {"firstPreference": first, "secondPreference": second}),
        "Le client LoL a refusé ces postes",
    )


# ---------- file d'attente (tâche 81) ----------


def file_state(proxy: LcuProxy) -> Dict[str, Any]:
    """Ce que la barre de titre affiche : lancer, la recherche en cours, ou rien."""
    phase = _phase(proxy)
    lobby = proxy.get(LOBBY) if phase in ("Lobby", "Matchmaking") else None
    search = _search_info(proxy, phase)
    local = (lobby or {}).get("localMember") or {}
    prefs = load_user_prefs()
    return {
        "phase": phase,
        "in_lobby": lobby is not None,
        "can_start": bool(
            phase == "Lobby"
            and lobby
            and lobby["canStartActivity"]
            and local.get("allowedStartActivity")
        ),
        "searching": phase == "Matchmaking",
        "elapsed": search["elapsed"] if search else 0.0,
        "estimated": search["estimated"] if search else 0.0,
        "queue": _queue_name(lobby, proxy.get(QUEUES) or []) if lobby else None,
        "auto_accept": bool(prefs and prefs.auto_accept_queue),
    }


def start(proxy: LcuProxy) -> Dict[str, Any]:
    """Lance la recherche de partie du lobby ; réservée au chef du groupe, hors recherche."""
    phase = _phase(proxy)
    if phase == "Matchmaking":
        raise Refusal("La recherche est déjà lancée")
    if phase != "Lobby":
        raise Refusal("Ouvre d'abord un lobby")
    lobby = proxy.get(LOBBY)
    if not lobby:
        raise Refusal("Ouvre d'abord un lobby")
    if not lobby["localMember"].get("allowedStartActivity"):
        raise Refusal("Seul le chef du groupe lance la recherche")
    if not lobby["canStartActivity"]:
        codes = ", ".join(
            str(r.get("restrictionCode", "?")) for r in lobby.get("restrictions") or []
        )
        raise Refusal("Le lobby ne peut pas lancer la recherche" + (f" ({codes})" if codes else ""))
    return _refused(proxy.send("POST", SEARCH), "Le client LoL a refusé de lancer la recherche")


def cancel(proxy: LcuProxy) -> Dict[str, Any]:
    """Annule la recherche de partie en cours ; refusée hors recherche (jamais une partie trouvée)."""
    if _phase(proxy) != "Matchmaking":
        raise Refusal("Aucune recherche en cours")
    return _refused(proxy.send("DELETE", SEARCH), "Le client LoL a refusé d'annuler la recherche")
