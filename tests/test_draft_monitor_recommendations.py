"""Tests de l'affichage des recommandations du Live Coach.

SPEC-06 C3 (historique) : les scores affichés devaient être ceux qui avaient
servi au classement, jamais un recalcul — deux calculs séparés pouvaient
diverger. SPEC-12 rend la divergence structurellement impossible (la recherche
produit une valeur par candidat, l'affichage l'imprime), mais la propriété
reste testée ici : c'est elle qui garantit que le chiffre à l'écran est bien
celui qui a trié la liste.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft.search import PickTurn, SearchResult
from src.draft_monitor import DraftMonitor, DraftState
from src.models import Matchup

POOL = ["Aatrox", "Darius", "Garen", "Sett"]
CHAMPION_IDS = {266: "Aatrox", 122: "Darius", 86: "Garen", 875: "Sett", 64: "LeeSin"}
OUR_TURN = PickTurn(is_ally=True, is_local_player=True)


def _matchup(enemy="LeeSin", games=1000):
    return Matchup(
        enemy_name=enemy, winrate=52.0, delta1=100.0, delta2=150.0, pickrate=5.0, games=games
    )


@pytest.fixture
def monitor():
    """DraftMonitor avec LCU et Assistant simulés, pool de 4 champions."""
    assistant = Mock()
    assistant.db = Mock()
    assistant.get_matchups_for_draft.return_value = [_matchup()]
    # Tables réelles (vides) : l'évaluateur SPEC-12 les indexe, un Mock nu
    # ferait exploser les lookups de paires.
    assistant.db.get_all_matchups_bulk.return_value = {}
    assistant.db.get_all_synergies_bulk.return_value = {}
    assistant.db.get_all_champion_scores.return_value = []

    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=assistant):
            monitor = DraftMonitor(verbose=False, auto_hover=False)

    monitor.current_pool = POOL
    monitor.champion_id_to_name = dict(CHAMPION_IDS)
    return monitor


@pytest.fixture
def state():
    """Un ennemi pické, aucun allié, notre pick à venir : phase de counterpick."""
    return DraftState(
        phase="BAN_PICK",
        enemy_picks=[64],
        ally_picks=[],
        remaining_picks=[OUR_TURN],
    )


def test_pool_is_scored_once_per_champion(monitor, state, capsys):
    """Un seul passage en base par champion du pool, et une seule recherche.

    La recherche est appelée avec le pool entier : si elle était relancée par
    champion, le budget temps serait divisé par la taille du pool.
    """
    with patch.object(monitor.search, "rank", return_value=[]) as mock_rank:
        monitor._provide_recommendations(state)

    capsys.readouterr()
    assert monitor.assistant.get_matchups_for_draft.call_count == len(POOL)
    assert mock_rank.call_count == 1
    assert sorted(mock_rank.call_args.kwargs["pool"]) == sorted(POOL)


def test_displayed_probability_is_the_searched_one(monitor, state, capsys):
    """Le chiffre affiché est la valeur rendue par la recherche, pas un recalcul."""
    ranked = [
        SearchResult("Aatrox", "top", 0.5731, [("Fiora", "top")], depth=2),
        SearchResult("Darius", "top", 0.5210, [], depth=2),
        SearchResult("Garen", "top", 0.4890, [], depth=2),
        SearchResult("Sett", "top", 0.4102, [], depth=2),
    ]

    with patch.object(monitor.search, "rank", return_value=ranked):
        monitor._provide_recommendations(state)

    output = capsys.readouterr().out
    assert "[1st] Aatrox" in output
    assert "57.31%" in output
    assert "[2nd] Darius" in output
    assert "52.10%" in output
    # Sett est 4e : hors du top 3, donc jamais affiché
    assert "Sett" not in output


def test_principal_variation_is_displayed(monitor, state, capsys):
    """La réponse adverse anticipée est montrée au joueur : c'est l'intérêt
    d'une recherche par rapport à un score plat."""
    ranked = [SearchResult("Aatrox", "top", 0.53, [("Fiora", "top")], depth=2)]

    with patch.object(monitor.search, "rank", return_value=ranked):
        monitor._provide_recommendations(state)

    output = capsys.readouterr().out
    assert "suite attendue" in output
    assert "Fiora (top)" in output
    assert "Profondeur atteinte : 2" in output


def test_champion_without_data_is_listed_as_skipped_not_dropped(monitor, capsys):
    """SPEC-09 E1 : un champion de la pool sans matchups pour la lane doit
    apparaître comme écarté, jamais disparaître silencieusement.

    Avec SPEC-12 le risque change de nature mais reste le même : la recherche
    noterait un champion sans données à 50 %, soit exactement le score d'un
    matchup réellement neutre. Il doit donc être retiré du classement en amont.
    """
    pool = ["Aatrox", "Darius", "Malphite"]
    monitor.current_pool = pool
    monitor.champion_id_to_name = {**CHAMPION_IDS, 54: "Malphite"}
    state = DraftState(
        phase="BAN_PICK",
        enemy_picks=[64],
        ally_picks=[],
        local_player_cell_id=1,
        ally_positions={1: "middle"},
        remaining_picks=[OUR_TURN],
    )

    def fake_matchups(champion_name, lane=None):
        if champion_name == "Malphite":
            return []  # aucune donnée pour cette lane
        return [_matchup()]

    monitor.assistant.get_matchups_for_draft.side_effect = fake_matchups

    monitor._provide_recommendations(state)

    output = capsys.readouterr().out
    assert "Malphite (0 games)" in output
    assert "Sans données exploitables en middle" in output
    # Malphite ne doit jamais apparaître dans le classement [1st]/[2nd]/[3rd]
    for rank_line in output.splitlines():
        if rank_line.strip().startswith(("[1st]", "[2nd]", "[3rd]")):
            assert "Malphite" not in rank_line
    # Et il ne doit pas non plus être soumis à la recherche.
    assert "Malphite" not in str(monitor.search.candidates._by_lane)


class TestTurnSelection:
    """`_turns_from_our_next_pick` : la racine de la recherche doit être NOTRE
    tour, sinon la valeur par candidat perd son sens."""

    def test_turns_before_ours_are_dropped(self, monitor):
        state = DraftState(
            remaining_picks=[
                PickTurn(is_ally=False),
                PickTurn(is_ally=True),  # un allié, pas nous
                OUR_TURN,
                PickTurn(is_ally=False),
            ]
        )

        turns = monitor.recommender._turns_from_our_next_pick(state)

        assert turns[0] is OUR_TURN
        assert len(turns) == 2

    def test_no_remaining_pick_of_ours_returns_nothing(self, monitor):
        state = DraftState(remaining_picks=[PickTurn(is_ally=False)])
        assert monitor.recommender._turns_from_our_next_pick(state) == []

    def test_message_when_we_have_already_picked(self, monitor, capsys):
        """Après notre pick, un classement de counterpick n'aurait plus d'objet."""
        state = DraftState(phase="BAN_PICK", enemy_picks=[64], ally_picks=[266])

        monitor._provide_recommendations(state)

        assert "Plus aucun pick à jouer de votre côté" in capsys.readouterr().out
