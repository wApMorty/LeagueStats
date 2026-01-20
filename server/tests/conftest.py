"""Pytest fixtures for API testing."""

import pytest
from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture
def client():
    """FastAPI test client."""
    return TestClient(app)
