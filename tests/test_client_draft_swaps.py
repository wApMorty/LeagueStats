"""SPEC-24 tâche 101 : actions d'échange (demander, accepter, refuser, annuler) sur les formes relevées.

Faux LCU et fixtures réelles anonymisées (`session_swaps` : demande d'ordre reçue de la cellule 1, rôles
demandables ; `session_swaps_sent` : demande d'ordre envoyée à la cellule 4). Aucun client LoL.
"""

import pytest

from src.client import draft_swaps
from src.client.draft_actions import Refusal
from src.client.lcu_proxy import WRITES, ForbiddenEndpoint, LcuProxy
from tests.test_client_draft_actions import FauxLCU, load, make_client, post

BASE = "/lol-champ-select/v1/session"


def lcu(name="session_swaps.json", refuses=False):
    return FauxLCU(load(name), refuses=refuses)


def test_accepter_une_demande_recue_ecrit_l_id_de_la_session():
    faux = lcu()
    result = draft_swaps.run(LcuProxy(faux), "pick_order", "accept", 1)
    assert faux.writes == [("POST", f"{BASE}/pick-order-swaps/26/accept", None)]
    assert result == {"kind": "pick_order", "action": "accept", "cell_id": 1}


def test_refuser_et_demander_un_echange_de_role():
    faux = lcu()
    draft_swaps.run(LcuProxy(faux), "pick_order", "decline", 1)
    draft_swaps.run(LcuProxy(faux), "position", "request", 2)
    assert [w[1] for w in faux.writes] == [
        f"{BASE}/pick-order-swaps/26/decline",
        f"{BASE}/position-swaps/8/request",
    ]


def test_annuler_une_demande_envoyee():
    faux = lcu("session_swaps_sent.json")
    draft_swaps.run(LcuProxy(faux), "pick_order", "cancel", 4)
    assert faux.writes == [("POST", f"{BASE}/pick-order-swaps/46/cancel", None)]


@pytest.mark.parametrize(
    "kind, action, cell",
    [
        ("pick_order", "request", 1),  # déjà reçue de ce joueur : on ne la redemande pas
        ("pick_order", "request", 2),  # INVALID : bloquée par la demande en cours
        ("pick_order", "accept", 2),  # rien reçu de la cellule 2
        ("pick_order", "cancel", 1),  # rien envoyé
        ("position", "accept", 2),  # AVAILABLE, pas RECEIVED
        ("position", "request", 4),  # la mienne : jamais listée
        ("position", "request", 99),
    ],
)
def test_etat_inattendu_refuse_sans_ecriture(kind, action, cell):
    faux = lcu()
    with pytest.raises(Refusal):
        draft_swaps.run(LcuProxy(faux), kind, action, cell)
    assert faux.writes == []


@pytest.mark.parametrize("kind, action", [("champion", "request"), ("position", "swap"), ("", "")])
def test_type_ou_action_inconnus(kind, action):
    faux = lcu()
    with pytest.raises(Refusal, match="inconnu"):
        draft_swaps.run(LcuProxy(faux), kind, action, 1)
    assert faux.calls == []


def test_hors_champ_select_et_liste_absente():
    with pytest.raises(Refusal, match="Pas de champ select"):
        draft_swaps.run(LcuProxy(FauxLCU(session=None)), "position", "request", 1)
    session = load("session_swaps.json")
    del session["positionSwaps"]
    faux = FauxLCU(session)
    with pytest.raises(Refusal):
        draft_swaps.run(LcuProxy(faux), "position", "request", 2)
    assert faux.writes == []


def test_refus_du_client_lisible():
    faux = lcu(refuses=True)
    with pytest.raises(Refusal, match="a refusé l'échange"):
        draft_swaps.run(LcuProxy(faux), "pick_order", "accept", 1)


# ---------- liste blanche ----------

EXPECTED_SWAP_PATTERN = (
    r"/lol-champ-select/v1/session/(pick-order-swaps|position-swaps)/\d+/"
    r"(request|accept|decline|cancel)"
)


def test_la_liste_blanche_ne_gagne_que_le_motif_des_huit_chemins():
    swaps = [p.pattern for m, p in WRITES if "swaps" in p.pattern]
    assert swaps == [EXPECTED_SWAP_PATTERN]
    assert len(WRITES) == 11  # les dix écritures d'avant SPEC-24, plus ce seul motif
    assert all(m == "POST" for m, p in WRITES if "swaps" in p.pattern)
    paths = [
        f"{BASE}/{segment}/{n}/{action}"
        for segment in ("pick-order-swaps", "position-swaps")
        for action in ("request", "accept", "decline", "cancel")
        for n in (7,)
    ]
    assert len(paths) == 8
    proxy = LcuProxy(FauxLCU(load("session_swaps.json")))
    for path in paths:
        proxy.send("POST", path)  # ne lève pas


@pytest.mark.parametrize(
    "method, endpoint",
    [
        ("POST", f"{BASE}/champion-swaps/7/request"),  # hors périmètre
        ("POST", f"{BASE}/pick-order-swaps/7/clear"),
        ("POST", f"{BASE}/pick-order-swaps/x/accept"),
        ("POST", f"{BASE}/pick-order-swaps/7/accept/extra"),
        ("POST", f"{BASE}/pick-order-swaps/7/../1/accept"),
        ("PUT", f"{BASE}/pick-order-swaps/7/accept"),
        ("DELETE", f"{BASE}/position-swaps/7/cancel"),
    ],
)
def test_aucun_autre_chemin_d_echange(method, endpoint):
    faux = lcu()
    with pytest.raises(ForbiddenEndpoint):
        LcuProxy(faux).send(method, endpoint)
    assert faux.calls == []


# ---------- route ----------


def test_route_ecrit_l_id_de_la_session_jamais_un_parametre_du_front(temp_db):
    faux = lcu()
    client = make_client(temp_db, faux)
    response = post(client, "/draft/swap/pick_order/accept", cell_id=1, id=999)
    assert response.status_code == 200 and response.json()["cell_id"] == 1
    assert faux.writes == [("POST", f"{BASE}/pick-order-swaps/26/accept", None)]


def test_route_sans_jeton_403_et_aucun_appel_lcu(temp_db):
    faux = lcu()
    response = post(
        make_client(temp_db, faux), "/draft/swap/position/request", token=False, cell_id=2
    )
    assert response.status_code == 403 and faux.calls == []


def test_route_409_sans_ecriture_quand_la_session_ne_liste_pas_l_echange(temp_db):
    faux = lcu()
    response = post(make_client(temp_db, faux), "/draft/swap/pick_order/request", cell_id=2)
    assert response.status_code == 409 and "demandé" in response.json()["detail"]
    assert faux.writes == []


def test_route_cell_id_invalide_422(temp_db):
    faux = lcu()
    assert (
        post(make_client(temp_db, faux), "/draft/swap/position/request", cell_id="x").status_code
        == 422
    )
    assert faux.calls == []
