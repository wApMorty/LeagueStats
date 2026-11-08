"""SPEC-53 tâche 263 : conseil de place en draft (`src/draft/pick_advice.py`), module pur.

La fixture `session_swaps.json` est lue avec `DraftStateParser`, comme dans
`tests/test_draft_state_order_swaps.py`. Aucun client LoL, aucune base.
"""

import json
from pathlib import Path
from unittest.mock import Mock

from src.analysis.pick_order import Pick
from src.draft.pick_advice import PickAdvice, pick_advice, request_effect
from src.draft.state import Swap
from src.draft.state_parser import DraftStateParser

FIXTURES = Path(__file__).parent / "fixtures" / "lcu_forms"

# Ligne de référence (SPEC-51 §1.3, 1er nov.) : B jungle, R jungle, R mid, B mid, B bot, R bot,
# R support, B top, B support, R top.
LINE = [
    Pick(1, "blue", "jungle"),
    Pick(2, "red", "jungle"),
    Pick(3, "red", "middle"),
    Pick(4, "blue", "middle"),
    Pick(5, "blue", "bottom"),
    Pick(6, "red", "bottom"),
    Pick(7, "red", "support"),
    Pick(8, "blue", "top"),
    Pick(9, "blue", "support"),
    Pick(10, "red", "top"),
]


def parse(session):
    lcu = Mock()
    lcu.get_assigned_positions.return_value = {
        p["cellId"]: p["assignedPosition"] for p in session["myTeam"]
    }
    return DraftStateParser(lcu, str).parse(session, {}, {})[0]


def avail(cell_id, kind="pick_order"):
    return Swap(kind, 100 + cell_id, cell_id, "AVAILABLE")


def test_le_cote_bleu_est_celui_qui_a_le_rang_1():
    advice = pick_advice(LINE, "top", 4, {0: 1, 4: 9}, [])
    assert advice.side == "blue"
    advice = pick_advice(LINE, "top", 4, {0: 2, 4: 10}, [])
    assert advice.side == "red" and advice.target == 10


def test_blind_quand_mon_pick_precede_l_adverse_du_meme_poste():
    # Bleu top : slot 8, adverse rouge top : slot 10.
    advice = pick_advice(LINE, "top", 4, {0: 1, 4: 9}, [])
    assert advice.mode == "blind" and advice.target == 8


def test_counter_quand_mon_pick_suit_l_adverse_du_meme_poste():
    # Rouge bot : slot 6, adverse bleu bot : slot 5.
    advice = pick_advice(LINE, "bottom", 4, {0: 2, 4: 8}, [])
    assert advice.mode == "counter" and advice.side == "red" and advice.target == 6


def test_place_exacte_disponible_est_conseillee():
    ranks = {0: 1, 4: 9, 3: 8}
    advice = pick_advice(LINE, "top", 4, ranks, [avail(3)])
    assert advice == PickAdvice("top", "blue", "blind", 8, 9, 3, True)


def test_repli_sur_le_plus_proche_qui_rapproche():
    # Mon rang 10, visé 8 : le rang 9 rapproche, le 6 ne rapproche pas (même distance que 10 - 8 = 2).
    ranks = {0: 1, 4: 10, 1: 9, 2: 6}
    advice = pick_advice(LINE, "top", 4, ranks, [avail(2), avail(1)])
    assert advice.cell_id == 1 and advice.target_cell is False


def test_egalite_blind_prend_le_rang_le_plus_tot():
    # Visé 8, mon rang 10 : rangs 7 et 9 à égale distance d'1 ; blind prend 7 (pas la place 8).
    ranks = {0: 1, 4: 10, 1: 9, 2: 7}
    advice = pick_advice(LINE, "top", 4, ranks, [avail(1), avail(2)])
    assert advice.cell_id == 2 and advice.target_cell is False


def test_egalite_counter_prend_le_rang_le_plus_tard():
    # Rouge bot, visé 6, mon rang 10 : rangs 5 et 7 à égale distance d'1 ; counter prend 7 (pas 6).
    ranks = {0: 2, 4: 10, 1: 5, 2: 7}
    advice = pick_advice(LINE, "bottom", 4, ranks, [avail(1), avail(2)])
    assert advice.mode == "counter" and advice.cell_id == 2 and advice.target_cell is False


def test_echange_qui_eloigne_jamais_conseille():
    # Mon rang 9, visé 8 : le rang 4 éloigne.
    ranks = {0: 1, 4: 9, 1: 4}
    advice = pick_advice(LINE, "top", 4, ranks, [avail(1)])
    assert advice.cell_id is None and advice.target_cell is False


def test_deja_a_la_place_visee_rien_a_conseiller():
    ranks = {0: 1, 4: 8, 1: 9}
    advice = pick_advice(LINE, "top", 4, ranks, [avail(1)])
    assert advice.current == advice.target == 8
    assert advice.cell_id is None and advice.target_cell is False


def test_seuls_les_echanges_d_ordre_available_sont_demandables():
    ranks = {0: 1, 4: 10, 1: 8, 2: 9}
    swaps = [
        Swap("pick_order", 1, 1, "SENT"),
        Swap("pick_order", 2, 1, "RECEIVED"),
        Swap("pick_order", 3, 1, "INVALID"),
        Swap("position", 4, 1, "AVAILABLE"),
        avail(2),
    ]
    advice = pick_advice(LINE, "top", 4, ranks, swaps)
    assert advice.cell_id == 2 and advice.target_cell is False


def test_un_echange_avec_une_cellule_sans_rang_est_ignore():
    ranks = {0: 1, 4: 9}
    advice = pick_advice(LINE, "top", 4, ranks, [avail(3)])
    assert advice.cell_id is None


def test_none_sans_ligne_sans_poste_sans_rang_pour_moi_ou_sans_adverse():
    ranks = {0: 1, 4: 9}
    assert pick_advice([], "top", 4, ranks, []) is None
    assert pick_advice(LINE, None, 4, ranks, []) is None
    assert pick_advice(LINE, "top", 3, ranks, []) is None
    assert pick_advice(LINE, "top", None, ranks, []) is None
    assert pick_advice([p for p in LINE if p.lane != "top"], "top", 4, ranks, []) is None
    assert pick_advice([p for p in LINE if p.side == "blue"], "top", 4, ranks, []) is None


def test_request_effect_rapproche_eloigne_ou_ne_change_rien():
    advice = PickAdvice("top", "blue", "blind", 8, 10, None, False)
    ranks = {0: 1, 4: 10, 1: 9, 2: 4, 3: 8}
    assert request_effect(advice, ranks, 1) == "closer"
    assert request_effect(advice, ranks, 2) == "farther"
    assert request_effect(advice, ranks, 3) == "closer"
    # Rang égal à la distance de mon rang (10 - 8 = 2 : rang 6) : rien ne change.
    assert request_effect(advice, {0: 1, 4: 10, 1: 6}, 1) is None


def test_request_effect_cellule_de_rang_inconnu_est_none():
    advice = PickAdvice("top", "blue", "blind", 8, 9, None, False)
    assert request_effect(advice, {0: 1, 4: 9}, 3) is None


def test_fixture_session_swaps_donne_le_conseil_attendu():
    session = json.loads((FIXTURES / "session_swaps.json").read_text(encoding="utf-8"))
    state = parse(session)
    allies = {c.cell_id for c in state.ally_cells}
    ranks = {cell: rank for cell, rank in state.pick_order.items() if cell in allies}
    # Cellules alliées 0 à 4 : rangs 1, 4, 5, 8, 9 (moi : cellule 4, rang 9).
    assert ranks == {0: 1, 1: 4, 2: 5, 3: 8, 4: 9}

    advice = pick_advice(LINE, "top", state.local_player_cell_id, ranks, state.swaps)
    # Blind (8 < 10 du rouge top), vise 8, je suis à 9 ; cellule 3 INVALID : rien à demander.
    assert advice == PickAdvice("top", "blue", "blind", 8, 9, None, False)
    # Demande RECEIVED de la cellule 1 (rang 4) : elle m'éloigne de 8.
    assert request_effect(advice, ranks, 1) == "farther"
