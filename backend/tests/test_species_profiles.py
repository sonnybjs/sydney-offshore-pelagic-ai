from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_species_profiles_include_all_v01_targets():
    response = client.get("/api/species")
    assert response.status_code == 200
    species = response.json()
    assert len(species) >= 7
    ids = {item["species_id"] for item in species}
    assert "yellowfin_tuna" in ids
    assert "southern_bluefin_tuna" in ids
    assert "mahi_mahi" in ids

