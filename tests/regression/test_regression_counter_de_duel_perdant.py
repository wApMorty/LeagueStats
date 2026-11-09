"""Régression carte de draft : « Counter de Yone » sur un champion qui perd la lane.

Symptôme (@pj35, 2026-11-09, partie 8041130893) : en counterpick sous l'Arbre, la carte n° 1 proposait
Ornn avec « Counter de Yone », alors qu'Ornn est le pire duel de la pool contre Yone (delta2 −1,97,
duel −1,86 pt).

Cause racine : le libellé ajouté en 4b405c6 était posé sur la carte n° 1 dès qu'un vis-à-vis existait.
Or la règle D classe sur toute la draft (force, duels, synergies) : Ornn passait n° 1 par sa force
(+1,22) et sa synergie avec Rengar (+0,75), malgré le duel. Le libellé affirmait un counter jamais mesuré.

Correctif : la carte dit le duel réellement compté, « Duel vs Yone −1,86 », lu dans `parts["duel"]`.

Prévention : une carte n° 1 au duel négatif ne dit jamais « Counter de » et montre la valeur du duel.
"""

from src.client import draft_view
from tests.test_client_draft import assets, exposure_snapshot  # noqa: F401  (fixture `assets`)


def test_la_carte_1_dit_le_duel_et_non_un_counter(assets):
    snapshot = exposure_snapshot(versus="Yone")
    snapshot["recommendations"][0]["parts"] = {"force": 1.22, "duel": -1.86}
    line = draft_view.recommendations(snapshot, draft_view.Champions(assets))[0]["line"]
    assert "Counter de" not in line
    assert line.startswith("Duel vs Yone −1,86 · Connu +1,20 · Exposition −0,85 · ")
