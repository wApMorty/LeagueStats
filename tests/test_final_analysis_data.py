"""SPEC-24 tâche 106 : l'analyse de fin de draft devient une donnée, publiée sur le bus.

Hermétique : évaluateur factice de ``test_final_analysis_face_off``, pages OneTricks enregistrées
de ``test_loadout_import``, aucun accès à data/db.db ni au vrai client.
"""

import contextlib
import io
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.client.bus import EventBus
from src.draft.final_analysis import (
    TOPIC,
    FinalDraftAnalyzer,
    build_final_analysis,
    evaluation_of,
)
from src.draft.lifecycle import MonitorLifecycle
from src.draft.state import DraftState
from tests import test_final_analysis_face_off as fo
from tests import test_loadout_import as li
from tests.test_loadout_import import enabled, http, importer, lcu  # noqa: F401  (fixtures)

GOLDEN = Path(__file__).parent / "fixtures" / "final_analysis_console.txt"


def console(probability, lanes=fo.LANES_BY_ID, thin=()):
    monitor = fo.make_monitor(thin=thin)
    monitor.evaluator.win_probability = lambda allies, enemies: probability
    buffer = io.StringIO()
    with (
        patch("src.draft.final_analysis.clear_console"),
        patch("src.draft.final_analysis.draft_reminder", return_value=["[INFO] axe test"]),
        contextlib.redirect_stdout(buffer),
    ):
        FinalDraftAnalyzer(monitor).analyze(fo.ALLY_IDS, fo.ENEMY_IDS, ally_lanes=lanes)
    return f"##### prob={probability} thin={thin}\n" + buffer.getvalue()


def test_la_sortie_console_est_identique_a_celle_d_avant_la_refonte():
    """Le fichier a été relevé sur le code d'avant la tâche 106 (5 jeux : toutes les évaluations)."""
    played = "".join(
        [
            console(0.55),
            console(0.53, thin=("Garen",)),
            console(0.50, lanes={}),
            console(0.46),
            console(0.40, lanes={**fo.LANES_BY_ID, 2: "middle"}),
        ]
    )
    assert played == GOLDEN.read_text(encoding="utf-8")


def test_une_ligne_par_lane_dans_l_ordre_du_face_a_face():
    analysis = build_final_analysis(fo.make_monitor(), fo.ALLY_IDS, fo.ENEMY_IDS, fo.LANES_BY_ID)
    pairs = [(line.ally.name, line.enemy.name) for line in analysis.lines]
    assert pairs == [
        ("Garen", "Darius"),
        ("Vi", "Lee Sin"),
        ("Ahri", "Syndra"),
        ("Jinx", "Draven"),
        ("Rell", "Nautilus"),
    ]
    assert [line.duel for line in analysis.lines][:2] == pytest.approx([3.4, -1.3])
    assert analysis.lines[4].duel is None  # Rell / Nautilus : aucune donnée


def test_probabilite_ecart_et_evaluation():
    analysis = build_final_analysis(fo.make_monitor(), fo.ALLY_IDS, fo.ENEMY_IDS, fo.LANES_BY_ID)
    assert analysis.win_probability == 0.55
    assert analysis.draft_diff == pytest.approx(10.0)
    assert analysis.evaluation == "Avantage de draft majeur"


@pytest.mark.parametrize(
    "diff, label",
    [
        (5.0, "Avantage de draft majeur"),
        (2.5, "Bon avantage de draft"),
        (0.0, "Draft équilibré"),
        (-2.5, "Draft équilibré"),
        (-2.51, "Désavantage de draft"),
        (-5.0, "Désavantage de draft"),
        (-5.01, "Désavantage de draft majeur"),
    ],
)
def test_paliers_d_evaluation(diff, label):
    assert evaluation_of(diff)[0] == label


def test_analyze_publie_sur_le_sujet_game_et_la_charge_utile_est_du_json():
    bus = EventBus()
    monitor = fo.make_monitor()
    monitor.bus = bus
    with patch("src.draft.final_analysis.clear_console"):
        FinalDraftAnalyzer(monitor).analyze(fo.ALLY_IDS, fo.ENEMY_IDS, ally_lanes=fo.LANES_BY_ID)
    payload = bus.latest(TOPIC)
    assert TOPIC == "game"
    assert payload["lines"][0]["ally"]["name"] == "Garen"
    assert payload["evaluation"] == "Avantage de draft majeur"
    json.dumps(payload)


def test_un_bus_en_panne_n_interrompt_pas_l_analyse(capsys):
    monitor = fo.make_monitor()
    monitor.bus.publish.side_effect = RuntimeError("bus cassé")
    with patch("src.draft.final_analysis.clear_console"):
        FinalDraftAnalyzer(monitor).analyze(fo.ALLY_IDS, fo.ENEMY_IDS, ally_lanes=fo.LANES_BY_ID)
    assert "COMPARAISON DU DRAFT" in capsys.readouterr().out


def test_le_reset_vide_le_sujet_game():
    bus = EventBus()
    bus.publish(TOPIC, {"lines": []})
    monitor = Mock()
    monitor.bus = bus
    MonitorLifecycle(monitor).reset_for_next_game()
    assert bus.latest(TOPIC) is None
    assert isinstance(monitor.last_draft_state, DraftState)


class TestLoadoutAvecSubstitutions:
    def test_le_duel_ajoute_les_substitutions_et_les_noms_d_objets(self, importer, http):
        importer.on_tick(li.session(), li.state([li.DRAVEN], {li.DRAVEN: "bottom"}))
        detail = importer.state(with_duel=True)
        assert {sub["category"] for sub in detail["substitutions"]} == {"Sorts", "Rune 3"}
        sorts = next(sub for sub in detail["substitutions"] if sub["category"] == "Sorts")
        assert (sorts["old"], sorts["new"]) == ("Barrier+Flash", "Exhaust+Flash")
        assert "parties" in sorts["reason"] and "%" in sorts["reason"]
        blocks = {item for block in detail["item_blocks"] for item in block["items"]}
        assert all(str(item) in detail["item_names"] for item in blocks)

    def test_la_charge_utile_du_bus_embarque_les_substitutions(self, importer, http):
        li_state = li.state([li.DRAVEN], {li.DRAVEN: "bottom"})
        importer.on_tick(li.session(), li_state)
        monitor = fo.make_monitor()
        monitor.loadout = importer
        bus = EventBus()
        monitor.bus = bus
        with patch("src.draft.final_analysis.clear_console"):
            FinalDraftAnalyzer(monitor).analyze(
                fo.ALLY_IDS, fo.ENEMY_IDS, ally_lanes=fo.LANES_BY_ID
            )
        loadout = bus.latest(TOPIC)["loadout"]
        assert {s["category"] for s in loadout["substitutions"]} == {"Sorts", "Rune 3"}
        assert loadout["item_names"]

    def test_state_sans_with_duel_reste_celui_de_la_draft(self, importer, http):
        importer.on_tick(li.session(), li.state([li.DRAVEN], {li.DRAVEN: "bottom"}))
        assert "substitutions" not in importer.state()

    def test_build_generale_seule_sans_substitution(self, importer, http):
        importer.on_tick(li.session(), li.state())
        assert importer.state(with_duel=True)["substitutions"] == []

    def test_reset_efface_les_substitutions(self, importer, http):
        importer.on_tick(li.session(), li.state([li.DRAVEN], {li.DRAVEN: "bottom"}))
        importer.reset()
        assert importer.state(with_duel=True) is None


importer = li.importer
li_http = li.http
