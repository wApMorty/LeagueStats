"""Régression (2026-10-10, SPEC-29) : aucun axe de travail n'était jamais proposé. Le coach n'attendait
qu'un schéma négatif net face à la norme, que le joueur, au-dessus de ses pairs partout, ne produit pas ;
`coaching_goals` restait vide et l'accueil affichait deux « Place libre ».

Points couverts :
1. Sans schéma négatif face à la norme, le coach propose la métrique au z_objective moyen le plus bas.
2. Cette proposition n'est pas un défaut avéré : `propose` n'écrit rien.
3. Un schéma négatif net reste prioritaire et se fixe seul.
"""

import pytest

from src.coaching import goals
from src.config_constants import coaching_config
from src.repositories.coaching import CoachingRepository

# (z_norm, z_objective) par métrique : au-dessus de la norme partout, sous l'objectif sur un seul.
GAPS = {"gold_diff_15": 0.3, "xp_diff_15": 0.4, "deaths_per_10": -0.1}


def _store(db, z_norm=0.5, games=10):
    repo = CoachingRepository(db)
    rows = []
    for game_id in range(1, games + 1):
        db.insert_game_record(
            game_id=game_id,
            queue_id=420,
            game_creation_utc=f"2026-10-01 00:00:{game_id:02d}",
            duration_s=1800,
            player_participant_id=1,
            raw_game="{}",
            raw_timeline=None,
            raw_eog=None,
        )
        rows += [
            (game_id, 1, metric, 1, "top", 2, 1.0, 1.0, 0.5, 20, z_norm)
            + (1.0, 0.5, "onetricks", z_objective, coaching_config.GRID_VERSION)
            for metric, z_objective in GAPS.items()
        ]
    repo.insert_metrics(rows)
    return repo


def test_lowest_objective_gap_is_proposed_when_no_negative_pattern(db):
    repo = _store(db)

    proposal = goals.next_proposal(repo, "top")

    assert (proposal.metric, proposal.reference, proposal.net) == (
        "deaths_per_10",
        "objective",
        False,
    )
    assert proposal.gap == pytest.approx(-0.1)


def test_objective_proposal_is_never_written_by_propose(db):
    repo = _store(db)

    assert goals.propose(repo, "top") is None
    assert repo.goals() == []


def test_negative_pattern_against_the_norm_stays_first_and_is_fixed_alone(db):
    repo = _store(db, z_norm=-1.5)

    proposal = goals.next_proposal(repo, "top")
    message = goals.propose(repo, "top")

    assert proposal.reference == "norm" and proposal.net and proposal.gap is None
    assert "Nouvel axe" in message
    assert [g["reference"] for g in repo.goals()] == ["norm"]
