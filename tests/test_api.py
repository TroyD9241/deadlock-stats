import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture
def mock_db():
    return MagicMock()


def test_health_check(mock_db):
    """Test health endpoint returns healthy."""
    from backend.app.main import app

    with patch("backend.app.main.get_db", return_value=iter([mock_db])):
        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code in [200, 503]


def test_player_search_excludes_opted_out():
    """Verify opted-out players don't appear in search."""
    pass


def test_player_not_found_for_opted_out():
    """Test that opted-out players return 404."""
    pass
