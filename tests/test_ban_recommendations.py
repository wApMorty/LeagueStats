"""
Unit tests for ban recommendations system (pre-calculated and real-time).

Tests cover:
- Pre-calculation of ban recommendations for custom pools
- Database storage and retrieval of ban recommendations
- Real-time calculation fallback
- Integration with draft monitor
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from src.assistant import Assistant
from src.db import Database


class TestBanRecommendationsDatabase:
    """Test database methods for ban recommendations."""

    def test_init_pool_ban_recommendations_table(self, db):
        """Test creation of pool_ban_recommendations table."""
        # The table should be created successfully
        db.init_pool_ban_recommendations_table()

        # Verify table exists by trying to query it
        cursor = db.connection.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pool_ban_recommendations'"
        )
        result = cursor.fetchone()

        assert result is not None
        assert result[0] == "pool_ban_recommendations"

    def test_save_pool_ban_recommendations(self, db):
        """Test saving ban recommendations for a pool."""
        db.init_pool_ban_recommendations_table()

        # Sample ban data
        ban_data = [
            ("Darius", 15.5, -2.5, "Aatrox", 3),
            ("Garen", 12.0, -1.5, "Camille", 4),
            ("Malphite", 10.5, -1.0, "Fiora", 2),
        ]

        saved = db.save_pool_ban_recommendations("TestPool", ban_data)

        assert saved == 3

    def test_get_pool_ban_recommendations(self, db):
        """Test retrieving ban recommendations for a pool."""
        db.init_pool_ban_recommendations_table()

        # Save test data
        ban_data = [
            ("Darius", 15.5, -2.5, "Aatrox", 3),
            ("Garen", 12.0, -1.5, "Camille", 4),
            ("Malphite", 10.5, -1.0, "Fiora", 2),
        ]
        db.save_pool_ban_recommendations("TestPool", ban_data)

        # Retrieve recommendations
        recommendations = db.get_pool_ban_recommendations("TestPool", limit=3)

        assert len(recommendations) == 3
        # Should be sorted by threat_score DESC
        assert recommendations[0][0] == "Darius"  # enemy_champion
        assert recommendations[0][1] == 15.5  # threat_score
        assert recommendations[1][0] == "Garen"
        assert recommendations[2][0] == "Malphite"

    def test_get_pool_ban_recommendations_with_limit(self, db):
        """Test retrieving limited number of ban recommendations."""
        db.init_pool_ban_recommendations_table()

        ban_data = [
            ("Darius", 15.5, -2.5, "Aatrox", 3),
            ("Garen", 12.0, -1.5, "Camille", 4),
            ("Malphite", 10.5, -1.0, "Fiora", 2),
        ]
        db.save_pool_ban_recommendations("TestPool", ban_data)

        # Get only top 2
        recommendations = db.get_pool_ban_recommendations("TestPool", limit=2)

        assert len(recommendations) == 2
        assert recommendations[0][0] == "Darius"
        assert recommendations[1][0] == "Garen"

    def test_pool_has_ban_recommendations(self, db):
        """Test checking if pool has ban recommendations."""
        db.init_pool_ban_recommendations_table()

        # Initially should be False
        assert db.pool_has_ban_recommendations("TestPool") is False

        # Save data
        ban_data = [("Darius", 15.5, -2.5, "Aatrox", 3)]
        db.save_pool_ban_recommendations("TestPool", ban_data)

        # Now should be True
        assert db.pool_has_ban_recommendations("TestPool") is True

    def test_clear_pool_ban_recommendations_specific_pool(self, db):
        """Test clearing ban recommendations for specific pool."""
        db.init_pool_ban_recommendations_table()

        # Save data for two pools
        ban_data1 = [("Darius", 15.5, -2.5, "Aatrox", 3)]
        ban_data2 = [("Garen", 12.0, -1.5, "Camille", 4)]

        db.save_pool_ban_recommendations("Pool1", ban_data1)
        db.save_pool_ban_recommendations("Pool2", ban_data2)

        # Clear only Pool1
        deleted = db.clear_pool_ban_recommendations("Pool1")

        assert deleted == 1
        assert db.pool_has_ban_recommendations("Pool1") is False
        assert db.pool_has_ban_recommendations("Pool2") is True

    def test_clear_pool_ban_recommendations_all(self, db):
        """Test clearing all ban recommendations."""
        db.init_pool_ban_recommendations_table()

        # Save data for two pools
        ban_data1 = [("Darius", 15.5, -2.5, "Aatrox", 3)]
        ban_data2 = [("Garen", 12.0, -1.5, "Camille", 4)]

        db.save_pool_ban_recommendations("Pool1", ban_data1)
        db.save_pool_ban_recommendations("Pool2", ban_data2)

        # Clear all
        deleted = db.clear_pool_ban_recommendations(None)

        assert deleted == 2
        assert db.pool_has_ban_recommendations("Pool1") is False
        assert db.pool_has_ban_recommendations("Pool2") is False

    def test_save_pool_ban_recommendations_replaces_existing(self, db):
        """Test that saving ban recommendations replaces existing data."""
        db.init_pool_ban_recommendations_table()

        # Save initial data
        ban_data1 = [("Darius", 15.5, -2.5, "Aatrox", 3)]
        db.save_pool_ban_recommendations("TestPool", ban_data1)

        # Save new data for same pool
        ban_data2 = [("Garen", 20.0, -3.0, "Camille", 5), ("Malphite", 18.0, -2.8, "Fiora", 4)]
        db.save_pool_ban_recommendations("TestPool", ban_data2)

        # Verify old data is replaced
        recommendations = db.get_pool_ban_recommendations("TestPool", limit=10)

        assert len(recommendations) == 2
        assert recommendations[0][0] == "Garen"
        assert recommendations[1][0] == "Malphite"
        # Old "Darius" should be gone


class TestBanRecommendationsAssistant:
    """Test Assistant methods for ban recommendations."""

    def test_precalculate_pool_bans_empty_pool(self, db):
        """Test pre-calculating bans with empty pool."""
        assistant = Assistant(verbose=False)
        assistant.db = db

        result = assistant.precalculate_pool_bans("EmptyPool", [])

        assert result is False

    def test_precalculate_pool_bans_with_valid_pool(self, db, insert_matchup):
        """Test pre-calculating bans for valid champion pool."""
        # Setup test data
        insert_matchup("Aatrox", "Darius", 48.5, -150, -2.5, 8.5, 1500)
        insert_matchup("Aatrox", "Garen", 51.2, 120, 1.2, 6.5, 1200)
        insert_matchup("Camille", "Darius", 49.0, -100, -1.5, 8.5, 1400)
        insert_matchup("Camille", "Garen", 52.0, 200, 2.0, 6.5, 1100)

        db.init_pool_ban_recommendations_table()

        assistant = Assistant(verbose=False)
        assistant.db = db

        # Pre-calculate for pool
        pool = ["Aatrox", "Camille"]
        result = assistant.precalculate_pool_bans("TestPool", pool)

        assert result is True
        assert db.pool_has_ban_recommendations("TestPool")

    def test_precalculate_all_custom_pool_bans_no_pools(self, db):
        """Test pre-calculating bans when no custom pools exist."""
        assistant = Assistant(verbose=False)
        assistant.db = db

        # Mock pool manager to return no custom pools
        with patch("src.pool_manager.PoolManager") as mock_pool_manager:
            mock_instance = Mock()
            mock_instance.get_all_pools.return_value = {}
            mock_pool_manager.return_value = mock_instance

            results = assistant.precalculate_all_custom_pool_bans()

            assert results == {}

    def test_precalculate_all_custom_pool_bans_with_custom_pools(self, db, insert_matchup):
        """Test pre-calculating bans for all custom pools."""
        # Setup test data
        insert_matchup("Aatrox", "Darius", 48.5, -150, -2.5, 8.5, 1500)
        insert_matchup("Camille", "Darius", 49.0, -100, -1.5, 8.5, 1400)

        db.init_pool_ban_recommendations_table()

        assistant = Assistant(verbose=False)
        assistant.db = db

        # Mock pool manager with custom pool
        with patch("src.pool_manager.PoolManager") as mock_pool_manager:
            mock_pool = Mock()
            mock_pool.champions = ["Aatrox", "Camille"]
            mock_pool.created_by = "user"

            mock_instance = Mock()
            mock_instance.get_all_pools.return_value = {"MyCustomPool": mock_pool}
            mock_pool_manager.return_value = mock_instance

            results = assistant.precalculate_all_custom_pool_bans()

            assert "MyCustomPool" in results
            assert results["MyCustomPool"] > 0

    def test_precalculate_all_custom_pool_bans_skips_system_pools(self, db):
        """Test that system pools are skipped during pre-calculation."""
        assistant = Assistant(verbose=False)
        assistant.db = db

        # Mock pool manager with system and custom pools
        with patch("src.pool_manager.PoolManager") as mock_pool_manager:
            system_pool = Mock()
            system_pool.champions = ["Aatrox", "Camille"]
            system_pool.created_by = "system"

            custom_pool = Mock()
            custom_pool.champions = ["Fiora", "Jax"]
            custom_pool.created_by = "user"

            mock_instance = Mock()
            mock_instance.get_all_pools.return_value = {
                "SystemPool": system_pool,
                "CustomPool": custom_pool,
            }
            mock_pool_manager.return_value = mock_instance

            results = assistant.precalculate_all_custom_pool_bans()

            # Only custom pool should be in results
            assert "SystemPool" not in results
            assert "CustomPool" in results or results == {"CustomPool": 0}


class TestBanRecommendationsIntegration:
    """Integration tests for ban recommendations."""

    def test_get_ban_recommendations_real_time(self, db, insert_matchup):
        """Test real-time ban recommendation calculation."""
        # Setup matchup data
        insert_matchup("Aatrox", "Darius", 48.5, -150, -2.5, 8.5, 1500)
        insert_matchup("Aatrox", "Garen", 51.2, 120, 1.2, 6.5, 1200)
        insert_matchup("Camille", "Darius", 49.0, -100, -1.5, 8.5, 1400)
        insert_matchup("Camille", "Garen", 52.0, 200, 2.0, 6.5, 1100)

        assistant = Assistant(verbose=False)
        assistant.db = db

        pool = ["Aatrox", "Camille"]
        recommendations = assistant.get_ban_recommendations(pool, num_bans=2)

        # Should get recommendations (Darius should be top threat)
        assert len(recommendations) > 0
        assert recommendations[0][0] == "Darius"  # Champion with worst matchups

    def test_ban_recommendations_with_pre_calculated_data(self, db, insert_matchup):
        """Test using pre-calculated ban recommendations."""
        # Setup matchup data
        insert_matchup("Aatrox", "Darius", 48.5, -150, -2.5, 8.5, 1500)
        insert_matchup("Camille", "Darius", 49.0, -100, -1.5, 8.5, 1400)

        db.init_pool_ban_recommendations_table()

        assistant = Assistant(verbose=False)
        assistant.db = db

        # Pre-calculate bans
        pool = ["Aatrox", "Camille"]
        assistant.precalculate_pool_bans("TestPool", pool)

        # Retrieve pre-calculated recommendations
        recommendations = db.get_pool_ban_recommendations("TestPool", limit=3)

        assert len(recommendations) > 0
        assert recommendations[0][0] == "Darius"

    def test_ban_recommendations_format_compatibility(self, db, insert_matchup):
        """Test that pre-calculated and real-time formats are compatible."""
        # Setup data
        insert_matchup("Aatrox", "Darius", 48.5, -150, -2.5, 8.5, 1500)

        db.init_pool_ban_recommendations_table()

        assistant = Assistant(verbose=False)
        assistant.db = db

        pool = ["Aatrox"]

        # Get real-time recommendations (3 values: enemy, threat, delta2)
        real_time = assistant.get_ban_recommendations(pool, num_bans=1)

        # Pre-calculate (5 values: enemy, threat, delta2, response_champ, count)
        assistant.precalculate_pool_bans("TestPool", pool)
        pre_calculated = db.get_pool_ban_recommendations("TestPool", limit=1)

        # Both should have enemy and threat_score in first 2 positions
        assert real_time[0][0] == pre_calculated[0][0]  # enemy name
        assert abs(real_time[0][1] - pre_calculated[0][1]) < 0.1  # threat score (close enough)


class TestBanRecommendationsLaneAware:
    """Regression (audit 2026-09-04): ban recommendations blended every lane
    a champion has ever played into one threat score -- same bug class as
    the Live Coach / Tournament Coach / tier list lane fixes of the same
    day, never applied to bans."""

    def test_get_ban_recommendations_is_filtered_by_lane(self, db, insert_matchup):
        insert_matchup("Aatrox", "Darius", 40.0, -300, -5.0, 8.5, 1500, lane="top")
        insert_matchup("Aatrox", "Darius", 60.0, 300, 5.0, 8.5, 1500, lane="jungle")

        assistant = Assistant(verbose=False)
        assistant.db = db

        top_recs = assistant.get_ban_recommendations(["Aatrox"], num_bans=1, lane="top")
        jungle_recs = assistant.get_ban_recommendations(["Aatrox"], num_bans=1, lane="jungle")

        assert top_recs[0][2] == pytest.approx(-5.0)  # best_response_delta2
        assert jungle_recs[0][2] == pytest.approx(5.0)
        # base_threat = -best_response_delta2: worse matchup -> higher threat.
        assert top_recs[0][1] > jungle_recs[0][1]

    def test_get_ban_recommendations_without_lane_is_unfiltered(self, db, insert_matchup):
        """None (default) preserves the pre-fix all-lanes behaviour."""
        insert_matchup("Aatrox", "Darius", 40.0, -300, -5.0, 8.5, 1500, lane="top")

        assistant = Assistant(verbose=False)
        assistant.db = db

        recs = assistant.get_ban_recommendations(["Aatrox"], num_bans=1)

        assert recs[0][2] == pytest.approx(-5.0)

    def test_precalculate_pool_bans_is_filtered_by_lane(self, db, insert_matchup):
        insert_matchup("Aatrox", "Darius", 40.0, -300, -5.0, 8.5, 1500, lane="top")
        insert_matchup("Aatrox", "Darius", 60.0, 300, 5.0, 8.5, 1500, lane="jungle")
        db.init_pool_ban_recommendations_table()

        assistant = Assistant(verbose=False)
        assistant.db = db

        assistant.precalculate_pool_bans("TopPool", ["Aatrox"], lane="top")
        assistant.precalculate_pool_bans("JunglePool", ["Aatrox"], lane="jungle")

        top_saved = db.get_pool_ban_recommendations("TopPool", limit=1)[0]
        jungle_saved = db.get_pool_ban_recommendations("JunglePool", limit=1)[0]

        assert top_saved[2] == pytest.approx(-5.0)
        assert jungle_saved[2] == pytest.approx(5.0)

    def test_precalculate_all_custom_pool_bans_resolves_pool_role_to_lane(self, db, insert_matchup):
        """precalculate_all_custom_pool_bans must pass each pool's own lane
        (pool_manager.pool_role_to_lane(pool.role)) down to
        precalculate_pool_bans, not blend every lane the champion has ever
        played."""
        insert_matchup("Aatrox", "Darius", 40.0, -300, -5.0, 8.5, 1500, lane="top")
        insert_matchup("Aatrox", "Darius", 60.0, 300, 5.0, 8.5, 1500, lane="jungle")
        db.init_pool_ban_recommendations_table()

        assistant = Assistant(verbose=False)
        assistant.db = db

        with patch("src.pool_manager.PoolManager") as mock_pool_manager:
            top_pool = Mock()
            top_pool.champions = ["Aatrox"]
            top_pool.created_by = "user"
            top_pool.role = "top"

            mock_instance = Mock()
            mock_instance.get_all_pools.return_value = {"TopPool": top_pool}
            mock_pool_manager.return_value = mock_instance

            assistant.precalculate_all_custom_pool_bans()

        saved = db.get_pool_ban_recommendations("TopPool", limit=1)[0]
        assert saved[2] == pytest.approx(-5.0)  # the top-lane row, not the jungle one

    def test_precalculate_all_custom_pool_bans_custom_role_is_unfiltered(self, db, insert_matchup):
        """role="custom" (multi-lane pool) has no single lane ->
        pool_role_to_lane returns None -> all-lanes behaviour preserved."""
        insert_matchup("Aatrox", "Darius", 40.0, -300, -5.0, 8.5, 1500, lane="top")
        db.init_pool_ban_recommendations_table()

        assistant = Assistant(verbose=False)
        assistant.db = db

        with patch("src.pool_manager.PoolManager") as mock_pool_manager:
            custom_pool = Mock()
            custom_pool.champions = ["Aatrox"]
            custom_pool.created_by = "user"
            custom_pool.role = "custom"

            mock_instance = Mock()
            mock_instance.get_all_pools.return_value = {"CustomPool": custom_pool}
            mock_pool_manager.return_value = mock_instance

            assistant.precalculate_all_custom_pool_bans()

        saved = db.get_pool_ban_recommendations("CustomPool", limit=1)[0]
        assert saved[2] == pytest.approx(-5.0)


class TestBanRecommendationsEdgeCases:
    """Test edge cases for ban recommendations."""

    def test_precalculate_with_insufficient_matchup_data(self, db):
        """Test pre-calculating bans when champions have insufficient data."""
        db.init_pool_ban_recommendations_table()

        assistant = Assistant(verbose=False)
        assistant.db = db

        # Pool with champions that don't exist in DB
        pool = ["NonExistentChampion1", "NonExistentChampion2"]
        result = assistant.precalculate_pool_bans("TestPool", pool)

        # Should return False or save empty recommendations
        assert result is False or db.get_pool_ban_recommendations("TestPool") == []

    def test_get_ban_recommendations_empty_pool(self, db):
        """Test getting ban recommendations with empty pool."""
        assistant = Assistant(verbose=False)
        assistant.db = db

        recommendations = assistant.get_ban_recommendations([], num_bans=3)

        assert recommendations == []

    def test_save_ban_recommendations_with_empty_data(self, db):
        """Test saving empty ban data."""
        db.init_pool_ban_recommendations_table()

        saved = db.save_pool_ban_recommendations("TestPool", [])

        assert saved == 0
