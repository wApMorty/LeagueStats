"""SPEC-53 tâche 264 : la place de pick conseillée dans le snapshot de draft et la console.

Forme réelle relevée en draft classée (`tests/fixtures/lcu_forms/session_swaps.json`) : je suis la
cellule 4, top, côté bleu, n° 9 ; trois picks déjà verrouillés ; échange d'ordre reçu de la cellule 1.
"""

from src.analysis.pick_order import PICK_ORDER_META_KEY, Pick, to_meta
from tests.test_client_draft_actions import load
from tests.test_draft_snapshot import monitor  # noqa: F401  (fixture)
from tests.test_draft_state_order_swaps import parse, snapshot_of

# Séquence de SPEC-51 §1.3 (scrape du 1er nov.) : B top en 8, R top en 10.
LINE = to_meta(
    [
        Pick(slot, side, lane)
        for slot, (side, lane) in enumerate(
            [
                ("blue", "jungle"),
                ("red", "jungle"),
                ("red", "middle"),
                ("blue", "middle"),
                ("blue", "bottom"),
                ("red", "bottom"),
                ("red", "support"),
                ("blue", "top"),
                ("blue", "support"),
                ("red", "top"),
            ],
            start=1,
        )
    ]
)


def _with_line(monitor, value=LINE):  # noqa: F811
    monitor.assistant.db.get_meta.side_effect = lambda key: (
        value if key == PICK_ORDER_META_KEY else None
    )
    return monitor


def test_la_fixture_donne_le_conseil_et_l_effet_de_la_demande_recue(monitor):  # noqa: F811
    payload = snapshot_of(_with_line(monitor), parse(load("session_swaps.json")))

    assert payload["pick_advice"] == {
        "lane": "top",
        "side": "blue",
        "mode": "blind",
        "target": 8,
        "current": 9,
        "cell_id": None,  # la cellule 3 (n° 8) est INVALID : rien à demander
        "target_cell": False,
        "request_effects": {1: "farther"},  # la cellule 1 est n° 4 : plus loin du n° 8
    }


def test_plus_de_conseil_une_fois_mon_pick_verrouille(monitor):  # noqa: F811
    session = load("session_swaps.json")
    for action_set in session["actions"]:
        for action in action_set:
            if action.get("type") == "pick" and action.get("actorCellId") == 4:
                action["completed"] = True

    assert snapshot_of(_with_line(monitor), parse(session))["pick_advice"] is None


def test_plus_de_conseil_sans_echange_d_ordre_liste(monitor):  # noqa: F811
    session = load("session_swaps.json")
    session["pickOrderSwaps"] = []

    assert snapshot_of(_with_line(monitor), parse(session))["pick_advice"] is None


def test_sans_sequence_stockee_pas_de_conseil(monitor):  # noqa: F811
    payload = snapshot_of(_with_line(monitor, None), parse(load("session_swaps.json")))

    assert payload["pick_advice"] is None


def test_une_base_qui_leve_ne_coute_que_le_conseil(monitor):  # noqa: F811
    monitor.assistant.db.get_meta.side_effect = RuntimeError("base fermée")

    payload = snapshot_of(monitor, parse(load("session_swaps.json")))

    assert payload["pick_advice"] is None
    assert payload["swaps"] and payload["allies"]  # le reste du snapshot est publié


def test_la_console_ecrit_le_conseil_une_seule_fois(monitor, capsys):  # noqa: F811
    state = parse(load("session_swaps.json"))
    _with_line(monitor)

    snapshot_of(monitor, state)
    snapshot_of(monitor, state)

    lines = [l for l in capsys.readouterr().out.splitlines() if "Place conseillée" in l]
    assert lines == ["[INFO] Place conseillée : top côté bleu, blind, vise le n° 8 (tu es n° 9)"]
