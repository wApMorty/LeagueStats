"""Regression test — the initial blind-pick hover ignored the known lane and
scored candidates on their all-lanes aggregate instead.

Bug report (SPEC-09 E3, 2026-09-05): the 5th residual of the lane-filter bug
family fixed across the Live Coach in September 2026 (Live Coach recommend-
ations, end-of-draft screen, bans, Team Builder, Tournament Coach — see
CHANGELOG.md [Unreleased]), not caught by the 2026-09-04 audit because it
lives on a rarely-exercised code path: the "Meilleur blind pick" announced
and auto-hovered at the very start of champion select.

Root cause: ``HoverAutomation.get_best_champion_from_pool()``
(``src/draft/automation.py``) called
``self.m.assistant.get_matchups_for_draft(champion_name)`` with no ``lane=``,
even though the lane is already known at that point via either
``self.m.pool_lane`` (mono-role pool, set by ``PoolSelector``) or
``self.m.last_draft_state.ally_positions`` (LCU-assigned position). A
multi-lane champion in the pool (e.g. Yasuo top/mid/bottom) therefore had its
blind-pick score computed from every lane combined, diluting or inflating the
number behind "votre choix le plus sûr".

Fix: resolve the lane via ``HoverAutomation._resolve_player_lane()`` (pool_lane
first, then the LCU position, else None — never a silent fallback to the
all-lanes aggregate, per SPEC-09 "Hors périmètre") and thread it into
``get_matchups_for_draft``.

Prevention: this test locks the call to always carry the resolved lane, for
both sources, so a future edit that drops the ``lane=`` kwarg again fails
immediately instead of silently reintroducing the aggregate-scoring bug.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor, DraftState
from src.models import Matchup

POOL = ["Yasuo"]
CHAMPION_IDS = {777: "Yasuo", 64: "LeeSin"}


@pytest.fixture
def monitor():
    assistant = Mock()
    assistant.db = Mock()
    assistant.get_matchups_for_draft.return_value = [
        Matchup(
            enemy_name="LeeSin",
            winrate=52.0,
            delta1=100.0,
            delta2=150.0,
            pickrate=5.0,
            games=1000,
        )
    ]
    assistant.score_against_team.return_value = 5.0

    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=assistant):
            monitor = DraftMonitor(verbose=False, auto_hover=False)

    monitor.current_pool = POOL
    monitor.champion_id_to_name = dict(CHAMPION_IDS)
    return monitor


def test_blind_pick_uses_pool_lane_when_set(monitor):
    """pool_lane (mono-role pool, resolved before champion select opens)
    takes precedence and must be threaded into get_matchups_for_draft."""
    monitor.pool_lane = "middle"

    monitor._get_best_champion_from_pool()

    monitor.assistant.get_matchups_for_draft.assert_called_with("Yasuo", lane="middle")


def test_blind_pick_falls_back_to_lcu_position_when_no_pool_lane(monitor):
    """No pool_lane (multi-role pool): fall back to the LCU-assigned
    position from the last known draft state, not the all-lanes aggregate."""
    monitor.pool_lane = None
    monitor.last_draft_state = DraftState(local_player_cell_id=1, ally_positions={1: "bottom"})

    monitor._get_best_champion_from_pool()

    monitor.assistant.get_matchups_for_draft.assert_called_with("Yasuo", lane="bottom")


def test_blind_pick_uses_no_lane_when_truly_unknown(monitor):
    """Neither source available (queue with no assigned roles): unchanged
    all-lanes behavior — never a crash, and never a fabricated lane."""
    monitor.pool_lane = None
    monitor.last_draft_state = DraftState()  # no local_player_cell_id, empty ally_positions

    monitor._get_best_champion_from_pool()

    monitor.assistant.get_matchups_for_draft.assert_called_with("Yasuo", lane=None)
