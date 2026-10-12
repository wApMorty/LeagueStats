"""Régression : Death's Dance absente des situationnels d'Ambessa (2026-09-25).

Le bloc « Cores alternatifs » listait le 2e item des autres cores (Death's
Dance, 6 % en core) et la déduplication le retirait ensuite des situationnels,
où OneTricks le classe parmi les suites du core. SPEC-31 réintroduit un bloc
« Autres cores » : un item à la fois dans le chemin du core choisi et dans un
autre core reste en « Situationnels », sur la fixture Jinx
(Infinity Edge, 72 %, est dans le chemin du core et dans le core Yun Tal + Infinity Edge).
"""

import json
from pathlib import Path

from src.draft.loadout import _core_path, _option, pick_build

FIXTURES = Path(__file__).parent.parent / "fixtures"


def test_item_in_the_path_and_in_another_core_stays_situational():
    item = 3031
    page = json.loads((FIXTURES / "onetricks_jinx_bot.json").read_text(encoding="utf-8"))
    stats = page["firstItemStats"]["all"]["all"]
    core = _option(stats["popCore"][0][0])
    other_cores = [_option(option) for option, _ in stats["popCore"][1:]]
    path = [path_item for path_item, _, _ in _core_path(stats, 500, core)]
    assert item in path and any(item in option for option in other_cores)
    blocks = dict(pick_build(page).item_blocks)
    assert item in blocks["Situationnels"]
    assert item not in blocks["Autres cores"]
