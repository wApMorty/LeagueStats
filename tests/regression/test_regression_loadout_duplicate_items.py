"""Régression : Sterak's Gage deux fois dans le set « LS Yorick top » (2026-09-25).

Le bloc « Suite » prenait le premier choix de chaque emplacement de
``popPath`` : le même item arrivait premier de deux emplacements et le set le
comptait deux fois. Hors départ (deux potions voulues), un item ne figure
qu'une fois dans le set.
"""

import json
from pathlib import Path

from src.draft.loadout import pick_build

FIXTURE = Path(__file__).parent.parent / "fixtures" / "onetricks_jinx_bot.json"


def test_no_item_listed_twice_outside_the_starting_block():
    page = json.loads(FIXTURE.read_text(encoding="utf-8"))
    stats = page["firstItemStats"]["all"]["all"]
    # Le même item premier de deux emplacements, et un core aussi populaire.
    stats["popPath"] = [[[[3053, 0.02]], [[3053, 0.01]]]]
    stats["popularItems"] = [["3053", 0.2], ["3053", 0.1], ["2523", 0.7]]

    blocks = pick_build(page).item_blocks
    items = [item for _, block in blocks[1:] for item in block]
    assert len(items) == len(set(items))
    assert set(blocks[0][1]).isdisjoint(items)
    assert items.count(3053) == 1
