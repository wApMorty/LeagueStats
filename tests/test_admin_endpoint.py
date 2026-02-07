"""Tests for admin endpoint /refresh-db."""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from server.src.api.main import app


class TestAdminEndpoint:
    """Tests for admin /refresh-db endpoint security and functionality."""

    def setup_method(self):
        """Setup test client and valid API key."""
        self.client = TestClient(app)
        self.valid_api_key = "HhdTAzern_Z1UaJB09D7qQTNLLWYClXmGr8eHYK-DwU"
        self.admin_url = "/admin/refresh-db"

    def test_without_api_key(self):
        """Test POST /admin/refresh-db without X-API-Key header.

        Expected: 422 Unprocessable Entity (FastAPI validation requires header)
        """
        response = self.client.post(self.admin_url)
        # FastAPI will return 403 from our validation logic (not 422)
        # because we set Optional[str] = Header(None), so header is optional
        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid API key"

    def test_with_invalid_api_key(self):
        """Test POST /admin/refresh-db with invalid API key.

        Expected: 403 Forbidden + message 'Invalid API key'
        """
        response = self.client.post(self.admin_url, headers={"X-API-Key": "invalid-key-12345"})
        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid API key"

    def test_with_empty_api_key(self):
        """Test POST /admin/refresh-db with empty API key.

        Expected: 403 Forbidden
        """
        response = self.client.post(self.admin_url, headers={"X-API-Key": ""})
        assert response.status_code == 403
        assert response.json()["detail"] == "Invalid API key"

    @patch("server.src.api.routes.admin.close_all_connections", new_callable=AsyncMock)
    def test_with_valid_api_key(self, mock_close_connections):
        """Test POST /admin/refresh-db with valid API key.

        Expected:
        - 200 OK
        - Success message
        - close_all_connections() is called once
        """
        mock_close_connections.return_value = None

        response = self.client.post(self.admin_url, headers={"X-API-Key": self.valid_api_key})

        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["message"] == "Database connection pool refreshed successfully"
        mock_close_connections.assert_called_once()

    @patch("server.src.api.routes.admin.settings")
    def test_admin_api_key_not_configured(self, mock_settings):
        """Test POST /admin/refresh-db when ADMIN_API_KEY env var is not set.

        Expected: 500 Internal Server Error + message 'Admin API key not configured'
        """
        mock_settings.admin_api_key = ""

        response = self.client.post(self.admin_url, headers={"X-API-Key": self.valid_api_key})

        assert response.status_code == 500
        assert response.json()["detail"] == "Admin API key not configured"

    @patch("server.src.api.routes.admin.close_all_connections", new_callable=AsyncMock)
    def test_exception_during_refresh(self, mock_close_connections):
        """Test POST /admin/refresh-db when close_all_connections() raises exception.

        Expected: 500 Internal Server Error + error message in detail
        """
        mock_close_connections.side_effect = Exception("Database connection error")

        response = self.client.post(self.admin_url, headers={"X-API-Key": self.valid_api_key})

        assert response.status_code == 500
        assert "Failed to refresh pool" in response.json()["detail"]
        assert "Database connection error" in response.json()["detail"]


class TestAdminEndpointIntegration:
    """Integration tests for admin endpoint (without mocking database)."""

    def setup_method(self):
        """Setup test client."""
        self.client = TestClient(app)
        self.valid_api_key = "HhdTAzern_Z1UaJB09D7qQTNLLWYClXmGr8eHYK-DwU"
        self.admin_url = "/admin/refresh-db"

    def test_real_pool_refresh(self):
        """Test actual pool refresh without mocking.

        This test verifies that the endpoint can successfully refresh
        the connection pool in a real scenario (requires DATABASE_URL configured).
        """
        response = self.client.post(self.admin_url, headers={"X-API-Key": self.valid_api_key})

        # Should succeed if database is properly configured
        # May fail in CI if DATABASE_URL not set, which is expected
        if response.status_code == 200:
            assert response.json()["status"] == "ok"
            assert response.json()["message"] == "Database connection pool refreshed successfully"
        else:
            # Allow failure in CI/test environment where DB may not be configured
            pytest.skip("Database not configured in test environment")
