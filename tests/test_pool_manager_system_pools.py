"""Tests for PoolManager's DB-driven system pools (issue #41).

The "All X Champions" system pools used to be hardcoded lists in
src/constants.py, drifting out of sync with the meta. They are now computed
from the lane already tagged on matchup rows by the multi-lane pipeline
(src/lane_discovery.py, src/multilane.py), falling back per-role to the
hardcoded constants.py lists when the DB has no lane data yet (fresh
install, before the first multi-lane scrape).
"""

import sqlite3

import pytest

from src.pool_manager import PoolManager


def _insert_champion(conn, champion_id, name):
    conn.execute("INSERT INTO champions (id, name) VALUES (?, ?)", (champion_id, name))


def _insert_matchup(conn, champion_id, enemy_id, lane):
    conn.execute(
        """
        INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane)
        VALUES (?, ?, 50.0, 0.0, 0.0, 15.0, 100, ?)
        """,
        (champion_id, enemy_id, lane),
    )


@pytest.fixture
def pool_manager_env(tmp_path, monkeypatch):
    """Isolate PoolManager from the real DB and the real champion_pools.json."""
    pools_file = tmp_path / "champion_pools.json"
    monkeypatch.setattr("src.pool_manager.get_user_pools_path", lambda: str(pools_file))
    return pools_file


class TestSystemPoolsFallbackToConstants:
    def test_no_database_falls_back_to_hardcoded_pools(
        self, pool_manager_env, tmp_path, monkeypatch
    ):
        """Fresh install / no db.db yet: system pools use the constants.py lists."""
        missing_db_path = tmp_path / "does_not_exist.db"
        monkeypatch.setattr("src.config.config.DATABASE_PATH", str(missing_db_path))

        from src.constants import TOP_SOLOQ_POOL

        manager = PoolManager()
        pool = manager.get_pool("All Top Champions")

        assert pool.created_by == "system"
        assert pool.champions == TOP_SOLOQ_POOL

    def test_empty_database_falls_back_to_hardcoded_pools(
        self, pool_manager_env, temp_db, monkeypatch
    ):
        """DB exists but has no lane-tagged matchups: fall back for every role."""
        monkeypatch.setattr("src.config.config.DATABASE_PATH", str(temp_db))

        from src.constants import SUPPORT_SOLOQ_POOL

        manager = PoolManager()
        pool = manager.get_pool("All Support Champions")

        assert pool.champions == SUPPORT_SOLOQ_POOL


class TestSystemPoolsFromDatabase:
    def test_role_with_lane_data_is_computed_from_db(self, pool_manager_env, temp_db, monkeypatch):
        """A role with tagged matchup rows uses the DB champions, not the fallback list."""
        monkeypatch.setattr("src.config.config.DATABASE_PATH", str(temp_db))

        conn = sqlite3.connect(str(temp_db))
        _insert_champion(conn, 1, "Jayce")
        _insert_champion(conn, 2, "Camille")
        _insert_champion(conn, 3, "Nidalee")
        _insert_matchup(conn, 1, 2, "top")
        _insert_matchup(conn, 2, 1, "top")
        conn.commit()
        conn.close()

        manager = PoolManager()
        pool = manager.get_pool("All Top Champions")

        assert pool.champions == ["Camille", "Jayce"]
        assert pool.created_by == "system"

    def test_role_without_lane_data_still_falls_back_individually(
        self, pool_manager_env, temp_db, monkeypatch
    ):
        """Only the roles with DB data switch over; others keep the hardcoded fallback."""
        monkeypatch.setattr("src.config.config.DATABASE_PATH", str(temp_db))

        conn = sqlite3.connect(str(temp_db))
        _insert_champion(conn, 1, "Jayce")
        _insert_champion(conn, 2, "Camille")
        _insert_matchup(conn, 1, 2, "top")
        conn.commit()
        conn.close()

        from src.constants import JUNGLE_SOLOQ_POOL

        manager = PoolManager()
        assert manager.get_pool("All Top Champions").champions == ["Jayce"]
        assert manager.get_pool("All Jungle Champions").champions == JUNGLE_SOLOQ_POOL

    def test_multi_lane_champion_appears_in_every_played_role(
        self, pool_manager_env, temp_db, monkeypatch
    ):
        """A champion tagged with two lanes (e.g. Pyke) belongs to both role pools."""
        monkeypatch.setattr("src.config.config.DATABASE_PATH", str(temp_db))

        conn = sqlite3.connect(str(temp_db))
        _insert_champion(conn, 1, "Pyke")
        _insert_champion(conn, 2, "Sylas")
        _insert_matchup(conn, 1, 2, "top")
        _insert_matchup(conn, 1, 2, "support")
        conn.commit()
        conn.close()

        manager = PoolManager()
        assert "Pyke" in manager.get_pool("All Top Champions").champions
        assert "Pyke" in manager.get_pool("All Support Champions").champions

    def test_untagged_rows_are_ignored(self, pool_manager_env, temp_db, monkeypatch):
        """lane=NULL rows (discovery failure fallback) don't count towards any role pool."""
        monkeypatch.setattr("src.config.config.DATABASE_PATH", str(temp_db))

        conn = sqlite3.connect(str(temp_db))
        _insert_champion(conn, 1, "UnknownLaneChamp")
        _insert_champion(conn, 2, "Jayce")
        _insert_matchup(conn, 1, 2, None)
        conn.commit()
        conn.close()

        from src.constants import TOP_SOLOQ_POOL

        manager = PoolManager()
        pool = manager.get_pool("All Top Champions")
        assert "UnknownLaneChamp" not in pool.champions
        assert pool.champions == TOP_SOLOQ_POOL
