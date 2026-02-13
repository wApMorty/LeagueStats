"""
Tests for HybridDataSource - PostgreSQL with SQLite fallback.

This test suite verifies the hybrid data source correctly implements:
- PostgreSQL-first strategy with SQLite fallback
- Mode switching (postgresql_only, sqlite_only, hybrid)
- Graceful degradation on PostgreSQL failures
- Warning logs when fallback occurs

Author: @pj35
Created: 2026-02-06
Sprint: 2 - API Integration (Adapter Pattern Implementation)
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import logging

from src.hybrid_data_source import HybridDataSource
from src.models import Matchup, MatchupDraft, Synergy


@pytest.fixture
def mock_postgres_source():
    """Mock PostgreSQLDataSource for testing."""
    with patch("src.hybrid_data_source.PostgreSQLDataSource") as mock_postgres_class:
        mock_postgres = Mock()
        mock_postgres_class.return_value = mock_postgres
        yield mock_postgres


@pytest.fixture
def mock_sqlite_source():
    """Mock SQLiteDataSource for testing."""
    with patch("src.hybrid_data_source.SQLiteDataSource") as mock_sqlite_class:
        mock_sqlite = Mock()
        mock_sqlite_class.return_value = mock_sqlite
        yield mock_sqlite


@pytest.fixture
def hybrid_source_hybrid_mode(mock_postgres_source, mock_sqlite_source):
    """Create HybridDataSource in hybrid mode."""
    with patch("src.hybrid_data_source.api_config") as mock_config:
        mock_config.MODE = "hybrid"
        mock_config.ENABLED = True
        data_source = HybridDataSource()
        data_source.connect()
        return data_source


@pytest.fixture
def hybrid_source_postgresql_only(mock_postgres_source):
    """Create HybridDataSource in postgresql_only mode."""
    with patch("src.hybrid_data_source.api_config") as mock_config:
        mock_config.MODE = "postgresql_only"
        mock_config.ENABLED = True
        data_source = HybridDataSource()
        data_source.connect()
        return data_source


@pytest.fixture
def hybrid_source_sqlite_only(mock_sqlite_source):
    """Create HybridDataSource in sqlite_only mode."""
    with patch("src.hybrid_data_source.api_config") as mock_config:
        mock_config.MODE = "sqlite_only"
        mock_config.ENABLED = True
        data_source = HybridDataSource()
        data_source.connect()
        return data_source


class TestHybridDataSourceModes:
    """Test different operation modes (hybrid, postgresql_only, sqlite_only)."""

    def test_hybrid_mode_initializes_both_sources(self, mock_postgres_source, mock_sqlite_source):
        """Test that hybrid mode initializes both PostgreSQL and SQLite sources."""
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "hybrid"
            mock_config.ENABLED = True

            data_source = HybridDataSource()

            assert data_source.postgres_source is not None
            assert data_source.sqlite_source is not None

    def test_postgresql_only_mode_initializes_only_postgres_source(self, mock_postgres_source):
        """Test that postgresql_only mode initializes only PostgreSQL source."""
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "postgresql_only"
            mock_config.ENABLED = True

            data_source = HybridDataSource()

            assert data_source.postgres_source is not None
            assert data_source.sqlite_source is None

    def test_sqlite_only_mode_initializes_only_sqlite_source(self, mock_sqlite_source):
        """Test that sqlite_only mode initializes only SQLite source."""
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "sqlite_only"
            mock_config.ENABLED = True

            data_source = HybridDataSource()

            assert data_source.postgres_source is None
            assert data_source.sqlite_source is not None


class TestHybridDataSourceFallback:
    """Test fallback behavior in hybrid mode."""

    def test_get_champion_id_uses_postgres_first(self, hybrid_source_hybrid_mode):
        """Test that PostgreSQL is tried first in hybrid mode."""
        hybrid_source_hybrid_mode.postgres_source.get_champion_id.return_value = 42

        champion_id = hybrid_source_hybrid_mode.get_champion_id("Jinx")

        assert champion_id == 42
        hybrid_source_hybrid_mode.postgres_source.get_champion_id.assert_called_once_with("Jinx")
        # SQLite should not be called if PostgreSQL succeeds
        hybrid_source_hybrid_mode.sqlite_source.get_champion_id.assert_not_called()

    def test_get_champion_id_falls_back_to_sqlite_on_postgres_error(
        self, hybrid_source_hybrid_mode
    ):
        """Test that SQLite is used when PostgreSQL fails."""
        # Simulate PostgreSQL failure
        hybrid_source_hybrid_mode.postgres_source.get_champion_id.side_effect = Exception(
            "PostgreSQL timeout"
        )
        hybrid_source_hybrid_mode.sqlite_source.get_champion_id.return_value = 42

        champion_id = hybrid_source_hybrid_mode.get_champion_id("Jinx")

        assert champion_id == 42
        # Both sources should be tried
        hybrid_source_hybrid_mode.postgres_source.get_champion_id.assert_called_once_with("Jinx")
        hybrid_source_hybrid_mode.sqlite_source.get_champion_id.assert_called_once_with("Jinx")

    def test_fallback_logs_warning(self, hybrid_source_hybrid_mode, caplog):
        """Test that fallback logs a warning message."""
        hybrid_source_hybrid_mode.postgres_source.get_champion_id.side_effect = Exception(
            "PostgreSQL timeout"
        )
        hybrid_source_hybrid_mode.sqlite_source.get_champion_id.return_value = 42

        with caplog.at_level(logging.WARNING):
            hybrid_source_hybrid_mode.get_champion_id("Jinx")

        # Check that warning was logged
        assert any("PostgreSQL call failed" in record.message for record in caplog.records)


class TestHybridDataSourcePostgreSQLOnly:
    """Test postgresql_only mode behavior."""

    def test_postgresql_only_mode_raises_on_postgres_error(self, hybrid_source_postgresql_only):
        """Test that postgresql_only mode raises exception when PostgreSQL fails (no fallback)."""
        hybrid_source_postgresql_only.postgres_source.get_champion_id.side_effect = Exception(
            "PostgreSQL timeout"
        )

        with pytest.raises(Exception, match="PostgreSQL timeout"):
            hybrid_source_postgresql_only.get_champion_id("Jinx")


class TestHybridDataSourceSQLiteOnly:
    """Test sqlite_only mode behavior."""

    def test_sqlite_only_mode_uses_sqlite_directly(self, hybrid_source_sqlite_only):
        """Test that sqlite_only mode uses SQLite directly without trying API."""
        hybrid_source_sqlite_only.sqlite_source.get_champion_id.return_value = 42

        champion_id = hybrid_source_sqlite_only.get_champion_id("Jinx")

        assert champion_id == 42
        hybrid_source_sqlite_only.sqlite_source.get_champion_id.assert_called_once_with("Jinx")


class TestHybridDataSourceChampionQueries:
    """Test champion-related queries with hybrid fallback."""

    def test_get_champion_by_id_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_champion_by_id() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_champion_by_id.side_effect = Exception(
            "Network error"
        )
        hybrid_source_hybrid_mode.sqlite_source.get_champion_by_id.return_value = "Jinx"

        champion_name = hybrid_source_hybrid_mode.get_champion_by_id(42)

        assert champion_name == "Jinx"

    def test_get_all_champion_names_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_all_champion_names() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_all_champion_names.side_effect = Exception(
            "Network error"
        )
        hybrid_source_hybrid_mode.sqlite_source.get_all_champion_names.return_value = {
            1: "Aatrox",
            42: "Jinx",
        }

        names = hybrid_source_hybrid_mode.get_all_champion_names()

        assert names == {1: "Aatrox", 42: "Jinx"}

    def test_build_champion_cache_with_fallback(self, hybrid_source_hybrid_mode):
        """Test build_champion_cache() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.build_champion_cache.side_effect = Exception(
            "Network error"
        )
        hybrid_source_hybrid_mode.sqlite_source.build_champion_cache.return_value = {
            "Jinx": 42,
            "jinx": 42,
        }

        cache = hybrid_source_hybrid_mode.build_champion_cache()

        assert cache == {"Jinx": 42, "jinx": 42}


class TestHybridDataSourceMatchupQueries:
    """Test matchup-related queries with hybrid fallback."""

    def test_get_champion_matchups_by_name_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_champion_matchups_by_name() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_champion_matchups_by_name.side_effect = (
            Exception("Network error")
        )
        expected_matchups = [
            Matchup("Darius", 48.5, -150, -200, 8.5, 1500),
            Matchup("Garen", 52.0, 100, 150, 12.3, 2000),
        ]
        hybrid_source_hybrid_mode.sqlite_source.get_champion_matchups_by_name.return_value = (
            expected_matchups
        )

        matchups = hybrid_source_hybrid_mode.get_champion_matchups_by_name("Aatrox")

        assert matchups == expected_matchups

    def test_get_champion_matchups_for_draft_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_champion_matchups_for_draft() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_champion_matchups_for_draft.side_effect = (
            Exception("Network error")
        )
        expected_matchups = [MatchupDraft("Darius", -200, 8.5, 1500)]
        hybrid_source_hybrid_mode.sqlite_source.get_champion_matchups_for_draft.return_value = (
            expected_matchups
        )

        matchups = hybrid_source_hybrid_mode.get_champion_matchups_for_draft("Aatrox")

        assert matchups == expected_matchups

    def test_get_matchup_delta2_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_matchup_delta2() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_matchup_delta2.side_effect = Exception(
            "Network error"
        )
        hybrid_source_hybrid_mode.sqlite_source.get_matchup_delta2.return_value = -200.0

        delta2 = hybrid_source_hybrid_mode.get_matchup_delta2("Aatrox", "Darius")

        assert delta2 == -200.0

    def test_get_all_matchups_bulk_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_all_matchups_bulk() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_all_matchups_bulk.side_effect = Exception(
            "Network error"
        )
        expected_cache = {("aatrox", "darius"): -200.0, ("aatrox", "garen"): 150.0}
        hybrid_source_hybrid_mode.sqlite_source.get_all_matchups_bulk.return_value = expected_cache

        matchups_bulk = hybrid_source_hybrid_mode.get_all_matchups_bulk()

        assert matchups_bulk == expected_cache

    def test_get_champion_base_winrate_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_champion_base_winrate() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_champion_base_winrate.side_effect = Exception(
            "Network error"
        )
        hybrid_source_hybrid_mode.sqlite_source.get_champion_base_winrate.return_value = 50.5

        winrate = hybrid_source_hybrid_mode.get_champion_base_winrate("Aatrox")

        assert winrate == 50.5


class TestHybridDataSourceSynergyQueries:
    """Test synergy-related queries with hybrid fallback."""

    def test_get_champion_synergies_by_name_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_champion_synergies_by_name() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_champion_synergies_by_name.side_effect = (
            Exception("Network error")
        )
        expected_synergies = [Synergy("Malphite", 55.0, 200, 250, 8.5, 1000)]
        hybrid_source_hybrid_mode.sqlite_source.get_champion_synergies_by_name.return_value = (
            expected_synergies
        )

        synergies = hybrid_source_hybrid_mode.get_champion_synergies_by_name("Yasuo")

        assert synergies == expected_synergies

    def test_get_synergy_delta2_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_synergy_delta2() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_synergy_delta2.side_effect = Exception(
            "Network error"
        )
        hybrid_source_hybrid_mode.sqlite_source.get_synergy_delta2.return_value = 250.0

        delta2 = hybrid_source_hybrid_mode.get_synergy_delta2("Yasuo", "Malphite")

        assert delta2 == 250.0

    def test_get_all_synergies_bulk_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_all_synergies_bulk() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_all_synergies_bulk.side_effect = Exception(
            "Network error"
        )
        expected_cache = {("yasuo", "malphite"): 250.0, ("yasuo", "gragas"): 120.0}
        hybrid_source_hybrid_mode.sqlite_source.get_all_synergies_bulk.return_value = expected_cache

        synergies_bulk = hybrid_source_hybrid_mode.get_all_synergies_bulk()

        assert synergies_bulk == expected_cache


class TestHybridDataSourceChampionScores:
    """Test champion scores queries with hybrid fallback."""

    def test_get_champion_scores_by_name_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_champion_scores_by_name() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_champion_scores_by_name.side_effect = (
            Exception("Network error")
        )
        expected_scores = {
            "avg_delta2": 150.5,
            "variance": 50.2,
            "coverage": 0.85,
        }
        hybrid_source_hybrid_mode.sqlite_source.get_champion_scores_by_name.return_value = (
            expected_scores
        )

        scores = hybrid_source_hybrid_mode.get_champion_scores_by_name("Jinx")

        assert scores == expected_scores

    def test_get_all_champion_scores_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_all_champion_scores() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_all_champion_scores.side_effect = Exception(
            "Network error"
        )
        expected_scores = [("Jinx", 150.5, 50.2, 0.85, 200.0, 30.5, 0.65)]
        hybrid_source_hybrid_mode.sqlite_source.get_all_champion_scores.return_value = (
            expected_scores
        )

        all_scores = hybrid_source_hybrid_mode.get_all_champion_scores()

        assert all_scores == expected_scores

    def test_champion_scores_table_exists_with_fallback(self, hybrid_source_hybrid_mode):
        """Test champion_scores_table_exists() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.champion_scores_table_exists.side_effect = (
            Exception("Network error")
        )
        hybrid_source_hybrid_mode.sqlite_source.champion_scores_table_exists.return_value = True

        exists = hybrid_source_hybrid_mode.champion_scores_table_exists()

        assert exists is True


class TestHybridDataSourceBanRecommendations:
    """Test ban recommendations queries with hybrid fallback."""

    def test_get_pool_ban_recommendations_with_fallback(self, hybrid_source_hybrid_mode):
        """Test get_pool_ban_recommendations() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.get_pool_ban_recommendations.side_effect = (
            Exception("Network error")
        )
        expected_bans = [("Zed", 85.5, -150.0, "Malzahar", 10)]
        hybrid_source_hybrid_mode.sqlite_source.get_pool_ban_recommendations.return_value = (
            expected_bans
        )

        bans = hybrid_source_hybrid_mode.get_pool_ban_recommendations("TestPool")

        assert bans == expected_bans

    def test_pool_has_ban_recommendations_with_fallback(self, hybrid_source_hybrid_mode):
        """Test pool_has_ban_recommendations() falls back to SQLite on PostgreSQL error."""
        hybrid_source_hybrid_mode.postgres_source.pool_has_ban_recommendations.side_effect = (
            Exception("Network error")
        )
        hybrid_source_hybrid_mode.sqlite_source.pool_has_ban_recommendations.return_value = True

        has_bans = hybrid_source_hybrid_mode.pool_has_ban_recommendations("TestPool")

        assert has_bans is True


class TestHybridDataSourceConnectionManagement:
    """Test connection and cleanup."""

    def test_connect_connects_both_sources_in_hybrid_mode(
        self, mock_postgres_source, mock_sqlite_source
    ):
        """Test that connect() connects both PostgreSQL and SQLite sources in hybrid mode."""
        with patch("src.hybrid_data_source.api_config") as mock_config:
            mock_config.MODE = "hybrid"
            mock_config.ENABLED = True

            data_source = HybridDataSource()
            data_source.connect()

            mock_postgres_source.connect.assert_called_once()
            mock_sqlite_source.connect.assert_called_once()

    def test_close_closes_both_sources(self, hybrid_source_hybrid_mode):
        """Test that close() closes both sources."""
        hybrid_source_hybrid_mode.close()

        hybrid_source_hybrid_mode.postgres_source.close.assert_called_once()
        hybrid_source_hybrid_mode.sqlite_source.close.assert_called_once()
