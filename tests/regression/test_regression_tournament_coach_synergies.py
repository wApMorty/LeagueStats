"""Regression test: le Tournament Coach ignorait les synergies alliées.

Bug: `Assistant._calculate_and_display_recommendations()` et les fonctions de
`src/ui/tournament_display_ui.py` (status, analyze) ne calculaient qu'un score
de matchup contre l'équipe ennemie -- `ally_team` ne servait qu'à exclure les
champions déjà pick, jamais à calculer un bonus de synergie, alors que le
Live Coach (`src/draft_monitor.py`) le fait bien via `DraftScorer`.

Fix: `Assistant` construit maintenant un `DraftScorer` partagé
(`self.draft_scorer`) et l'utilise à la fois pour les recommandations
(`RecommendationEngine.calculate_and_display_recommendations`) et pour le
score bidirectionnel exposé via `Assistant.score_with_synergy()`, unifiant le
moteur de scoring du Tournament Coach sur celui du Live Coach.
"""

import sqlite3

import pytest

from src.assistant import Assistant
from src.db import Database


@pytest.fixture
def synergy_capable_db(tmp_path):
    """Base de test minimale incluant matchups ET synergies (le fixture `db`
    partagé de tests/conftest.py n'a pas de table `synergies`)."""
    db_path = tmp_path / "test_tournament_synergies.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE champions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            role TEXT
        )
        """)
    cursor.execute("""
        CREATE TABLE matchups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            enemy INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            lane TEXT,
            FOREIGN KEY (champion) REFERENCES champions(id),
            FOREIGN KEY (enemy) REFERENCES champions(id)
        )
        """)
    cursor.execute("""
        CREATE TABLE synergies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            ally INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            lane TEXT,
            FOREIGN KEY (champion) REFERENCES champions(id),
            FOREIGN KEY (ally) REFERENCES champions(id)
        )
        """)

    for champ in ("Yasuo", "Ally1", "Enemy1"):
        cursor.execute("INSERT INTO champions (name) VALUES (?)", (champ,))
    ids = dict(cursor.execute("SELECT name, id FROM champions").fetchall())

    # Matchup neutre Yasuo vs Enemy1 : le score de matchup seul doit être ~0.
    cursor.execute(
        "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) "
        "VALUES (?, ?, 50.0, 0.0, 0.0, 10.0, 12000)",
        (ids["Yasuo"], ids["Enemy1"]),
    )
    # Forte synergie Yasuo + Ally1, au-dessus des seuils de qualité
    # (synergy_config.MIN_SYNERGY_PICKRATE=0.5, MIN_SYNERGY_GAMES=200).
    cursor.execute(
        "INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games) "
        "VALUES (?, ?, 60.0, 250.0, 300.0, 15.0, 1200)",
        (ids["Yasuo"], ids["Ally1"]),
    )
    conn.commit()
    conn.close()

    database = Database(str(db_path))
    database.connect()
    yield database
    database.close()


def test_recommendation_score_rises_with_ally_synergy(synergy_capable_db):
    """Same candidate, same enemy team: adding a strong synergy ally to
    ally_team must raise the recommendation score above the matchup-only
    baseline -- proves ally_team is no longer ignored by the Tournament Coach.
    """
    assistant = Assistant(db=synergy_capable_db)

    baseline = assistant._calculate_and_display_recommendations(
        enemy_team=["Enemy1"],
        ally_team=[],
        nb_results=1,
        champion_pool=["Yasuo"],
    )
    with_synergy = assistant._calculate_and_display_recommendations(
        enemy_team=["Enemy1"],
        ally_team=["Ally1"],
        nb_results=1,
        champion_pool=["Yasuo"],
    )

    assert baseline[0][0] == "Yasuo"
    assert with_synergy[0][0] == "Yasuo"
    # Regression: before the fix, both scores were identical (ally_team was
    # only used to filter already-picked champions, never for synergy).
    assert with_synergy[0][1] > baseline[0][1]
    assert baseline[0][1] == pytest.approx(0.0, abs=0.5)


def test_score_with_synergy_blends_matchup_and_synergy(synergy_capable_db):
    """Assistant.score_with_synergy (used by the Tournament Coach's status/
    analyze commands) must add the synergy bonus, not just the matchup score.
    """
    assistant = Assistant(db=synergy_capable_db)
    matchups = assistant.db.get_champion_matchups_by_name("Yasuo")

    matchup_only = assistant.score_against_team(matchups, ["Enemy1"], "Yasuo")
    blended = assistant.score_with_synergy(matchups, ["Enemy1"], ["Ally1"], "Yasuo")

    assert blended > matchup_only
