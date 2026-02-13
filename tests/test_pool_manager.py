"""Regression tests for PoolManager ban recalculation in .exe mode."""

import json
import os
import sys
from unittest.mock import Mock, patch, MagicMock, call
import pytest

from src.pool_manager import PoolManager, ChampionPool


class TestPoolManagerBanRecalculation:
    """Tests for ban recalculation behavior in .exe vs dev mode."""

    @patch("src.assistant.Assistant")
    @patch("src.db.Database")
    @patch("builtins.print")
    def test_save_custom_pools_skip_ban_recalc_when_frozen(
        self, mock_print, mock_db_class, mock_assistant_class, tmp_path
    ):
        """
        Regression test: Skip ban recalculation in .exe mode (sys.frozen = True).

        Verifies that when running as PyInstaller executable:
        - Assistant.precalculate_all_custom_pool_bans() is NOT called
        - Log message indicates skip behavior
        - Pool is successfully saved to champion_pools.json
        """
        # GIVEN: PyInstaller mode (sys.frozen = True)
        with patch.object(sys, "frozen", True, create=True):
            # Mock filesystem path for .exe mode
            pools_file = tmp_path / "champion_pools.json"

            with patch("src.pool_manager.get_user_pools_path", return_value=str(pools_file)):
                # Create PoolManager with 1 custom pool
                manager = PoolManager()
                manager.create_pool(
                    name="Test Pool",
                    champions=["Aatrox", "Darius", "Garen"],
                    description="Test pool for regression",
                    role="custom",
                    tags=["test"],
                )

                # Mock Database and Assistant
                mock_db_instance = Mock()
                mock_db_class.return_value = mock_db_instance

                mock_assistant_instance = Mock()
                mock_assistant_instance.precalculate_all_custom_pool_bans.return_value = {
                    "Test Pool": 5
                }
                mock_assistant_class.return_value = mock_assistant_instance

                # WHEN: Save custom pools with recalculate_bans=True
                result = manager.save_custom_pools(recalculate_bans=True)

                # THEN: Save operation succeeds
                assert result is True
                assert pools_file.exists()

                # THEN: Pool data is correctly saved
                with open(pools_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    assert len(data["custom_pools"]) == 1
                    assert data["custom_pools"][0]["name"] == "Test Pool"
                    assert data["custom_pools"][0]["champions"] == [
                        "Aatrox",
                        "Darius",
                        "Garen",
                    ]

                # THEN: precalculate_all_custom_pool_bans() is NOT called (skipped in .exe mode)
                mock_assistant_instance.precalculate_all_custom_pool_bans.assert_not_called()

                # THEN: Log message indicates skip behavior
                print_calls = [str(call_args) for call_args in mock_print.call_args_list]
                skip_log_found = any(
                    "Skipping ban recalculation in .exe mode" in call_str
                    for call_str in print_calls
                )
                assert skip_log_found, (
                    "Expected log message 'Skipping ban recalculation in .exe mode' not found"
                )

    @patch("src.assistant.Assistant")
    @patch("src.db.Database")
    @patch("builtins.print")
    def test_save_custom_pools_recalc_bans_in_dev_mode(
        self, mock_print, mock_db_class, mock_assistant_class, tmp_path
    ):
        """
        Regression test: Normal ban recalculation in dev mode (sys.frozen = False or absent).

        Verifies that when running in development mode:
        - Assistant.precalculate_all_custom_pool_bans() IS called
        - Ban recalculation executes normally
        - Success log message is displayed
        """
        # GIVEN: Development mode (sys.frozen = False or absent)
        # Ensure sys.frozen is False or doesn't exist
        if hasattr(sys, "frozen"):
            with patch.object(sys, "frozen", False, create=True):
                self._run_dev_mode_test(
                    mock_print, mock_db_class, mock_assistant_class, tmp_path
                )
        else:
            # sys.frozen doesn't exist (default dev behavior)
            self._run_dev_mode_test(
                mock_print, mock_db_class, mock_assistant_class, tmp_path
            )

    def _run_dev_mode_test(self, mock_print, mock_db_class, mock_assistant_class, tmp_path):
        """Helper method to run dev mode test logic."""
        # Mock filesystem path for dev mode
        pools_file = tmp_path / "champion_pools.json"

        with patch("src.pool_manager.get_user_pools_path", return_value=str(pools_file)):
            # Create PoolManager with 1 custom pool
            manager = PoolManager()
            manager.create_pool(
                name="Dev Pool",
                champions=["Ahri", "Zed", "Yasuo"],
                description="Pool for dev mode test",
                role="custom",
                tags=["dev"],
            )

            # Mock Database and Assistant
            mock_db_instance = Mock()
            mock_db_class.return_value = mock_db_instance

            mock_assistant_instance = Mock()
            mock_assistant_instance.precalculate_all_custom_pool_bans.return_value = {
                "Dev Pool": 8
            }
            mock_assistant_class.return_value = mock_assistant_instance

            # WHEN: Save custom pools with recalculate_bans=True
            result = manager.save_custom_pools(recalculate_bans=True)

            # THEN: Save operation succeeds
            assert result is True
            assert pools_file.exists()

            # THEN: Pool data is correctly saved
            with open(pools_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                assert len(data["custom_pools"]) == 1
                assert data["custom_pools"][0]["name"] == "Dev Pool"
                assert data["custom_pools"][0]["champions"] == ["Ahri", "Zed", "Yasuo"]

            # THEN: precalculate_all_custom_pool_bans() IS called (normal dev behavior)
            mock_assistant_instance.precalculate_all_custom_pool_bans.assert_called_once()

            # THEN: Database connection was established
            mock_db_class.assert_called_once_with("data/db.db")
            mock_db_instance.connect.assert_called_once()

            # THEN: Success log message is displayed
            print_calls = [str(call_args) for call_args in mock_print.call_args_list]
            success_log_found = any(
                "Recalculated" in call_str and "ban recommendations" in call_str
                for call_str in print_calls
            )
            assert success_log_found, (
                "Expected success log message 'Recalculated ... ban recommendations' not found"
            )

    @patch("src.assistant.Assistant")
    @patch("src.db.Database")
    def test_save_custom_pools_no_recalc_when_flag_false(
        self, mock_db_class, mock_assistant_class, tmp_path
    ):
        """
        Test that ban recalculation is skipped when recalculate_bans=False.

        This test verifies the existing behavior (before T1 modification):
        - When recalculate_bans=False, no ban recalculation happens
        - This should work identically in both .exe and dev mode
        """
        # GIVEN: Any mode (.exe or dev)
        pools_file = tmp_path / "champion_pools.json"

        with patch("src.pool_manager.get_user_pools_path", return_value=str(pools_file)):
            manager = PoolManager()
            manager.create_pool(
                name="No Recalc Pool",
                champions=["Jax", "Fiora"],
                description="Pool with recalc disabled",
            )

            # Mock Assistant
            mock_assistant_instance = Mock()
            mock_assistant_class.return_value = mock_assistant_instance

            # WHEN: Save with recalculate_bans=False
            result = manager.save_custom_pools(recalculate_bans=False)

            # THEN: Save succeeds
            assert result is True

            # THEN: precalculate_all_custom_pool_bans() is NOT called (flag disabled)
            mock_assistant_instance.precalculate_all_custom_pool_bans.assert_not_called()

    @patch("src.assistant.Assistant")
    @patch("src.db.Database")
    def test_save_custom_pools_no_recalc_when_no_custom_pools(
        self, mock_db_class, mock_assistant_class, tmp_path
    ):
        """
        Test that ban recalculation is skipped when there are no custom pools.

        Verifies existing behavior:
        - When custom_pools list is empty, no recalculation happens
        - Prevents unnecessary database operations
        """
        # GIVEN: PoolManager with NO custom pools (only system pools)
        pools_file = tmp_path / "champion_pools.json"

        with patch("src.pool_manager.get_user_pools_path", return_value=str(pools_file)):
            manager = PoolManager()
            # Do not create any custom pools (only default/system pools exist)

            # Mock Assistant
            mock_assistant_instance = Mock()
            mock_assistant_class.return_value = mock_assistant_instance

            # WHEN: Save with recalculate_bans=True
            result = manager.save_custom_pools(recalculate_bans=True)

            # THEN: Save succeeds
            assert result is True

            # THEN: precalculate_all_custom_pool_bans() is NOT called (no custom pools)
            mock_assistant_instance.precalculate_all_custom_pool_bans.assert_not_called()

    @patch("src.assistant.Assistant")
    @patch("src.db.Database")
    @patch("builtins.print")
    def test_save_custom_pools_graceful_error_on_ban_recalc_failure(
        self, mock_print, mock_db_class, mock_assistant_class, tmp_path
    ):
        """
        Test graceful error handling when ban recalculation fails.

        Verifies that:
        - Save operation STILL succeeds even if ban recalculation fails
        - Warning message is logged
        - Exception does not propagate
        """
        # GIVEN: PoolManager with custom pool
        pools_file = tmp_path / "champion_pools.json"

        with patch("src.pool_manager.get_user_pools_path", return_value=str(pools_file)):
            manager = PoolManager()
            manager.create_pool(
                name="Error Pool",
                champions=["TestChamp"],
                description="Pool to test error handling",
            )

            # Mock Database and Assistant to simulate failure
            mock_db_instance = Mock()
            mock_db_class.return_value = mock_db_instance

            mock_assistant_instance = Mock()
            mock_assistant_instance.precalculate_all_custom_pool_bans.side_effect = (
                RuntimeError("Simulated database error")
            )
            mock_assistant_class.return_value = mock_assistant_instance

            # WHEN: Save with recalculate_bans=True (but recalc fails)
            result = manager.save_custom_pools(recalculate_bans=True)

            # THEN: Save operation STILL succeeds (graceful degradation)
            assert result is True
            assert pools_file.exists()

            # THEN: Warning message logged
            print_calls = [str(call_args) for call_args in mock_print.call_args_list]
            warning_found = any(
                "WARNING" in call_str
                and "Failed to recalculate ban recommendations" in call_str
                for call_str in print_calls
            )
            assert warning_found, (
                "Expected warning log for ban recalculation failure not found"
            )

    @patch("builtins.open", side_effect=PermissionError("Write access denied"))
    @patch("builtins.print")
    def test_save_custom_pools_returns_false_on_filesystem_error(
        self, mock_print, mock_open, tmp_path
    ):
        """
        Test that save_custom_pools returns False when filesystem write fails.

        Verifies error handling for:
        - Permission errors
        - Disk full scenarios
        - Other filesystem issues
        """
        # GIVEN: PoolManager with custom pool
        pools_file = tmp_path / "champion_pools.json"

        with patch("src.pool_manager.get_user_pools_path", return_value=str(pools_file)):
            manager = PoolManager()
            manager.create_pool(
                name="Fail Pool",
                champions=["Aatrox"],
                description="Pool to test filesystem error",
            )

            # WHEN: Save fails due to filesystem error
            result = manager.save_custom_pools(recalculate_bans=False)

            # THEN: Returns False
            assert result is False

            # THEN: Error message logged
            print_calls = [str(call_args) for call_args in mock_print.call_args_list]
            error_found = any(
                "ERROR" in call_str and "Failed to save custom pools" in call_str
                for call_str in print_calls
            )
            assert error_found, "Expected error log for filesystem failure not found"
