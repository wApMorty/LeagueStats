"""Régression SPEC-06 E8 — la casse des noms d'alliés ne doit pas annuler la synergie.

`calculate_synergy_bonus` comparait `s.ally_name in ally_names` en exact, alors
que le reste du scoring normalise en minuscules. Toute variation de casse dans
la liste d'alliés faisait silencieusement tomber le bonus à 0.
"""

from unittest.mock import Mock

import pytest

from src.analysis.scoring import ChampionScorer
from src.models import Synergy


@pytest.fixture
def scorer():
    """Scorer avec une base simulée : Yasuo a une synergie avec Malphite."""
    db = Mock()
    db.get_champion_synergies_by_name.return_value = [
        Synergy(
            ally_name="Malphite",
            winrate=55.0,
            delta1=180.0,
            delta2=220.0,
            pickrate=15.0,
            games=1200,
        )
    ]
    return ChampionScorer(db, verbose=False)


@pytest.mark.parametrize("ally", ["Malphite", "malphite", "MALPHITE", "mAlPhItE"])
def test_synergy_bonus_ignores_ally_case(scorer, ally):
    """Le bonus est identique quelle que soit la casse du nom de l'allié."""
    bonus = scorer.calculate_synergy_bonus("Yasuo", [ally])

    assert bonus == pytest.approx(220.0, abs=0.1)


def test_synergy_bonus_still_zero_for_unknown_ally(scorer):
    """La normalisation ne doit pas faire matcher un allié absent."""
    assert scorer.calculate_synergy_bonus("Yasuo", ["Diana"]) == 0.0
