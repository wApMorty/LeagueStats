"""Tests de la migration ea9a2b4722f1 — contrainte d'unicité par lane (SPEC-03, item B8).

Trois choses à couvrir :
- Dédoublonnage `(champion, enemy, lane)` / `(champion, ally, lane)` : la
  ligne au plus grand `games` survit (cas réel de l'audit : Annie vs Lux en
  support avait deux lignes contradictoires, delta2 = -9.25/67 parties et
  +4.61/72 parties).
- Backfill `lane IS NULL` -> `'default'` : aucune ligne non taguée ne doit
  survivre à la migration (SQLite ne contraint pas NULL != NULL).
- Idempotence applicative : `Database.add_matchups_batch` /
  `add_synergies_batch` mettent à jour au lieu de dupliquer sur un second
  appel pour le même triplet (`ON CONFLICT ... DO UPDATE`).

Créé : 2026-09-01 — SPEC-03 / B8
"""

import sqlite3

import pytest
from alembic import command
from alembic.config import Config

from src.db import Database


@pytest.fixture(autouse=True)
def _no_alembic_logging_reconfig(monkeypatch):
    """alembic/env.py calls fileConfig(alembic.ini) on every command run.

    fileConfig defaults to disable_existing_loggers=True, which disables
    every Python logger not listed in the ini — including ones already
    created by src/ modules (e.g. src.parallel_parser). Since pytest runs
    the whole suite in one process, that leaks into unrelated tests later
    in the session that rely on caplog. No-op the reconfiguration here;
    the app's own `alembic upgrade` CLI usage is unaffected (this only
    patches the test process).
    """
    monkeypatch.setattr("logging.config.fileConfig", lambda *a, **k: None)


def _make_pre_migration_db(db_path) -> None:
    """Base au schéma d'avant ea9a2b4722f1 : lane nullable, sans contrainte."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE champions (
            id INTEGER PRIMARY KEY,
            key TEXT,
            name TEXT NOT NULL,
            title TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE matchups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            enemy INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            lane TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE synergies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            champion INTEGER NOT NULL,
            ally INTEGER NOT NULL,
            winrate REAL NOT NULL,
            delta1 REAL NOT NULL,
            delta2 REAL NOT NULL,
            pickrate REAL NOT NULL,
            games INTEGER NOT NULL,
            lane TEXT
        )
    """)
    conn.execute("INSERT INTO champions (id, name) VALUES (1, 'Annie'), (2, 'Lux'), (3, 'Leona')")

    # Pre-3e87f22f2ec1 schema: migration 3e87f22f2ec1 (add lane column to
    # champion_scores) drops and recreates this table, so it must exist
    # before upgrading through it.
    conn.execute("""
        CREATE TABLE champion_scores (
            id INTEGER PRIMARY KEY,
            avg_delta2 REAL,
            variance REAL,
            coverage REAL,
            peak_impact REAL,
            volatility REAL,
            target_ratio REAL,
            FOREIGN KEY (id) REFERENCES champions(id) ON DELETE CASCADE
        )
    """)

    # Doublon (Annie, Lux, support), valeurs contradictoires (cas réel de
    # l'audit). On garde la ligne au plus grand `games` : id=2.
    conn.execute(
        "INSERT INTO matchups (id, champion, enemy, winrate, delta1, delta2, pickrate, games, lane)"
        " VALUES (1, 1, 2, 40.0, -8.0, -9.25, 3.0, 67, 'support')"
    )
    conn.execute(
        "INSERT INTO matchups (id, champion, enemy, winrate, delta1, delta2, pickrate, games, lane)"
        " VALUES (2, 1, 2, 55.0, 4.0, 4.61, 3.0, 72, 'support')"
    )
    # Ligne non dupliquée, lane NULL (repli découverte de lane échouée).
    conn.execute(
        "INSERT INTO matchups (id, champion, enemy, winrate, delta1, delta2, pickrate, games, lane)"
        " VALUES (3, 2, 1, 50.0, 0.0, 0.0, 2.0, 500, NULL)"
    )

    # Doublon synergies (Annie, Leona, top).
    conn.execute(
        "INSERT INTO synergies (id, champion, ally, winrate, delta1, delta2, pickrate, games, lane)"
        " VALUES (1, 1, 3, 50.0, 1.0, 1.0, 1.0, 100, 'top')"
    )
    conn.execute(
        "INSERT INTO synergies (id, champion, ally, winrate, delta1, delta2, pickrate, games, lane)"
        " VALUES (2, 1, 3, 52.0, 2.0, 2.0, 1.0, 300, 'top')"
    )
    conn.commit()
    conn.close()


def _upgrade_to_head(db_path) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.stamp(cfg, "ab14babf365b")
    command.upgrade(cfg, "head")
    return cfg


@pytest.fixture
def migrated_db(tmp_path):
    db_path = tmp_path / "migration_test.db"
    _make_pre_migration_db(db_path)
    _upgrade_to_head(db_path)

    conn = sqlite3.connect(str(db_path))
    yield conn
    conn.close()


class TestDedup:
    def test_matchups_deduplicated_keeps_highest_games(self, migrated_db):
        rows = migrated_db.execute(
            "SELECT id, games, delta2 FROM matchups WHERE champion = 1 AND enemy = 2 AND lane = 'support'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 2
        assert rows[0][1] == 72
        assert rows[0][2] == pytest.approx(4.61)

    def test_synergies_deduplicated_keeps_highest_games(self, migrated_db):
        rows = migrated_db.execute(
            "SELECT id, games FROM synergies WHERE champion = 1 AND ally = 3 AND lane = 'top'"
        ).fetchall()
        assert rows == [(2, 300)]

    def test_null_lane_backfilled_to_default(self, migrated_db):
        row = migrated_db.execute(
            "SELECT lane FROM matchups WHERE champion = 2 AND enemy = 1"
        ).fetchone()
        assert row == ("default",)
        assert migrated_db.execute(
            "SELECT COUNT(*) FROM matchups WHERE lane IS NULL"
        ).fetchone() == (0,)


class TestUniqueConstraintEnforced:
    def test_raw_duplicate_matchup_insert_rejected(self, migrated_db):
        with pytest.raises(sqlite3.IntegrityError):
            migrated_db.execute(
                "INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane)"
                " VALUES (1, 2, 1.0, 1.0, 1.0, 1.0, 1, 'support')"
            )

    def test_raw_duplicate_synergy_insert_rejected(self, migrated_db):
        with pytest.raises(sqlite3.IntegrityError):
            migrated_db.execute(
                "INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games, lane)"
                " VALUES (1, 3, 1.0, 1.0, 1.0, 1.0, 1, 'top')"
            )


def test_downgrade_drops_unique_indexes_but_dedup_is_not_reversed(tmp_path):
    """downgrade() ne retire que les index : le dédoublonnage est définitif."""
    db_path = tmp_path / "downgrade_test.db"
    _make_pre_migration_db(db_path)
    cfg = _upgrade_to_head(db_path)
    command.downgrade(cfg, "ab14babf365b")

    conn = sqlite3.connect(str(db_path))
    try:
        indexes = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        }
        assert "idx_matchups_unique" not in indexes
        assert "idx_synergies_unique" not in indexes

        rows = conn.execute(
            "SELECT games FROM matchups WHERE champion = 1 AND enemy = 2 AND lane = 'support'"
        ).fetchall()
        assert rows == [(72,)]
    finally:
        conn.close()


@pytest.fixture
def fresh_db(tmp_path):
    """Base neuve, schéma applicatif (Database.init_*_table), pour tester
    l'idempotence des insertions plutôt que la migration elle-même."""
    db_path = tmp_path / "idempotent_test.db"
    db = Database(str(db_path))
    db.connect()
    cursor = db.connection.cursor()
    cursor.execute(
        "CREATE TABLE champions (id INTEGER PRIMARY KEY, key TEXT, name TEXT NOT NULL, title TEXT)"
    )
    cursor.executemany("INSERT INTO champions (id, name) VALUES (?, ?)", [(1, "Annie"), (2, "Lux")])
    db.connection.commit()
    db.init_matchups_table()
    db.init_synergies_table()
    yield db
    db.close()


class TestIdempotentInsert:
    """Second appel pour le même triplet -> update, jamais de doublon."""

    def test_second_matchup_insert_updates_instead_of_duplicating(self, fresh_db):
        fresh_db.add_matchups_batch([("Annie", "Lux", 40.0, -8.0, -9.25, 3.0, 67)], lane="support")
        fresh_db.add_matchups_batch([("Annie", "Lux", 55.0, 4.0, 4.61, 3.0, 72)], lane="support")

        rows = fresh_db.connection.execute(
            "SELECT games, delta2 FROM matchups WHERE champion = 1 AND enemy = 2 AND lane = 'support'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 72
        assert rows[0][1] == pytest.approx(4.61)

    def test_none_lane_stored_as_default_and_stays_unique(self, fresh_db):
        fresh_db.add_matchups_batch([("Annie", "Lux", 50.0, 0.0, 0.0, 1.0, 100)])
        fresh_db.add_matchups_batch([("Annie", "Lux", 51.0, 1.0, 1.0, 1.0, 200)])

        rows = fresh_db.connection.execute(
            "SELECT lane, games FROM matchups WHERE champion = 1 AND enemy = 2"
        ).fetchall()
        assert rows == [("default", 200)]

    def test_second_synergy_insert_updates_instead_of_duplicating(self, fresh_db):
        fresh_db.add_synergies_batch([("Annie", "Lux", 50.0, 1.0, 1.0, 1.0, 100)], lane="top")
        fresh_db.add_synergies_batch([("Annie", "Lux", 52.0, 2.0, 2.0, 1.0, 300)], lane="top")

        rows = fresh_db.connection.execute(
            "SELECT games FROM synergies WHERE champion = 1 AND ally = 2 AND lane = 'top'"
        ).fetchall()
        assert rows == [(300,)]
