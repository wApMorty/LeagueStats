"""Échanges de la draft : demander, accepter, refuser, annuler (SPEC-24 tâche 101).

Le front nomme un type d'échange, une action et la cellule de l'AUTRE joueur ; l'`id` de l'échange n'est
jamais donné par le front : il est lu dans la session au moment de l'appel (relevé du 2026-10-07 : chaque
entrée `{cellId, id, state}` désigne l'autre joueur, et les `id` sont renouvelés à chaque échange terminé).
Une action n'est permise que dans l'état qui lui correspond, sinon `Refusal` sans écriture.
"""

from typing import Any, Dict

from .draft_actions import SESSION, Refusal
from .lcu_proxy import LcuProxy

# type d'échange -> (clé de la session, segment du chemin LCU)
KINDS = {
    "pick_order": ("pickOrderSwaps", "pick-order-swaps"),
    "position": ("positionSwaps", "position-swaps"),
}
# action -> état que la session doit lister pour cette cellule
ACTIONS = {
    "request": "AVAILABLE",
    "accept": "RECEIVED",
    "decline": "RECEIVED",
    "cancel": "SENT",
}
_REFUSALS = {
    "AVAILABLE": "Cet échange ne peut pas être demandé maintenant",
    "RECEIVED": "Aucune demande reçue de ce joueur",
    "SENT": "Aucune demande envoyée à ce joueur",
}


def run(proxy: LcuProxy, kind: str, action: str, cell_id: int) -> Dict[str, Any]:
    """Écrit l'échange ; lève `Refusal` si la session ne le liste pas dans l'état attendu."""
    if kind not in KINDS or action not in ACTIONS:
        raise Refusal("Échange inconnu")
    session = proxy.get(SESSION)
    if not session:
        raise Refusal("Pas de champ select en cours")
    key, segment = KINDS[kind]
    expected = ACTIONS[action]
    entry = next(
        (
            e
            for e in session.get(key) or []
            if e.get("cellId") == cell_id and e.get("state") == expected
        ),
        None,
    )
    if entry is None or not isinstance(entry.get("id"), int):
        raise Refusal(_REFUSALS[expected])
    result = proxy.send("POST", f"/lol-champ-select/v1/session/{segment}/{entry['id']}/{action}")
    if result is None:
        raise Refusal("Le client LoL a refusé l'échange")
    return {"kind": kind, "action": action, "cell_id": cell_id}
