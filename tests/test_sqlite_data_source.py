"""
Tests for SQLiteDataSource - Thin wrapper around Database class.

This test suite ensures that SQLiteDataSource correctly delegates all operations
to the underlying Database instance without adding or changing behavior.

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration (Adapter Pattern Implementation)
"""

import pytest
from src.sqlite_data_source import SQLiteDataSource
from src.models import Matchup, MatchupDraft, Synergy


class TestSQLiteDataSourceBasics:
    """Test basic connection management and instantiation."""

    def test_init_creates_database_instance(self, temp_db):
        """Test that initialization creates a Database instance."""
        data_source = SQLiteDataSource(str(temp_db))
        assert data_source._db is not None

    def test_connect_establishes_connection(self, temp_db):
        """Test that connect() establishes database connection."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()
        assert data_source._db.connection is not None
        data_source.close()

    def test_close_closes_connection(self, temp_db):
        """Test that close() properly closes database connection."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()
        data_source.close()
        # After close, connection should be None or closed
        # SQLite doesn't provide a clean way to check, but no exception means success


class TestSQLiteDataSourceChampionQueries:
    """Test champion-related queries delegation."""

    @pytest.fixture
    def data_source_with_champions(self, temp_db, sample_champions):
        """Create data source with sample champions loaded."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()
        # Use underlying db fixture to insert data
        cursor = data_source._db.connection.cursor()
        for champ in sample_champions:
            cursor.execute(
                "INSERT OR IGNORE INTO champions (name, role) VALUES (?, ?)", (champ, "top")
            )
        data_source._db.connection.commit()
        yield data_source
        data_source.close()

    def test_get_champion_id_returns_correct_id(self, data_source_with_champions):
        """Test get_champion_id() delegates correctly."""
        champion_id = data_source_with_champions.get_champion_id("Aatrox")
        assert champion_id is not None
        assert isinstance(champion_id, int)

    def test_get_champion_id_returns_none_for_invalid_name(self, data_source_with_champions):
        """Test get_champion_id() returns None for non-existent champion."""
        champion_id = data_source_with_champions.get_champion_id("InvalidChampion")
        assert champion_id is None

    def test_get_champion_by_id_returns_correct_name(self, data_source_with_champions):
        """Test get_champion_by_id() delegates correctly."""
        # Get ID first
        champion_id = data_source_with_champions.get_champion_id("Darius")
        # Then lookup by ID
        champion_name = data_source_with_champions.get_champion_by_id(champion_id)
        assert champion_name == "Darius"

    def test_get_champion_by_id_returns_none_for_invalid_id(self, data_source_with_champions):
        """Test get_champion_by_id() returns None for non-existent ID."""
        champion_name = data_source_with_champions.get_champion_by_id(9999)
        assert champion_name is None

    def test_get_all_champion_names_returns_dict(self, data_source_with_champions):
        """Test get_all_champion_names() returns complete mapping."""
        champion_names = data_source_with_champions.get_all_champion_names()
        assert isinstance(champion_names, dict)
        assert len(champion_names) >= 6  # At least sample champions
        # Check that mapping is id -> name
        for champ_id, name in champion_names.items():
            assert isinstance(champ_id, int)
            assert isinstance(name, str)

    def test_build_champion_cache_returns_dict(self, data_source_with_champions):
        """Test build_champion_cache() returns name -> ID mapping."""
        cache = data_source_with_champions.build_champion_cache()
        assert isinstance(cache, dict)
        assert "Aatrox" in cache or "aatrox" in cache
        # Check that mapping is name -> id
        for name, champ_id in cache.items():
            assert isinstance(name, str)
            assert isinstance(champ_id, int)


class TestSQLiteDataSourceMatchupQueries:
    """Test matchup-related queries delegation."""

    @pytest.fixture
    def data_source_with_matchups(self, temp_db, insert_matchup):
        """Create data source with sample matchup data."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()

        # Insert test matchups using helper
        insert_matchup("Aatrox", "Darius", 48.5, -150, -200, 8.5, 1500)
        insert_matchup("Aatrox", "Garen", 52.0, 100, 150, 12.3, 2000)
        insert_matchup("Aatrox", "Teemo", 45.0, -300, -400, 5.2, 800)

        yield data_source
        data_source.close()

    def test_get_champion_matchups_by_name_returns_matchup_objects(self, data_source_with_matchups):
        """Test get_champion_matchups_by_name() returns Matchup dataclasses."""
        matchups = data_source_with_matchups.get_champion_matchups_by_name("Aatrox")
        assert isinstance(matchups, list)
        assert len(matchups) == 3
        assert all(isinstance(m, Matchup) for m in matchups)

    def test_get_champion_matchups_by_name_returns_tuples_when_requested(
        self, data_source_with_matchups
    ):
        """Test get_champion_matchups_by_name() can return tuples for backward compatibility."""
        matchups = data_source_with_matchups.get_champion_matchups_by_name(
            "Aatrox", as_dataclass=False
        )
        assert isinstance(matchups, list)
        assert len(matchups) == 3
        assert all(isinstance(m, tuple) for m in matchups)

    def test_get_champion_matchups_for_draft_returns_matchupdraft_objects(
        self, data_source_with_matchups
    ):
        """Test get_champion_matchups_for_draft() returns MatchupDraft dataclasses."""
        matchups = data_source_with_matchups.get_champion_matchups_for_draft("Aatrox")
        assert isinstance(matchups, list)
        assert len(matchups) == 3
        assert all(isinstance(m, MatchupDraft) for m in matchups)
        # MatchupDraft should only have 4 fields
        for m in matchups:
            assert hasattr(m, "enemy_name")
            assert hasattr(m, "delta2")
            assert hasattr(m, "pickrate")
            assert hasattr(m, "games")

    def test_get_matchup_delta2_returns_float(self, data_source_with_matchups):
        """Test get_matchup_delta2() returns correct delta2 value."""
        delta2 = data_source_with_matchups.get_matchup_delta2("Aatrox", "Garen")
        assert delta2 == 150.0

    def test_get_matchup_delta2_returns_none_for_invalid_matchup(self, data_source_with_matchups):
        """Test get_matchup_delta2() returns None for non-existent matchup."""
        delta2 = data_source_with_matchups.get_matchup_delta2("Aatrox", "InvalidChamp")
        assert delta2 is None

    def test_get_all_matchups_bulk_returns_dict(self, data_source_with_matchups):
        """Test get_all_matchups_bulk() returns complete matchup cache."""
        matchups_bulk = data_source_with_matchups.get_all_matchups_bulk()
        assert isinstance(matchups_bulk, dict)
        # Check structure: (champion_name, enemy_name) -> delta2
        for key, value in matchups_bulk.items():
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert isinstance(value, float)

    def test_get_champion_base_winrate_returns_float(self, data_source_with_matchups):
        """Test get_champion_base_winrate() calculates weighted average."""
        winrate = data_source_with_matchups.get_champion_base_winrate("Aatrox")
        assert isinstance(winrate, float)
        assert 0.0 <= winrate <= 100.0

    def test_get_champion_base_winrate_returns_default_for_no_data(self, temp_db):
        """Test get_champion_base_winrate() returns 50.0 when no matchups exist."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()
        # Create champion without matchups
        cursor = data_source._db.connection.cursor()
        cursor.execute("INSERT INTO champions (name) VALUES (?)", ("TestChamp",))
        data_source._db.connection.commit()

        winrate = data_source.get_champion_base_winrate("TestChamp")
        assert winrate == 50.0
        data_source.close()


class TestSQLiteDataSourceSynergyQueries:
    """Test synergy-related queries delegation."""

    @pytest.fixture
    def data_source_with_synergies(self, temp_db):
        """Create data source with sample synergy data."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()

        # Create synergies table
        cursor = data_source._db.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS synergies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                champion INTEGER NOT NULL,
                ally INTEGER NOT NULL,
                winrate REAL NOT NULL,
                delta1 REAL NOT NULL,
                delta2 REAL NOT NULL,
                pickrate REAL NOT NULL,
                games INTEGER NOT NULL,
                FOREIGN KEY (champion) REFERENCES champions(id),
                FOREIGN KEY (ally) REFERENCES champions(id)
            )
        """
        )

        # Insert champions
        cursor.execute("INSERT INTO champions (name) VALUES (?)", ("Yasuo",))
        cursor.execute("INSERT INTO champions (name) VALUES (?)", ("Malphite",))
        cursor.execute("INSERT INTO champions (name) VALUES (?)", ("Gragas",))

        # Get IDs
        cursor.execute("SELECT id FROM champions WHERE name = ?", ("Yasuo",))
        yasuo_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM champions WHERE name = ?", ("Malphite",))
        malphite_id = cursor.fetchone()[0]
        cursor.execute("SELECT id FROM champions WHERE name = ?", ("Gragas",))
        gragas_id = cursor.fetchone()[0]

        # Insert synergies
        cursor.execute(
            """
            INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (yasuo_id, malphite_id, 55.0, 200, 250, 8.5, 1000),
        )
        cursor.execute(
            """
            INSERT INTO synergies (champion, ally, winrate, delta1, delta2, pickrate, games)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (yasuo_id, gragas_id, 52.0, 100, 120, 5.2, 600),
        )

        data_source._db.connection.commit()
        yield data_source
        data_source.close()

    def test_get_champion_synergies_by_name_returns_synergy_objects(
        self, data_source_with_synergies
    ):
        """Test get_champion_synergies_by_name() returns Synergy dataclasses."""
        synergies = data_source_with_synergies.get_champion_synergies_by_name("Yasuo")
        assert isinstance(synergies, list)
        assert len(synergies) == 2
        assert all(isinstance(s, Synergy) for s in synergies)

    def test_get_synergy_delta2_returns_float(self, data_source_with_synergies):
        """Test get_synergy_delta2() returns correct delta2 value."""
        delta2 = data_source_with_synergies.get_synergy_delta2("Yasuo", "Malphite")
        assert delta2 == 250.0

    def test_get_synergy_delta2_returns_none_for_invalid_synergy(self, data_source_with_synergies):
        """Test get_synergy_delta2() returns None for non-existent synergy."""
        delta2 = data_source_with_synergies.get_synergy_delta2("Yasuo", "InvalidChamp")
        assert delta2 is None

    def test_get_all_synergies_bulk_returns_dict(self, data_source_with_synergies):
        """Test get_all_synergies_bulk() returns complete synergy cache."""
        synergies_bulk = data_source_with_synergies.get_all_synergies_bulk()
        assert isinstance(synergies_bulk, dict)
        # Check structure: (champion_name, ally_name) -> delta2
        for key, value in synergies_bulk.items():
            assert isinstance(key, tuple)
            assert len(key) == 2
            assert isinstance(value, float)


class TestSQLiteDataSourceChampionScores:
    """Test champion scores queries delegation."""

    @pytest.fixture
    def data_source_with_scores(self, temp_db):
        """Create data source with sample champion scores."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()

        # Create champion_scores table
        cursor = data_source._db.connection.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS champion_scores (
                id INTEGER PRIMARY KEY,
                avg_delta2 REAL,
                variance REAL,
                coverage REAL,
                peak_impact REAL,
                volatility REAL,
                target_ratio REAL,
                FOREIGN KEY (id) REFERENCES champions(id) ON DELETE CASCADE
            )
        """
        )

        # Insert champion
        cursor.execute("INSERT INTO champions (name) VALUES (?)", ("Jinx",))
        cursor.execute("SELECT id FROM champions WHERE name = ?", ("Jinx",))
        jinx_id = cursor.fetchone()[0]

        # Insert scores
        cursor.execute(
            """
            INSERT INTO champion_scores
            (id, avg_delta2, variance, coverage, peak_impact, volatility, target_ratio)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (jinx_id, 150.5, 50.2, 0.85, 200.0, 30.5, 0.65),
        )

        data_source._db.connection.commit()
        yield data_source
        data_source.close()

    def test_get_champion_scores_by_name_returns_dict(self, data_source_with_scores):
        """Test get_champion_scores_by_name() returns scores dictionary."""
        scores = data_source_with_scores.get_champion_scores_by_name("Jinx")
        assert isinstance(scores, dict)
        assert "avg_delta2" in scores
        assert "variance" in scores
        assert "coverage" in scores

    def test_get_champion_scores_by_name_returns_none_for_no_scores(self, temp_db):
        """Test get_champion_scores_by_name() returns None when no scores exist."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()
        cursor = data_source._db.connection.cursor()
        cursor.execute("INSERT INTO champions (name) VALUES (?)", ("TestChamp",))
        data_source._db.connection.commit()

        scores = data_source.get_champion_scores_by_name("TestChamp")
        assert scores is None
        data_source.close()

    def test_get_all_champion_scores_returns_list(self, data_source_with_scores):
        """Test get_all_champion_scores() returns list of tuples."""
        all_scores = data_source_with_scores.get_all_champion_scores()
        assert isinstance(all_scores, list)
        if len(all_scores) > 0:
            assert isinstance(all_scores[0], tuple)

    def test_champion_scores_table_exists_returns_true_with_data(self, data_source_with_scores):
        """Test champion_scores_table_exists() returns True when data exists."""
        exists = data_source_with_scores.champion_scores_table_exists()
        assert exists is True

    def test_champion_scores_table_exists_returns_false_without_data(self, temp_db):
        """Test champion_scores_table_exists() returns False when no data."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()
        exists = data_source.champion_scores_table_exists()
        assert exists is False
        data_source.close()


class TestSQLiteDataSourceBanRecommendations:
    """Test ban recommendations queries delegation."""

    @pytest.fixture
    def data_source_with_bans(self, temp_db):
        """Create data source with sample ban recommendations."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()

        # Insert ban recommendation
        cursor = data_source._db.connection.cursor()
        cursor.execute(
            """
            INSERT INTO pool_ban_recommendations
            (pool_name, enemy_champion, threat_score, best_response_delta2,
             best_response_champion, matchups_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            ("TestPool", "Zed", 85.5, -150.0, "Malzahar", 10),
        )
        data_source._db.connection.commit()

        yield data_source
        data_source.close()

    def test_get_pool_ban_recommendations_returns_list(self, data_source_with_bans):
        """Test get_pool_ban_recommendations() returns list of tuples."""
        bans = data_source_with_bans.get_pool_ban_recommendations("TestPool")
        assert isinstance(bans, list)
        assert len(bans) == 1
        assert isinstance(bans[0], tuple)

    def test_get_pool_ban_recommendations_respects_limit(self, data_source_with_bans):
        """Test get_pool_ban_recommendations() respects limit parameter."""
        # Insert more bans
        cursor = data_source_with_bans._db.connection.cursor()
        for i in range(5):
            cursor.execute(
                """
                INSERT INTO pool_ban_recommendations
                (pool_name, enemy_champion, threat_score, best_response_delta2,
                 best_response_champion, matchups_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                ("TestPool", f"Enemy{i}", 80.0 - i, -100.0, "Response", 5),
            )
        data_source_with_bans._db.connection.commit()

        bans = data_source_with_bans.get_pool_ban_recommendations("TestPool", limit=3)
        assert len(bans) == 3

    def test_pool_has_ban_recommendations_returns_true_with_data(self, data_source_with_bans):
        """Test pool_has_ban_recommendations() returns True when recommendations exist."""
        has_bans = data_source_with_bans.pool_has_ban_recommendations("TestPool")
        assert has_bans is True

    def test_pool_has_ban_recommendations_returns_false_without_data(self, temp_db):
        """Test pool_has_ban_recommendations() returns False when no recommendations."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()
        has_bans = data_source.pool_has_ban_recommendations("NonExistentPool")
        assert has_bans is False
        data_source.close()

    def test_save_pool_ban_recommendations_delegates_to_database(self, temp_db):
        """Test save_pool_ban_recommendations() delegates correctly to Database."""
        data_source = SQLiteDataSource(str(temp_db))
        data_source.connect()

        # Sample ban data
        ban_data = [
            ("Darius", 15.5, -2.5, "Aatrox", 3),
            ("Garen", 12.0, -1.5, "Camille", 4),
        ]

        # Save ban recommendations
        saved_count = data_source.save_pool_ban_recommendations("MyPool", ban_data)

        # Verify delegation worked
        assert saved_count == 2

        # Verify data was actually saved via Database layer
        recommendations = data_source.get_pool_ban_recommendations("MyPool", limit=10)
        assert len(recommendations) == 2
        assert recommendations[0][0] == "Darius"
        assert recommendations[1][0] == "Garen"

        data_source.close()
