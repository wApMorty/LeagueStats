"""Le seul chemin du client vers le LCU : une liste blanche d'endpoints (SPEC-21 §4.2, §4.7).

Le front ne passe jamais un chemin : il nomme une action, et le serveur la traduit. Ce module est le
second verrou : même un appel interne ne sort que vers un endpoint listé ici, en lecture comme en
écriture. Les écritures sont celles de la draft, du lobby et de la file ; le social et tout le reste
sont en lecture seule (critères 5 et 6). Chaque tâche d'écran ajoute ses endpoints à ces tables.
"""

import re
from typing import Any, Dict, Optional, Pattern, Tuple

# Lectures : chemins exacts ou motifs complets (jamais un préfixe).
READS: Tuple[Pattern[str], ...] = tuple(
    re.compile(pattern)
    for pattern in (
        r"/lol-gameflow/v1/(gameflow-phase|session)",
        r"/lol-champ-select/v1/(session|pickable-champion-ids|bannable-champion-ids)",
        r"/lol-summoner/v1/current-summoner",
        r"/lol-champions/v1/inventories/\d+/champions/\d+/skins",
        r"/lol-perks/v1/(pages|inventory|styles|currentpage)",
        r"/lol-matchmaking/v1/ready-check",
    )
)

# Écritures : (méthode, motif complet). Draft seulement pour l'instant ; lobby et file à leurs tâches.
WRITES: Tuple[Tuple[str, Pattern[str]], ...] = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        ("PATCH", r"/lol-champ-select/v1/session/actions/\d+"),  # survoler, verrouiller, bannir
        ("PATCH", r"/lol-champ-select/v1/session/my-selection"),  # skin, sorts
        ("POST", r"/lol-matchmaking/v1/ready-check/(accept|decline)"),  # partie trouvée
        ("POST", r"/lol-perks/v1/pages"),  # page de runes du loadout
        ("DELETE", r"/lol-perks/v1/pages/\d+"),  # la page « LS » précédente seulement
    )
)


class ForbiddenEndpoint(Exception):
    """Endpoint ou méthode hors liste blanche : aucun appel n'a eu lieu."""


class LcuProxy:
    """Enveloppe d'un `LCUClient` qui n'émet que des appels de la liste blanche."""

    def __init__(self, lcu: Any) -> None:
        self._lcu = lcu

    def _ready(self) -> bool:
        lcu = self._lcu
        if lcu is None:
            return False
        if lcu.credentials is None:
            lcu.credentials = lcu.find_lcu_credentials()
        return lcu.credentials is not None

    def get(self, endpoint: str) -> Optional[Any]:
        """Lecture d'un endpoint listé ; None si le client est fermé ou ne répond pas."""
        if not any(pattern.fullmatch(endpoint) for pattern in READS):
            raise ForbiddenEndpoint(f"lecture non autorisée : {endpoint}")
        return self._lcu._make_request(endpoint) if self._ready() else None

    def send(
        self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """Écriture sur un endpoint listé ; None si le client la refuse ou est fermé."""
        method = method.upper()
        if not any(m == method and p.fullmatch(endpoint) for m, p in WRITES):
            raise ForbiddenEndpoint(f"écriture non autorisée : {method} {endpoint}")
        return self._lcu._make_request(endpoint, method, data) if self._ready() else None
