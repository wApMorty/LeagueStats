"""SPEC-24 tâche 102 : conseil d'échange de rôle, gain mesuré par l'évaluateur du Live Coach.

Évaluateur factice (victoire fixée par composition), aucun accès à data/db.db ni au client LoL.
"""

from unittest.mock import Mock, patch

import pytest

from src.client.bus import EventBus
from src.config_constants import draft_config
from src.draft.search import SearchResult
from src.draft.snapshot import TOPIC
from src.draft.state import Cell, DraftState, Swap
from src.draft.swap_advice import has_open_swap, role_swaps
from tests.test_draft_snapshot import monitor  # noqa: F401  (fixture)


class FakeEvaluator:
    """Victoire = 50 % + bonus par (champion, lane) ; Garen est meilleur en jungle que Vi en top."""

    BONUS = {
        ("Garen", "top"): 0.0,
        ("Garen", "jungle"): 0.03,
        ("Vi", "jungle"): 0.0,
        ("Vi", "top"): -0.02,
    }

    def __init__(self):
        self.calls = 0

    def win_probability(self, allies, enemies):
        self.calls += 1
        return 0.5 + sum(self.BONUS.get(placed, 0.0) for placed in allies)


ALLIES = {0: ("Garen", "top"), 1: ("Vi", "jungle")}
ENEMIES = [("Darius", "top")]
OPEN = [Swap("position", 8, 1, "AVAILABLE")]


def test_le_gain_vaut_la_victoire_apres_moins_avant_en_points():
    (advice,) = role_swaps(FakeEvaluator(), ALLIES, ENEMIES, 0, OPEN)
    assert advice.gain_pts == pytest.approx((0.5 + 0.03 - 0.02 - 0.5) * 100 - 0.0)  # +1,0 pt
    assert (advice.kind, advice.cell_id, advice.champion) == ("position", 1, "Vi")
    assert advice.reason == "Garen en jungle, Vi en top"


def test_aucun_conseil_sous_le_seuil(monkeypatch):
    monkeypatch.setattr(draft_config, "SWAP_MIN_GAIN_PTS", 1.5)
    assert role_swaps(FakeEvaluator(), ALLIES, ENEMIES, 0, OPEN) == []


def test_aucun_conseil_sans_champion_des_deux_cotes():
    assert (
        role_swaps(FakeEvaluator(), {0: ("Garen", "top")}, ENEMIES, 0, OPEN) == []
    )  # l'autre n'a pas pické
    assert (
        role_swaps(FakeEvaluator(), {1: ("Vi", "jungle")}, ENEMIES, 0, OPEN) == []
    )  # moi sans champion
    assert (
        role_swaps(FakeEvaluator(), {0: ("Garen", None), 1: ("Vi", "jungle")}, ENEMIES, 0, OPEN)
        == []
    )


@pytest.mark.parametrize(
    "swap",
    [
        Swap("pick_order", 8, 1, "AVAILABLE"),
        Swap("position", 8, 1, "SENT"),
        Swap("position", 8, 1, "INVALID"),
    ],
)
def test_seuls_les_echanges_de_role_ouverts_sont_conseilles(swap):
    assert role_swaps(FakeEvaluator(), ALLIES, ENEMIES, 0, [swap]) == []


def test_un_echange_recu_est_conseille_aussi():
    received = [Swap("position", 8, 1, "RECEIVED")]
    assert len(role_swaps(FakeEvaluator(), ALLIES, ENEMIES, 0, received)) == 1
    assert has_open_swap(received, "position") and not has_open_swap(received, "pick_order")


# ---------- dans DraftRecommender.provide ----------


def state_with_swap(swaps=None):
    return DraftState(
        phase="BAN_PICK",
        ally_picks=[1],
        enemy_picks=[2],
        local_player_cell_id=0,
        current_actor=0,
        ally_positions={0: "top", 1: "jungle"},
        inferred_roles={1: "jungle", 2: "top"},
        ally_cells=[Cell(0, hover_id=3, position="top"), Cell(1, champion_id=1, position="jungle")],
        enemy_cells=[Cell(5, champion_id=2)],
        swaps=OPEN if swaps is None else swaps,
    )


def publish(monitor, state):
    bus = EventBus()
    monitor.bus = bus
    monitor.champion_id_to_name = {1: "Vi", 2: "Darius", 3: "Garen"}
    monitor.evaluator = FakeEvaluator()
    with bus.subscribe([TOPIC]) as subscription:
        with patch.object(
            monitor.search, "rank", return_value=[SearchResult("A", "top", 0.5, [], 1)]
        ):
            monitor._provide_recommendations(state)
        return subscription.get(1)[1]


def test_le_snapshot_porte_le_conseil(monitor):
    payload = publish(monitor, state_with_swap())
    assert [a["champion"] for a in payload["swap_advice"]] == ["Vi"]
    assert payload["swap_advice"][0]["gain_pts"] > draft_config.SWAP_MIN_GAIN_PTS - 1e-9


def test_pas_de_calcul_sans_echange_ouvert(monitor):
    payload = publish(monitor, state_with_swap(swaps=[]))
    assert payload["swap_advice"] == []


def test_une_panne_du_conseil_n_interrompt_pas_provide(monitor, capsys):
    bus = EventBus()
    monitor.bus = bus
    monitor.champion_id_to_name = {1: "Vi", 2: "Darius", 3: "Garen"}
    monitor.evaluator = Mock(win_probability=Mock(side_effect=RuntimeError("évaluateur cassé")))
    with bus.subscribe([TOPIC]) as subscription:
        with patch.object(monitor.search, "rank", return_value=[]):
            monitor._provide_recommendations(state_with_swap())  # ne lève pas
        event = subscription.get(1)
    assert event is not None
    assert event[1]["swap_advice"] == []
