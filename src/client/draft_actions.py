"""Actions de draft déclenchées par le client : survoler, verrouiller, bannir (SPEC-21 tâche 74).

Une action n'est acceptée que pour la phase et le tour courants, lus dans la session du champ select
au moment de l'appel : sinon `Refusal`, avec une raison lisible et aucune écriture sur le LCU. Les
écritures passent par `LcuProxy` (liste blanche).
"""

import re
from typing import Any, Dict, Optional

from ..config_constants import scraping_config
from .lcu_proxy import LcuProxy

SESSION = "/lol-champ-select/v1/session"

# action -> (type d'action LCU attendu, `completed` à écrire, liste des champions permis)
ACTIONS = {
    "hover": ("pick", False, "pickable-champion-ids"),
    "lock": ("pick", True, "pickable-champion-ids"),
    "hover_ban": ("ban", False, "bannable-champion-ids"),
    "ban": ("ban", True, "bannable-champion-ids"),
}
_TYPE_LABEL = {"pick": "picker", "ban": "bannir"}
_CHAMPION = re.compile(
    r"\S+"
)  # un seul mot : la commande de rôle du Live Coach se coupe sur les blancs


class Refusal(Exception):
    """L'action est refusée avant tout appel d'écriture ; le message s'affiche tel quel."""


def current_action(session: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """L'action en cours du joueur local (non terminée, et en cours si le LCU l'indique)."""
    cell_id = session.get("localPlayerCellId")
    for action_set in session.get("actions", []):
        for action in action_set:
            if (
                action.get("actorCellId") == cell_id
                and not action.get("completed", False)
                and action.get("isInProgress", True)
            ):
                return action
    return None


def _refusal_reason(session: Dict[str, Any], expected: str, champion_id: int) -> str:
    """Pourquoi le client LoL a refusé, d'après la session ; message générique si rien n'explique."""
    actions = [action for action_set in session.get("actions", []) for action in action_set]
    taken = lambda kind: any(  # noqa: E731
        a.get("type") == kind and a.get("completed") and a.get("championId") == champion_id
        for a in actions
    )
    me = session.get("localPlayerCellId")
    if taken("ban"):
        return "Ce champion est déjà banni"
    if taken("pick"):
        return "Ce champion est déjà pris"
    if (
        expected == "ban"
        and session.get("disallowBanningTeammateHoveredChampions")
        and any(
            p.get("cellId") != me and p.get("championPickIntent") == champion_id
            for p in session.get("myTeam", [])
        )
    ):
        return "Un coéquipier survole ce champion : le client interdit de le bannir"
    return "Le client LoL a refusé l'action"


def run(proxy: LcuProxy, name: str, champion_id: int) -> Dict[str, Any]:
    """Exécute l'action `name` sur `champion_id` ; lève `Refusal` si elle n'est pas permise."""
    if name not in ACTIONS:
        raise Refusal("Action inconnue")
    expected, completed, allowed = ACTIONS[name]
    if champion_id <= 0:
        raise Refusal("Champion inconnu")
    session = proxy.get(SESSION)
    if not session:
        raise Refusal("Pas de champ select en cours")
    action = current_action(session)
    if action is None:
        raise Refusal("Ce n'est pas ton tour")
    if action.get("type") != expected:
        raise Refusal(f"Ce n'est pas le moment de {_TYPE_LABEL[expected]}")
    permitted = proxy.get(f"/lol-champ-select/v1/{allowed}")
    # Relevé SPEC-24 : en phase de bans la liste ne vaut que `[-1]` : sans identifiant réel elle ne
    # dit rien, c'est le client LoL qui tranche.
    real = [i for i in permitted if i > 0] if isinstance(permitted, list) else []
    if real and champion_id not in real:
        raise Refusal("Ce champion n'est pas disponible")
    result = proxy.send(
        "PATCH",
        f"/lol-champ-select/v1/session/actions/{action['id']}",
        {"championId": champion_id, "completed": completed, "type": expected},
    )
    if result is None:
        raise Refusal(_refusal_reason(session, expected, champion_id))
    return {"action": name, "champion_id": champion_id, "completed": completed}


def role_command(champion: str, lane: str) -> str:
    """La commande `r <champion> <lane>` du Live Coach ; lève `Refusal` si elle serait invalide."""
    if lane not in scraping_config.LANES:
        raise Refusal(f"Rôle inconnu : {lane}")
    if not _CHAMPION.fullmatch(champion):
        raise Refusal("Champion inconnu")
    return f"r {champion} {lane}"
