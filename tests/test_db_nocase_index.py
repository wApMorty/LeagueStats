"""Tests de l'index insensible à la casse sur champions.name (SPEC-06 C4).

`get_matchup_delta2` filtre sur `c1.name = ? COLLATE NOCASE` : sans index
NOCASE, SQLite ne peut pas utiliser `idx_champions_name` et attaque la
requête par la table `matchups` (6,68 ms/appel sur la base de production,
contre 0,11 ms avec l'index).
"""

import sqlite3

import pytest

from src.db import Database

MATCHUP_QUERY = """
    SELECT m.delta2, m.games
    FROM matchups m
    JOIN champions c1 ON m.champion = c1.id
    JOIN champions c2 ON m.enemy = c2.id
    WHERE c1.name = ? COLLATE NOCASE
    AND c2.name = ? COLLATE NOCASE
    AND m.pickrate >= 0.5
    AND m.games >= 200
"""


@pytest.fixture
def db_with_matchup(tmp_path):
    """Base minimale : Jinx vs Caitlyn, avec les index applicatifs créés."""
    db_path = tmp_path / "test_nocase.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE champions (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL)")
    conn.execute("""
        CREATE TABLE matchups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            enemy INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL
        )
        """)
    conn.execute("INSERT INTO champions (id, name) VALUES (1, 'Jinx'), (2, 'Caitlyn')")
    conn.execute(
        "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games) "
        "VALUES (1, 2, 52.0, 100.0, 150.0, 5.0, 1000)"
    )
    conn.commit()
    conn.close()

    db = Database(str(db_path))
    db.connect()
    db.create_database_indexes()
    yield db
    db.close()


def test_nocase_index_is_created(db_with_matchup):
    """L'index NOCASE est créé sur les bases existantes au premier connect."""
    indexes = {
        row[0]
        for row in db_with_matchup.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='champions'"
        )
    }

    assert "idx_champions_name_nocase" in indexes


def test_matchup_query_uses_the_nocase_index(db_with_matchup):
    """Le plan de requête part de champions par index, plus de la table matchups."""
    plan = " | ".join(
        row[3]
        for row in db_with_matchup.connection.execute(
            "EXPLAIN QUERY PLAN " + MATCHUP_QUERY, ("Jinx", "Caitlyn")
        )
    )

    assert "idx_champions_name_nocase" in plan
    assert "SCAN matchups" not in plan


@pytest.mark.parametrize("name", ["Jinx", "jinx", "JINX", "jInX"])
def test_lookup_stays_case_insensitive(db_with_matchup, name):
    """L'insensibilité à la casse est conservée après ajout de l'index."""
    assert db_with_matchup.get_matchup_delta2(name, "caitlyn") == pytest.approx(150.0)


def test_migration_is_chained_on_head():
    """La migration ab14babf365b est la tête et suit b7e41c9a3f02."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))

    assert list(script.get_heads()) == ["ab14babf365b"]
    assert script.get_revision("ab14babf365b").down_revision == "b7e41c9a3f02"
