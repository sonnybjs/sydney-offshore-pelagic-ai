from app.scoring.pelagic_score import score_pelagic_habitat
from app.scoring.species_profiles import get_species_profile, load_species_profiles
from app.services.explanation_service import ocean_summary_for
from app.services.ocean_mock_service import gradient_at, sst_at
from app.services.poi_service import get_pois


def _context_from_poi(poi: dict) -> dict:
    lat = poi["latitude"]
    lon = poi["longitude"]
    current_speed = 0.48 + max(0, lon - 151.0) * 0.12
    return {
        "sst_c": sst_at(lat, lon),
        "gradient_strength": gradient_at(lat, lon),
        "current_speed_m_s": round(current_speed, 2),
        "poi_type": poi["poi_type"],
        "depth_class": poi["depth_class"],
        "eddy_signal": lon > 152.0 and -34.6 < lat < -33.4,
        "data_confidence": "mock",
    }


def hotspots_for_species(species_id: str, min_score: float | None = None) -> dict:
    profile = get_species_profile(species_id)
    features = []
    for poi in get_pois():
        context = _context_from_poi(poi)
        scored = score_pelagic_habitat(profile, context)
        if min_score is not None and scored["score"] < min_score:
            continue
        props = {
            "id": f"{species_id}_{poi['id']}",
            "species_id": species_id,
            "species_name": profile["common_name"],
            "latitude": poi["latitude"],
            "longitude": poi["longitude"],
            "area_name": poi["name"],
            "score": scored["score"],
            "rating": scored["rating"],
            "confidence": scored["confidence"],
            "explanation": scored["explanation"],
            "suggested_strategy": scored["suggested_strategy"],
            "ocean_summary": ocean_summary_for(context),
            "key_drivers": scored["key_drivers"],
            "caution_notes": scored["caution_notes"],
            "demo_only": True,
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [poi["longitude"], poi["latitude"]]},
                "properties": props,
            }
        )
    features.sort(key=lambda f: f["properties"]["score"], reverse=True)
    return {"type": "FeatureCollection", "features": features}


def all_hotspots(species_id: str | None = None, min_score: float | None = None) -> dict:
    if species_id:
        return hotspots_for_species(species_id, min_score)
    features = []
    for profile in load_species_profiles():
        features.extend(hotspots_for_species(profile["species_id"], min_score)["features"][:5])
    features.sort(key=lambda f: f["properties"]["score"], reverse=True)
    return {"type": "FeatureCollection", "features": features}

