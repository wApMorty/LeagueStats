"""Partie trouvée : l'état de la file lu dans le LCU, et la réponse du joueur (SPEC-21 tâche 93).

Le navigateur apprend qu'une partie est trouvée par le flux du bus (événements du WebSocket LCU) puis
relit l'état ici. Les lectures et les deux écritures (accepter, refuser) passent par `LcuProxy`.
"""

from typing import Any, Dict, Optional

from ..config_client import client_config
from ..user_prefs import load_user_prefs
from .draft_actions import Refusal
from .lcu_proxy import LcuProxy

PHASE = "/lol-gameflow/v1/gameflow-phase"
READY_CHECK = "/lol-matchmaking/v1/ready-check"
ANSWERS = {"accept": "accept", "decline": "decline"}


def state(proxy: LcuProxy) -> Dict[str, Any]:
    """Phase du client et, pendant la file trouvée, ce qu'il reste pour répondre."""
    phase = proxy.get(PHASE)
    phase = phase if isinstance(phase, str) else None
    answer: Optional[Dict[str, Any]] = None
    remaining = 0.0
    if phase == "ReadyCheck":
        check = proxy.get(READY_CHECK)
        if isinstance(check, dict):
            elapsed = float(check.get("timer") or 0.0)
            remaining = max(0.0, client_config.FOUND_SECONDS - elapsed)
            answer = {"state": check.get("state"), "response": check.get("playerResponse")}
    prefs = load_user_prefs()
    return {
        "phase": phase,
        "ready_check": answer,
        "remaining": remaining,
        "total": client_config.FOUND_SECONDS,
        "hold_max": client_config.FOUND_HOLD_MAX_S,
        "enter_wait": client_config.FOUND_ENTER_WAIT_S,
        "auto_accept": bool(prefs and prefs.auto_accept_queue),
    }


def answer(proxy: LcuProxy, name: str) -> Dict[str, Any]:
    """Accepte ou refuse la partie trouvée ; `Refusal` hors de la file trouvée ou si le client refuse."""
    if name not in ANSWERS:
        raise Refusal("Réponse inconnue")
    if proxy.get(PHASE) != "ReadyCheck":
        raise Refusal("Aucune partie trouvée à ce moment")
    if proxy.send("POST", f"{READY_CHECK}/{ANSWERS[name]}") is None:
        raise Refusal("Le client LoL a refusé la réponse")
    return {"answer": name}
