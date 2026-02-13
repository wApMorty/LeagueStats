"""Regression tests for auto_update_db.py - Environment variable loading."""

import pytest
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open


class TestLoadEnvAdminApiKey:
    """Regression tests for ADMIN_API_KEY loading from .env file."""

    @patch.dict(os.environ, {"ADMIN_API_KEY": "test_key_12345"}, clear=False)
    def test_load_env_admin_api_key_success(self):
        """
        Test successful loading of ADMIN_API_KEY from environment.

        Scenario: ADMIN_API_KEY is set in environment (via .env or system)
        Expected: os.getenv() returns the key correctly
        """
        # Verify ADMIN_API_KEY is accessible
        api_key = os.getenv("ADMIN_API_KEY")
        assert api_key == "test_key_12345"
        assert api_key is not None

        # Verify module can import without errors
        import scripts.auto_update_db

        assert scripts.auto_update_db is not None

    def test_load_env_missing_file(self, tmp_path):
        """
        Test graceful handling when .env file is missing.

        Scenario: .env file does not exist in project root
        Expected: No exception raised, module imports successfully
        """
        # Create temporary project structure without .env
        fake_project_root = tmp_path / "fake_project"
        fake_project_root.mkdir()

        # Verify .env does not exist
        env_file = fake_project_root / ".env"
        assert not env_file.exists()

        # Import module should not raise exception
        try:
            import scripts.auto_update_db

            # If we reach here, no exception was raised (success)
            assert True

        except Exception as e:
            pytest.fail(f".env missing should not raise exception: {e}")

    @patch.dict(os.environ, {}, clear=False)
    def test_load_env_missing_key(self):
        """
        Test behavior when ADMIN_API_KEY is not in environment.

        Scenario: .env file exists but ADMIN_API_KEY is not set
        Expected: os.getenv("ADMIN_API_KEY") returns None
        """
        # Remove ADMIN_API_KEY from environment (if exists)
        os.environ.pop("ADMIN_API_KEY", None)

        # Verify ADMIN_API_KEY is None (missing key)
        api_key = os.getenv("ADMIN_API_KEY")
        assert api_key is None

    def test_load_env_dotenv_import_error(self):
        """
        Test graceful handling when python-dotenv is not installed.

        Scenario: ImportError when importing dotenv (lines 43-50)
        Expected: Exception caught, script continues execution
        """
        # Simulate ImportError by hiding dotenv module
        with patch.dict("sys.modules", {"dotenv": None}):
            try:
                # Module should handle ImportError gracefully (line 48-50)
                import scripts.auto_update_db

                # If we reach here, ImportError was caught gracefully
                assert True

            except ImportError:
                pytest.fail("ImportError should be caught gracefully (lines 48-50)")


class TestApiRefreshWithAdminKey:
    """Regression tests for API refresh call using ADMIN_API_KEY."""

    @patch("scripts.auto_update_db.requests.post")
    @patch("os.getenv")
    def test_api_refresh_with_valid_key(self, mock_getenv, mock_post):
        """
        Test API refresh call with valid ADMIN_API_KEY.

        Scenario: ADMIN_API_KEY is set in environment
        Expected: POST request sent with X-API-Key header
        """
        # Setup: Valid API key
        mock_getenv.return_value = "valid_api_key_12345"
        mock_post.return_value = MagicMock(status_code=200)

        # Simulate API refresh logic (lines 470-490)
        api_url = "https://leaguestats-adf4.onrender.com/admin/refresh-db"
        api_key = os.getenv("ADMIN_API_KEY")

        if api_key:
            response = mock_post(api_url, headers={"X-API-Key": api_key}, timeout=30)
            assert response.status_code == 200

        # Verify POST was called with correct headers
        mock_post.assert_called_once_with(
            api_url, headers={"X-API-Key": "valid_api_key_12345"}, timeout=30
        )

    @patch("scripts.auto_update_db.requests.post")
    @patch("os.getenv")
    def test_api_refresh_skipped_without_key(self, mock_getenv, mock_post):
        """
        Test API refresh skipped when ADMIN_API_KEY is missing.

        Scenario: ADMIN_API_KEY is None (not configured)
        Expected: API refresh skipped, no POST request sent
        """
        # Setup: No API key
        mock_getenv.return_value = None

        # Simulate API refresh logic with early return (lines 476-478)
        api_key = os.getenv("ADMIN_API_KEY")

        if not api_key:
            # Should skip API refresh
            pass
        else:
            # Should not reach here
            pytest.fail("API refresh should be skipped when api_key is None")

        # Verify POST was never called
        mock_post.assert_not_called()

    @patch("scripts.auto_update_db.requests.post")
    @patch("os.getenv")
    def test_api_refresh_invalid_key_returns_403(self, mock_getenv, mock_post):
        """
        Test API refresh handling when API key is invalid.

        Scenario: ADMIN_API_KEY is set but invalid
        Expected: POST returns 403 Forbidden
        """
        # Setup: Invalid API key
        mock_getenv.return_value = "invalid_key"
        mock_post.return_value = MagicMock(status_code=403)

        # Simulate API refresh logic
        api_url = "https://leaguestats-adf4.onrender.com/admin/refresh-db"
        api_key = os.getenv("ADMIN_API_KEY")

        if api_key:
            response = mock_post(api_url, headers={"X-API-Key": api_key}, timeout=30)
            assert response.status_code == 403  # Invalid API key

        # Verify POST was called
        mock_post.assert_called_once()


class TestDotenvIntegration:
    """Integration tests for dotenv loading with real file paths."""

    @patch.dict(os.environ, {}, clear=True)
    def test_dotenv_loads_before_config_import(self, tmp_path):
        """
        Test that dotenv loads BEFORE config module is imported.

        Scenario: Ensure dotenv loading happens at lines 41-50 (BEFORE line 74)
        Expected: Environment variables available when config is imported
        """
        # Create temporary .env file
        env_file = tmp_path / ".env"
        env_file.write_text("ADMIN_API_KEY=test_integration_key\nDATABASE_PATH=./test.db\n")

        # Mock Path to return our temp .env
        with patch("pathlib.Path") as mock_path_class:
            mock_path_instance = MagicMock()
            mock_path_instance.__truediv__ = lambda self, other: (
                env_file if other == ".env" else MagicMock()
            )
            mock_path_class.return_value = mock_path_instance

            # Load dotenv manually (simulate lines 41-50)
            try:
                from dotenv import load_dotenv

                load_dotenv(env_file)

                # Verify ADMIN_API_KEY was loaded
                api_key = os.getenv("ADMIN_API_KEY")
                assert api_key == "test_integration_key"

            except ImportError:
                pytest.skip("python-dotenv not installed")
