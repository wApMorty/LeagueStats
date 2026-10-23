"""Régression : l'écran de draft gardait la page générale après l'import affiné au duel.

Symptôme : au lock-in, le Live Coach écrit la page générale ; quand l'adversaire de lane apparaît, il
réécrit dans le client LoL la page et les sorts du duel, mais la colonne loadout montre toujours la
page générale.

Cause racine : l'état synchronisé avec le front ne portait que `loadout: bool`. `runes.js` ne
rechargeait la page qu'au passage de faux à vrai : une réécriture (ou un adversaire, un poste
nouveau) laissait le booléen à vrai et rien ne se rechargeait.

Correctif : `state.loadout` est une empreinte de la page écrite, de l'adversaire et du poste ;
`runes.js` recharge la page dès qu'elle change (sauf page modifiée à la main).

Prévention : ce test exige que l'empreinte change quand la page écrite change pour le même champion.
"""

from src.client import draft_view
from tests.test_client_draft import assets, pick_snapshot  # noqa: F401 - fixture

GENERAL = {"champion_id": 266, "perks": [8010, 9111, 9104, 8299, 8226, 8210], "spells": [4, 12]}
DUEL = {"champion_id": 266, "perks": [8010, 9111, 9105, 8299, 8226, 8210], "spells": [4, 14]}


def _key(assets, **overrides):  # noqa: F811
    return draft_view.stage_view(pick_snapshot(**overrides), assets)["state"]["loadout"]


def test_la_reecriture_de_la_page_au_duel_change_l_empreinte(assets):  # noqa: F811
    assert _key(assets, loadout=GENERAL) != _key(assets, loadout=DUEL)


def test_l_adversaire_qui_apparait_change_l_empreinte(assets):  # noqa: F811
    assert _key(assets, versus=None) != _key(assets, versus="Tryndamere")
