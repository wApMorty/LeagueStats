"""Régression cartes de draft : la carte et la tuile du grimoire ne donnaient pas la même victoire.

Symptôme (@pj35, 2026-10-20) : en phase de picks, la carte d'Aatrox affichait 54,82 % (victoire de fin de
draft, recherche) alors que sa tuile du grimoire affichait 50,3 % (victoire immédiate, si je le prends
maintenant). Les deux écrans se contredisaient et l'écart de la carte n'avait pas de sens.

Cause racine : `recommendations` (draft_view.py) prenait `win_probability` de la recherche, qui projette la fin
de draft, pour la valeur de la carte et pour l'écart à la base. La tuile, elle, lit la victoire immédiate du Live
Coach. Les deux valeurs n'étaient jamais rapprochées.

Correctif : la carte affiche la victoire immédiate (`_immediate`) en gros chiffre, l'écart à la base sur cette
valeur, et la fin de draft attendue en sous-ligne. Sans victoire immédiate pour le champion, les trois valeurs
d'avant restent.

Prévention : ce test pose la même table pour la carte et la tuile et exige que le pourcentage du gros chiffre
égale celui de la tuile à l'arrondi près, et que l'écart soit calculé sur la même valeur.
"""

from dataclasses import asdict

from src.draft.snapshot import SnapshotChampion
from tests.test_client_draft import (  # noqa: F401  (fixtures `client`, `bus`, `assets`)
    assets,
    bus,
    client,
    pick_snapshot,
)


def immediate_table():
    """Victoire immédiate : Aatrox et Darius sont sur les cartes, Ahri seulement au grimoire."""
    return [
        asdict(SnapshotChampion(266, "Aatrox", ["top"], 0.5027, None)),
        asdict(SnapshotChampion(122, "Darius", ["top"], 0.5390, None)),
        asdict(SnapshotChampion(103, "Ahri", ["middle"], 0.4950, None)),
    ]


def card(html, champ):
    """Le bloc HTML d'une carte de pick, repérée par son `data-champ`."""
    chunks = html.split('class="d-card"')[1:]
    return next(chunk for chunk in chunks if f'data-champ="{champ}"' in chunk)


def tile(html, champ):
    """Le bloc HTML d'une tuile du grimoire, repérée par son `data-id`."""
    chunks = html.split('class="g-tile')[1:]
    return next(chunk for chunk in chunks if f'data-id="{champ}"' in chunk)


def test_carte_et_tuile_donnent_la_meme_victoire_immediate(client, bus):
    bus.publish("draft", pick_snapshot(champions=immediate_table()))

    stage = client.get("/draft/stage").text
    aatrox = card(stage, 266)
    assert '<div class="d-card-big">50,27 %</div>' in aatrox
    assert '<div class="d-card-delta">−1,4 pts</div>' in aatrox
    assert "Fin de draft attendue 54,82 % · suite : Alistar (Support)" in aatrox

    darius = card(stage, 122)
    assert '<div class="d-card-big">53,90 %</div>' in darius
    assert '<div class="d-card-delta up">+2,2 pts</div>' in darius
    assert "Fin de draft attendue 53,07 % · suite : —" in darius

    assert stage.index('data-champ="266"') < stage.index('data-champ="122"')

    # La tuile du grimoire affiche la même victoire, à l'arrondi du dixième près.
    assert "50,3 %" in tile(client.get("/draft/champions").text, 266)
