from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_hotspots_returns_geojson_feature_collection():
    response = client.get("/api/hotspots?species_id=yellowfin_tuna")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) > 0
    props = body["features"][0]["properties"]
    assert "score" in props
    assert "rating" in props
    assert "confidence" in props
    assert "explanation" in props
    assert props["demo_only"] is True

