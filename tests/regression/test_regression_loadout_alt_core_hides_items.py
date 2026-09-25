"""Régression : Death's Dance absente des situationnels d'Ambessa (2026-09-25).

Le bloc « Cores alternatifs » listait le 2e item des autres cores (Death's
Dance, 6 % en core) et la déduplication le retirait ensuite des situationnels,
où OneTricks le classe 2e item le plus joué (46 %). Même cas sur la fixture :
Infinity Edge (72 %) n'apparaissait qu'en core alternatif.
"""

import json
from pathlib import Path

from src.config_constants import draft_config
from src.draft.loadout import pick_build

FIXTURE = Path(__file__).parent.parent / "fixtures" / "onetricks_jinx_bot.json"


def test_most_played_items_outside_the_core_are_all_situational():
    page = json.loads(FIXTURE.read_text(encoding="utf-8"))
    blocks = dict(pick_build(page).item_blocks)
    core = blocks["Core (57%)"]
    popular = [int(item) for item, _ in page["firstItemStats"]["all"]["all"]["popularItems"]]
    expected = [item for item in popular if item not in core]
    assert blocks["Situationnels"] == tuple(expected[: draft_config.LOADOUT_SITUATIONAL_ITEMS])
