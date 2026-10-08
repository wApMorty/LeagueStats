"""Regression test — l'overlay « Partie trouvée » se refermait puis se rouvrait en entier après « Accepter ».

1. Symptôme (2026-10-08) : après le clic sur « Accepter », l'animation de la partie trouvée repartait de zéro
   en boucle (boutons « Accepter » et « Refuser » de retour, 90 runes, pilier, explosion rejoués) jusqu'à
   l'arrivée du champ select.
2. Cause racine : `acceptedSequence` fermait l'overlay 1,2 s après l'acceptation, alors que, tant que les
   autres joueurs n'ont pas tous accepté, la phase reste `ReadyCheck` et le ready-check `InProgress`. `apply`
   voyait alors « partie trouvée » sans overlay et rappelait `show` ; la boucle durait jusqu'à `ChampSelect`.
3. Correctif : l'overlay accepté est tenu (`held`) tant que la phase est `ReadyCheck`, puis entre en draft à
   `ChampSelect` ; il ne dépend plus du détail du ready-check après l'acceptation (SPEC-26).
4. Prévention : le vrai `found.js` tourne sous `node` (`tests/support_found_js.py`) contre la suite d'états
   « sans réponse, clic, Accepted x 4, ChampSelect » ; un seul overlay, une seule séquence, jamais de boutons.
"""

from tests.support_found_js import run_found, served


def test_apres_accepter_un_seul_overlay_sans_boutons_jusqu_a_la_draft():
    result = run_found(
        [
            served("ReadyCheck", "None"),
            {"click": "accept"},
            {"advance": 2000},
            *[
                step
                for _ in range(4)
                for step in (served("ReadyCheck", "Accepted"), {"advance": 2000})
            ],
            served("ChampSelect"),
            {"advance": 5000},
        ]
    )
    assert result["created"] == 1  # jamais rouvert
    assert result["seals"] == 1  # une seule séquence d'acceptation
    for snap in result["snaps"][1:-2]:  # du clic à la dernière réponse `Accepted`
        assert snap["overlays"] == 1 and snap["buttons_hidden"] is True
    assert result["ajax"] == ["GET /draft"] and result["pushed"] == [
        "/draft"
    ]  # une seule navigation
    assert result["snaps"][-1]["overlays"] == 0  # retiré après l'effondrement
