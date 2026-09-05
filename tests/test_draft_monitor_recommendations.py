"""Tests du calcul unique des scores affichés (SPEC-06 C3).

`_provide_recommendations` calculait matchup et synergie pour tout le pool,
triait, puis **recalculait les deux** pour chacun des 3 champions affichés.
Au-delà du coût, deux calculs séparés peuvent diverger : le classement
afficherait alors un détail qui ne le justifie pas.
"""

from unittest.mock import Mock, patch

import pytest

from src.draft_monitor import DraftMonitor, DraftState
from src.models import Matchup

POOL = ["Aatrox", "Darius", "Garen", "Sett"]
CHAMPION_IDS = {266: "Aatrox", 122: "Darius", 86: "Garen", 875: "Sett", 64: "LeeSin"}


@pytest.fixture
def monitor():
    """DraftMonitor avec LCU et Assistant simulés, pool de 4 champions."""
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

    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=assistant):
            monitor = DraftMonitor(verbose=False, auto_hover=False)

    monitor.current_pool = POOL
    monitor.champion_id_to_name = dict(CHAMPION_IDS)
    return monitor


@pytest.fixture
def state():
    """Un ennemi pické, aucun allié : phase de counterpick."""
    return DraftState(phase="BAN_PICK", enemy_picks=[64], ally_picks=[])


def test_scores_are_computed_once_per_champion(monitor, state, capsys):
    """Chaque champion du pool n'est scoré qu'une fois, y compris ceux affichés."""
    with (
        patch.object(monitor, "_calculate_score_against_team", return_value=10.0) as mock_matchup,
        patch.object(monitor, "_calculate_synergy_score", return_value=2.0) as mock_synergy,
    ):
        monitor._provide_recommendations(state)

    capsys.readouterr()
    assert mock_matchup.call_count == len(POOL)
    assert mock_synergy.call_count == len(POOL)


def test_displayed_breakdown_matches_the_ranking(monitor, state, capsys):
    """Le détail affiché est celui qui a servi au classement, pas un recalcul."""
    matchup_by_champion = {"Aatrox": 30.0, "Darius": 20.0, "Garen": 10.0, "Sett": 5.0}

    with (
        patch.object(
            monitor,
            "_calculate_score_against_team",
            side_effect=lambda matchups, enemies, name, bans, **kwargs: matchup_by_champion[name],
        ),
        patch.object(monitor, "_calculate_synergy_score", return_value=0.0),
    ):
        monitor._provide_recommendations(state)

    output = capsys.readouterr().out
    assert "[1st] Aatrox" in output
    assert "Matchup: +30.00%" in output
    assert "[2nd] Darius" in output
    assert "Matchup: +20.00%" in output
    # Sett est 4e : hors du top 3, donc jamais affiché
    assert "Sett" not in output


def test_champion_without_data_is_listed_as_skipped_not_dropped(monitor, capsys):
    """SPEC-09 E1 : un champion de la pool sans matchups pour la lane doit
    apparaître comme écarté, jamais disparaître silencieusement.

    Avant le fix, l'absence de `else` dans `DraftRecommender.provide()`
    faisait sortir ce champion de la liste sans laisser de trace : le joueur
    ne pouvait pas distinguer "mauvais pick" de "aucune donnée en base".
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
    )

    def fake_matchups(champion_name, lane=None):
        if champion_name == "Malphite":
            return []  # aucune donnée pour cette lane
        return [
            Matchup(
                enemy_name="LeeSin",
                winrate=52.0,
                delta1=100.0,
                delta2=150.0,
                pickrate=5.0,
                games=1000,
            )
        ]

    monitor.assistant.get_matchups_for_draft.side_effect = fake_matchups

    with (
        patch.object(monitor, "_calculate_score_against_team", return_value=10.0),
        patch.object(monitor, "_calculate_synergy_score", return_value=0.0),
    ):
        monitor._provide_recommendations(state)

    output = capsys.readouterr().out
    assert "Malphite (0 games)" in output
    assert "Sans données exploitables en middle" in output
    # Malphite ne doit jamais apparaître dans le classement [1st]/[2nd]/[3rd]
    for rank_line in output.splitlines():
        if rank_line.strip().startswith(("[1st]", "[2nd]", "[3rd]")):
            assert "Malphite" not in rank_line
