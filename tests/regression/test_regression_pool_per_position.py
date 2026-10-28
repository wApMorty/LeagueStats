"""Régression : le pool du Live Coach ignorait le poste assigné (SPEC-44).

Symptôme (@pj35, 2026-10-28) : un seul pool par session, et son rôle passait avant le poste assigné.
Avec « Top playable » actif et un poste mid, le blind pick du hover initial et les bans étaient
calculés pour le top.

Cause racine : `HoverAutomation._resolve_player_lane` et `BanAdvisor._ban_lane` prennent `pool_lane`
d'abord, et `pool_lane` venait du rôle du pool choisi au lancement, jamais du poste de la draft.

Correctif : au premier tick de chaque draft, `PoolSelector.select_for_position` charge le pool désigné
pour le poste (ou le pool par défaut, ou le pool système du rôle) et pose `pool_lane` sur le poste.
Une commande `pool` au fil de la draft l'emporte sans quitter le poste.

Prévention : ce test suit la chaîne réelle du tick (`_handle_champ_select`) jusqu'au moment où le hover
initial lit la lane.
"""

import json
from unittest.mock import Mock, patch

import pytest

from src.draft.state import DraftState
from src.draft_monitor import DraftMonitor
from src.pool_manager import PoolManager
from src.ui import draft_coach_ui
from src.user_prefs import load_user_prefs

TOP = ["Garen", "Darius"]
MID = ["Ahri", "Zed"]


@pytest.fixture
def prefs(tmp_path):
    """Pool par défaut « Top Main » (top), « Mid Main » désigné pour le poste mid."""
    manager = PoolManager()
    manager.create_pool("Top Main", TOP, role="top")
    manager.create_pool("Mid Main", MID, role="custom")
    manager.save_custom_pools(recalculate_bans=False)
    (tmp_path / "user_prefs.json").write_text(
        json.dumps(
            {
                "auto_hover": True,
                "auto_accept_queue": False,
                "auto_ban_hover": False,
                "pool_name": "Top Main",
                "pools_by_role": {"middle": "Mid Main"},
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def monitor(prefs):
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            monitor = DraftMonitor(
                verbose=False,
                auto_select_pool=False,
                preselected_pool_name="Top Main",
                console_input=False,
            )
    monitor.pool_selector.select_at_launch()  # ce que fait start_monitoring
    monitor.seen = []
    monitor._handle_draft_change = Mock(
        side_effect=lambda _s: monitor.seen.append((monitor.pool_name, monitor.pool_lane))
    )
    monitor._has_draft_changed = Mock(return_value=True)
    monitor._is_draft_complete = Mock(return_value=False)
    monitor.loadout = Mock()
    return monitor


def tick(monitor, position):
    state = DraftState(phase="BAN_PICK", local_player_cell_id=2)
    if position:
        state.ally_positions = {2: position}
    monitor._parse_draft_state = Mock(return_value=state)
    monitor.lifecycle._handle_champ_select({})


def test_le_premier_tick_charge_le_pool_du_poste_avant_le_hover(monitor):
    assert (monitor.pool_name, monitor.pool_lane) == ("Top Main", "top")
    tick(monitor, "middle")
    assert monitor.seen == [("Mid Main", "middle")]
    assert monitor.current_pool == MID


def test_une_commande_pool_deposee_avant_la_draft_est_ecrasee(monitor):
    monitor._command_queue.put("pool Top Main")
    tick(monitor, "middle")
    assert (monitor.pool_name, monitor.pool_lane) == ("Mid Main", "middle")


def test_une_commande_pool_en_draft_l_emporte_et_garde_le_poste(monitor):
    tick(monitor, "middle")
    monitor._command_queue.put("pool Top Main")
    tick(monitor, "middle")
    assert (monitor.pool_name, monitor.pool_lane) == ("Top Main", "middle")
    assert monitor.current_pool == TOP


def test_apres_la_partie_une_draft_sans_poste_reprend_le_pool_par_defaut(monitor):
    tick(monitor, "middle")
    monitor._reset_for_next_game()
    tick(monitor, None)
    assert (monitor.pool_name, monitor.pool_lane) == ("Top Main", "top")
    assert monitor.current_pool == TOP


def test_le_coach_console_garde_les_pools_par_poste_et_le_pool_de_lancement(monitor):
    tick(monitor, "middle")
    with patch.object(draft_coach_ui, "DraftMonitor", return_value=monitor):
        monitor.start_monitoring = Mock()
        draft_coach_ui.run_draft_coach(pool_name="Top Main")
    saved = load_user_prefs()
    assert saved.pool_name == "Top Main"
    assert saved.pools_by_role == {"middle": "Mid Main"}
