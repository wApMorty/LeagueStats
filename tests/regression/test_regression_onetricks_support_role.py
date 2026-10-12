"""Régression : aucune page OneTricks pour les supports (2026-10-12).

OneTricks nomme ce poste « supp » (``?role=support`` et ``?role=utility`` répondent 404, et
``gameRoles.playerRole`` vaut « supp ») ; ``LANE_TO_ONETRICKS_ROLE`` ne traduisait que mid et bot.
Pas de build importée pour un support, et ni objectif OneTricks pour le coach de gameplay
(`objective_from_history`, même table).
"""

from unittest.mock import Mock, patch

from src.coaching.grid import objective_from_history
from src.draft.loadout import fetch_page


def test_support_page_is_requested_with_the_onetricks_role_name():
    with patch(
        "src.draft.loadout.requests.get", return_value=Mock(text="", raise_for_status=Mock())
    ) as get:
        fetch_page("Thresh", "support")
    assert get.call_args.kwargs["params"] == {"role": "supp"}


def test_support_games_are_found_by_their_onetricks_player_role():
    game = {
        "gameRoles": {"playerRole": "supp", "gd15": 120, "exp15": 80},
        "details": {"playerData": {"stats": {}}, "teamKills": 0},
    }
    refs = objective_from_history([game] * 40, "support", "OneTricks")
    assert refs  # avec « support » comme nom de poste, aucune partie ne correspondait
