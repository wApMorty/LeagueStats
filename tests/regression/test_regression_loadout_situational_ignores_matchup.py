"""Régression : les situationnels ignoraient le duel (2026-09-29).

Le test de sur-représentation au duel ne portait que sur départ, core et
bottes : les items légendaires gardaient l'ordre de la page générale, même
quand l'adversaire en faisait acheter un nettement plus souvent.
"""

import json
from pathlib import Path

from src.draft.loadout import adapt_to_matchup

FIXTURES = Path(__file__).parent.parent / "fixtures"
KRAKEN_SLAYER, HEXOPTICS = 6672, 2523


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_item_over_represented_in_the_duel_leads_the_situationals():
    general, duel = load("onetricks_jinx_bot.json"), load("onetricks_jinx_bot_vs_draven.json")
    popular = general["firstItemStats"]["all"]["all"]["popularItems"]
    boosted = {str(KRAKEN_SLAYER): 0.25, str(HEXOPTICS): 0.95}  # 5,9 % et 74 % en général
    duel_items = [[item, boosted.get(item, share)] for item, share in popular]
    duel["firstItemStats"]["all"]["all"]["popularItems"] = duel_items
    build, subs = adapt_to_matchup(general, duel)
    assert dict(build.item_blocks)["Situationnels"][0] == KRAKEN_SLAYER
    # Hexoptics, significatif lui aussi, est déjà dans le core : rien à signaler.
    assert [sub.new for sub in subs if sub.category == "Situationnels"] == [(KRAKEN_SLAYER,)]
