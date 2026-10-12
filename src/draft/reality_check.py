"""Comparaison des postes prédits et des postes réels en partie (SPEC-27 §4.3, tâche 124).

Fonctions pures : relevé `allPlayers` (voir `client/ingame.py:roster_of`) et
dictionnaire championId -> nom d'affichage de la draft -> comparaison. Aucune
base, aucun LCU, aucun bus.

Une vérification absente vaut mieux qu'une fausse : un champion dont le nom
n'est pas retrouvé de façon univoque, ou dont l'équipe n'a pas ses cinq postes
valides et distincts, n'entre dans aucun résultat.
"""

import re
from typing import Any, Dict, List

from ..coaching.metrics import EOG_POSITIONS


def _key(name: str) -> str:
    """Clé de comparaison d'un nom : minuscules, sans caractère non alphanumérique."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def resolve_champions(
    roster: List[Dict[str, Any]], names: Dict[int, str]
) -> Dict[int, Dict[str, Any]]:
    """championId -> entrée du relevé, pour les seuls noms retrouvés de façon univoque.

    `names` : championId -> nom d'affichage de la draft. La clé est essayée d'abord sur
    `raw` (Wukong / MonkeyKing), puis sur `champion` (Nunu & Willump / Nunu). Zéro ou
    plusieurs entrées : le champion est absent, jamais deviné.
    """
    resolved: Dict[int, Dict[str, Any]] = {}
    for champion_id, name in names.items():
        wanted = _key(name)
        if not wanted:
            continue
        matches = [entry for entry in roster if _key(entry.get("raw") or "") == wanted]
        if not matches:
            matches = [entry for entry in roster if _key(entry.get("champion") or "") == wanted]
        if len(matches) == 1:
            resolved[champion_id] = matches[0]
    return resolved


def real_lanes(resolved: Dict[int, Dict[str, Any]]) -> Dict[int, str]:
    """championId -> lane réelle, pour les seules équipes dont les cinq postes sont valides.

    Une équipe n'est retenue que si elle a cinq champions résolus, tous avec un poste de
    `EOG_POSITIONS`, et cinq postes distincts. Sinon aucun de ses champions n'apparaît.
    """
    by_team: Dict[str, List[tuple]] = {}
    for champion_id, entry in resolved.items():
        by_team.setdefault(entry.get("team") or "", []).append(
            (champion_id, entry.get("position") or "")
        )

    lanes: Dict[int, str] = {}
    for members in by_team.values():
        positions = [position for _, position in members]
        if (
            len(members) != 5
            or any(p not in EOG_POSITIONS for p in positions)
            or len(set(positions)) != 5
        ):
            continue
        for champion_id, position in members:
            lanes[champion_id] = EOG_POSITIONS[position]
    return lanes


def compare(predicted: Dict[int, str], real: Dict[int, str]) -> Dict[str, Any]:
    """Confronte les lanes prédites aux lanes réelles.

    Retourne `{"checked": n, "mismatches": [{"champion_id", "predicted", "real"}],
    "unverified": [champion_id, ...]}`. `checked` compte les ids présents des deux côtés ;
    `unverified` liste les ids prédits absents de `real` ; un id de `real` absent de
    `predicted` est ignoré.
    """
    checked = 0
    mismatches: List[Dict[str, Any]] = []
    unverified: List[int] = []
    for champion_id, lane in predicted.items():
        if champion_id not in real:
            unverified.append(champion_id)
            continue
        checked += 1
        if real[champion_id] != lane:
            mismatches.append(
                {"champion_id": champion_id, "predicted": lane, "real": real[champion_id]}
            )
    return {"checked": checked, "mismatches": mismatches, "unverified": unverified}
