"""Régression : l'ordre des compétences ignorait le duel (2026-11-10, SPEC-56).

Symptôme : Malphite top contre Nasus, l'écran « En partie » montrait Q > E > W alors que le
duel publie W > E > Q sur 32 % de 40 parties (absent des ordres publiés en général).

Cause racine : ``LoadoutImporter._describe`` lisait l'ordre sur la page générale
(``_skills(page)``), jamais sur celle du duel.

Correctif : l'ordre des compétences fait partie de ``Build`` ; ``adapt_to_matchup`` le
substitue par le même test binomial que les objets et les runes.

Prévention : ce test, sur les pages OneTricks enregistrées le 2026-11-10 (réduites par ``_trim``).
"""

import json
from pathlib import Path

from src.draft.loadout import adapt_to_matchup
from src.draft.loadout_import import LoadoutImporter

FIXTURES = Path(__file__).parent.parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_the_skill_order_follows_the_duel():
    general = load("onetricks_malphite_top.json")
    duel = load("onetricks_malphite_top_vs_nasus.json")
    build, subs = adapt_to_matchup(general, duel)
    skills = LoadoutImporter._describe(build, subs, general, duel)["skills"]
    assert skills["max_order"] == ["W", "E", "Q"]
    assert skills["levels"][0] == "W"
