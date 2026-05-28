from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_mock_ocean_endpoint_returns_mock_source():
    response = client.get("/api/ocean/mock/latest")
    assert response.status_code == 200
    assert response.json()["data_source"] == "mock"

