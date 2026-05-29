from __future__ import annotations

import csv
import gzip
import json
import math
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query


router = APIRouter()
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PREDICTION_DIR = PROJECT_ROOT / "data" / "processed" / "predictions"
PREDICTION_500M_DIR = PROJECT_ROOT / "data" / "processed" / "predictions_500m"
PREDICTION_500M_DEEP_DIR = PROJECT_ROOT / "data" / "processed" / "predictions_500m_deep"
CORRECTED_PREDICTION_DIR = PROJECT_ROOT / "data" / "processed" / "predictions_corrected"
MANIFEST_PATH = PREDICTION_DIR / "prediction_manifest.json"
CORRECTED_SUMMARY_PATH = CORRECTED_PREDICTION_DIR / "corrected_prediction_summary.json"
POI_PATH = PROJECT_ROOT / "backend" / "app" / "data" / "offshore_pois_seed.geojson"

TRAINED_DEMO_SPECIES = {
    "mahi_mahi": "Mahi Mahi / Dolphinfish",
    "southern_bluefin_tuna": "Southern Bluefin Tuna",
    "yellowtail_kingfish": "Yellowtail Kingfish",
}
TRAINED_DEMO_DATE = "2025-12-22"
AUDIT_WARNING = "Model under audit: trained presence/background output has known bias risk. Use for model debugging only."


def read_json(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {path.name}")
    try:
        if path.suffix == ".gz":
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                return json.load(handle)
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Invalid JSON file: {path.name}") from exc


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {
            "demo": {"species": {}},
            "current": {"species": {}},
            "message": "Prediction manifest not found. Run python pipelines/run_generate_demo_and_current_predictions.py",
        }
    manifest = read_json(MANIFEST_PATH)
    return apply_corrected_prediction_safety(manifest)


def model_metadata(species_id: str) -> dict:
    path = PROJECT_ROOT / "data" / "processed" / "models" / species_id / "model_metadata.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def available_500m_dates(species_id: str) -> list[str]:
    return available_500m_dates_for_source(species_id, "scikit_learn")


def available_500m_dates_for_source(species_id: str, model_source: str = "scikit_learn") -> list[str]:
    directory = PREDICTION_500M_DEEP_DIR if model_source == "deep_learning" else PREDICTION_500M_DIR
    stem = "500m_deep_sydney_heatmap_top" if model_source == "deep_learning" else "500m_sydney_heatmap_top"
    dates = []
    for suffix in [
        f"_{species_id}_{stem}.geojson",
        f"_{species_id}_{stem}.geojson.gz",
    ]:
        for path in directory.glob(f"*{suffix}"):
            if path.name.endswith(suffix):
                dates.append(path.name[: -len(suffix)])
    return sorted(dates)


def load_poi_features() -> list[dict]:
    if not POI_PATH.exists():
        return []
    try:
        payload = json.loads(POI_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return payload.get("features", [])


def nearest_poi(lat: float, lon: float) -> dict | None:
    best = None
    for feature in load_poi_features():
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        props = feature.get("properties") or {}
        if not isinstance(coords[0], (int, float)) or not isinstance(coords[1], (int, float)):
            continue
        distance = haversine_km(lat, lon, coords[1], coords[0])
        if best is None or distance < best["distance_km"]:
            best = {
                "id": props.get("id"),
                "name": props.get("name"),
                "poi_type": props.get("poi_type"),
                "distance_km": round(distance, 2),
                "demo_only": props.get("demo_only", True),
                "notes": props.get("notes"),
            }
    return best


def as_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return None if isinstance(value, float) and (math.isnan(value) or math.isinf(value)) else value
    text = str(value).strip()
    if text == "" or text.lower() in {"nan", "none", "null"}:
        return None
    try:
        number = float(text)
    except ValueError:
        return value
    return None if math.isnan(number) or math.isinf(number) else number


def strict_rating(score) -> str:
    if not isinstance(score, (int, float)):
        return "Low"
    if score >= 95:
        return "Prime"
    if score >= 85:
        return "Good"
    if score >= 60:
        return "Possible"
    return "Low"


def full_grid_geojson_from_csv(csv_path: Path, species_id: str) -> dict:
    features = []
    with csv_path.open("r", newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            lat = as_number(row.get("lat"))
            lon = as_number(row.get("lon"))
            score = as_number(row.get("score"))
            if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
                continue
            props = {
                "species_id": species_id,
                "common_name": row.get("common_name") or TRAINED_DEMO_SPECIES.get(species_id, species_id),
                "date": row.get("date"),
                "lat": lat,
                "lon": lon,
                "score": score,
                "rating": strict_rating(score),
                "confidence": row.get("confidence") or "Low",
                "model_type": row.get("model_type"),
                "feature_set_name": row.get("feature_set_name"),
                "sst_c": as_number(row.get("sst_c")),
                "sst_gradient": as_number(row.get("sst_gradient")),
                "sst_front_strength": as_number(row.get("sst_front_strength")),
                "depth_m": as_number(row.get("depth_m")),
                "distance_to_shelf_break": as_number(row.get("distance_to_shelf_break")),
                "data_sources_available": row.get("data_sources_available"),
                "top_drivers": ["sst_c", "sst_front_strength", "depth_m", "seasonality"],
                "explanation": [
                    "This API response uses the full prediction grid, not the old top-only GeoJSON export.",
                    "Rating uses strict display thresholds: Prime top 5%, Good 5-15%, Possible 15-40%, Low bottom 60%.",
                ],
                "limitations": [
                    "Relative habitat suitability only.",
                    "Not exact fish location or true catch probability.",
                    "Presence/background model is under audit for sampling and background bias.",
                ],
            }
            features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [lon, lat]}, "properties": props})
    return {"type": "FeatureCollection", "features": features}


def read_prediction_geojson(path: Path, entry: dict, species_id: str, date_text: str | None = None, model_source: str = "scikit_learn") -> dict:
    date_text = date_text or entry.get("prediction_date") or TRAINED_DEMO_DATE
    if model_source == "deep_learning":
        high_res_path = PREDICTION_500M_DEEP_DIR / f"{date_text}_{species_id}_500m_deep_sydney_heatmap_top.geojson"
    else:
        high_res_path = PREDICTION_500M_DIR / f"{date_text}_{species_id}_500m_sydney_heatmap_top.geojson"
    high_res_gz_path = high_res_path.with_suffix(high_res_path.suffix + ".gz")
    if high_res_path.exists():
        return read_json(high_res_path)
    if high_res_gz_path.exists():
        return read_json(high_res_gz_path)
    csv_path = path.with_suffix(".csv")
    if entry.get("audit_status") == "trained_under_audit" and csv_path.exists():
        return full_grid_geojson_from_csv(csv_path, species_id)
    return read_json(path)


def rating_distribution(geojson: dict) -> dict:
    counts: dict[str, int] = {}
    for feature in geojson.get("features", []):
        rating = (feature.get("properties") or {}).get("rating", "Unknown")
        counts[rating] = counts.get(rating, 0) + 1
    total = sum(counts.values()) or 1
    return {key: {"count": value, "percent": round(value / total * 100, 2)} for key, value in sorted(counts.items())}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def coast_segment(lat: float, segments: int = 8) -> int:
    south = -36.5
    north = -32.0
    if not isinstance(lat, (int, float)):
        return 0
    ratio = (lat - south) / (north - south)
    return max(0, min(segments - 1, int(ratio * segments)))


def recommended_spots(geojson: dict, radius_m: int = 500, limit: int = 30, min_separation_km: float = 4.0) -> list[dict]:
    rows = []
    for feature in geojson.get("features", []):
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
        score = props.get("score")
        if not isinstance(score, (int, float)):
            continue
        distance = props.get("distance_to_coast_km")
        band = "offshore"
        if isinstance(distance, (int, float)):
            if distance <= 20:
                band = "nearshore"
            elif distance <= 50:
                band = "midshore"
            else:
                band = "offshore"
        rows.append({"feature": feature, "score": score, "lat": coords[1], "lon": coords[0], "band": band, "segment": coast_segment(coords[1])})
    quotas = {"nearshore": max(5, limit // 2), "midshore": max(3, limit // 3), "offshore": max(1, limit - max(5, limit // 2) - max(3, limit // 3))}
    selected = []

    def add_item(item: dict) -> bool:
        nonlocal selected
        if len(selected) >= limit:
            return False
        if not isinstance(item["lat"], (int, float)) or not isinstance(item["lon"], (int, float)):
            return False
        if any(haversine_km(item["lat"], item["lon"], spot["lat"], spot["lon"]) < min_separation_km for spot in selected):
            return False
        props = dict((item["feature"].get("properties") or {}))
        props["spot_rank"] = len(selected) + 1
        props["recommendation_radius_m"] = radius_m
        props["coast_priority_band"] = item["band"]
        props["coast_segment"] = item["segment"]
        poi = nearest_poi(item["lat"], item["lon"])
        if poi:
            props["nearest_poi"] = poi
            props["poi_context"] = f"Nearest known/demo offshore feature: {poi.get('name')} ({poi.get('poi_type')}), about {poi.get('distance_km')} km away."
        drivers = []
        if isinstance(props.get("sst_c"), (int, float)):
            drivers.append(f"SST {props['sst_c']:.1f}C")
        if isinstance(props.get("sst_front_strength"), (int, float)):
            drivers.append(f"SST front proxy {props['sst_front_strength']:.3f}")
        if isinstance(props.get("current_speed"), (int, float)):
            drivers.append(f"Current {props['current_speed']:.2f}m/s")
        if isinstance(props.get("depth_m"), (int, float)):
            drivers.append(f"Depth {props['depth_m']:.0f}m")
        if isinstance(props.get("distance_to_coast_km"), (int, float)):
            drivers.append(f"{props['distance_to_coast_km']:.1f}km from coast")
        props["top_drivers"] = drivers
        props["explanation"] = [
            "Ranked hotspot candidate from the 500m display grid.",
            "Coastline segments are used so recommendations spread along NSW waters while still prioritising the highest local scores.",
            "Score is relative habitat suitability, not exact fish location.",
            props.get("poi_context") or "No nearby POI context available.",
        ]
        props["model_grid_resolution_note"] = "500m display grid is resampled from coarser environmental data. This is a ranked habitat-suitability candidate, not a precise fish position."
        selected.append({"type": "Feature", "geometry": item["feature"]["geometry"], "properties": props, "lat": item["lat"], "lon": item["lon"]})
        return True

    def selected_count(band: str | None = None, segment: int | None = None) -> int:
        return sum(
            1
            for spot in selected
            if (band is None or spot["properties"].get("coast_priority_band") == band)
            and (segment is None or spot["properties"].get("coast_segment") == segment)
        )

    def pass_select(band: str, quota: int, min_score: float, per_segment_target: int) -> None:
        for segment in range(8):
            if selected_count(band=band) >= quota:
                break
            if selected_count(band=band, segment=segment) >= per_segment_target:
                continue
            candidates = [
                row for row in rows
                if row["band"] == band and row["segment"] == segment and row["score"] >= min_score
            ]
            for item in sorted(candidates, key=lambda candidate: candidate["score"], reverse=True):
                if add_item(item):
                    break

    def fill_band(band: str, quota: int, min_score: float = 0) -> None:
        candidates = [row for row in rows if row["band"] == band and row["score"] >= min_score]
        for item in sorted(candidates, key=lambda candidate: candidate["score"], reverse=True):
            if selected_count(band=band) >= quota:
                break
            add_item(item)

    for score_floor in [95, 85, 75]:
        pass_select("nearshore", quotas["nearshore"], score_floor, 1)
        pass_select("midshore", quotas["midshore"], score_floor, 1)
    fill_band("nearshore", quotas["nearshore"], 85)
    fill_band("midshore", quotas["midshore"], 85)
    fill_band("offshore", quotas["offshore"], 85)
    fill_band("nearshore", quotas["nearshore"], 60)
    fill_band("midshore", quotas["midshore"], 60)
    fill_band("offshore", quotas["offshore"], 60)
    for item in sorted(rows, key=lambda candidate: candidate["score"], reverse=True):
        if len(selected) >= limit:
            break
        add_item(item)
    selected = sorted(selected, key=lambda spot: spot["properties"].get("score", 0), reverse=True)[:limit]
    for rank, spot in enumerate(selected, start=1):
        spot["properties"]["spot_rank"] = rank
    for spot in selected:
        spot.pop("lat", None)
        spot.pop("lon", None)
    return selected


def apply_corrected_prediction_safety(manifest: dict) -> dict:
    """Expose the latest trained-model demo outputs, clearly marked under audit."""
    demo_species = manifest.setdefault("demo", {}).setdefault("species", {})
    for species_id, common_name in TRAINED_DEMO_SPECIES.items():
        date_text = TRAINED_DEMO_DATE
        file_path = f"data/processed/predictions/{date_text}_{species_id}_sydney_heatmap.geojson"
        high_res_path = PREDICTION_500M_DIR / f"{date_text}_{species_id}_500m_sydney_heatmap_top.geojson"
        high_res_gz_path = high_res_path.with_suffix(high_res_path.suffix + ".gz")
        if not (PROJECT_ROOT / file_path).exists() and not high_res_path.exists() and not high_res_gz_path.exists():
            demo_species[species_id] = {
                "available": False,
                "species_id": species_id,
                "common_name": common_name,
                "reason": "trained prediction file is missing",
                "model_confidence": "Unavailable",
                "audit_status": "unavailable",
            }
            continue
        metadata = model_metadata(species_id)
        dates = available_500m_dates(species_id)
        latest_date = dates[-1] if dates else date_text
        demo_species[species_id] = {
            "available": True,
            "mode": "demo",
            "species_id": species_id,
            "common_name": metadata.get("common_name") or common_name,
            "prediction_date": latest_date,
            "target_date": latest_date,
            "available_dates": dates,
            "file_path": file_path,
            "model_type": metadata.get("model_type", "trained_model"),
            "model_confidence": metadata.get("confidence_level", "Low"),
            "feature_set_name": metadata.get("feature_set_name", "trained_feature_set"),
            "data_source_dates": {
                "sst": latest_date,
                "physics": latest_date,
                "chl": None,
                "bathymetry": "static",
            },
            "available_layers": ["habitat_heatmap", "hotspot_points", "poi_markers", "sst_front_proxy"],
            "audit_status": "trained_under_audit",
            "warning": AUDIT_WARNING,
            "score_explanation": "Score is relative habitat suitability / hotspot score from a presence/background model, not true probability.",
            "grid_resolution_m_estimate": 500,
            "source_resolution_note": "500m map layer is a display/recommendation grid using resampled source environmental features.",
            "notes": f"{AUDIT_WARNING} Relative habitat suitability only; not exact fish location or guaranteed catch.",
        }
    current_manifest = manifest.setdefault("current", {})
    current_available_dates = current_manifest.get("available_dates") or []
    current_species = current_manifest.setdefault("species", {})
    for species_id, common_name in TRAINED_DEMO_SPECIES.items():
        entry = current_species.setdefault(species_id, {"species_id": species_id, "common_name": common_name})
        sl_dates = set(available_500m_dates_for_source(species_id, "scikit_learn"))
        dl_dates = set(available_500m_dates_for_source(species_id, "deep_learning"))
        generated_dates = [date for date in current_available_dates if date in sl_dates or date in dl_dates]
        if generated_dates:
            latest = generated_dates[-1]
            entry.update(
                {
                    "available": True,
                    "mode": "current",
                    "species_id": species_id,
                    "common_name": entry.get("common_name") or common_name,
                    "prediction_date": latest,
                    "target_date": latest,
                    "available_dates": generated_dates,
                    "model_confidence": entry.get("model_confidence", "Low"),
                    "audit_status": entry.get("audit_status", "current_inference_under_audit"),
                    "warning": entry.get("warning", "Current/tomorrow output uses latest available environmental data where target-day sources are unavailable."),
                    "score_explanation": entry.get("score_explanation", "Score is relative habitat suitability / hotspot score, not true probability."),
                    "available_layers": entry.get("available_layers", ["habitat_heatmap", "hotspot_points", "poi_markers", "sst_front_proxy"]),
                }
            )
        else:
            entry["available"] = False
            entry["reason"] = "Current predictions have not been generated yet. Run python pipelines/29_generate_today_tomorrow_500m_predictions.py."
            entry["audit_status"] = "current_not_generated"
            entry["warning"] = "Current prediction is unavailable until today/tomorrow inference files exist."
    return manifest


@router.get("/predictions/manifest")
def prediction_manifest() -> dict:
    return load_manifest()


@router.get("/predictions/available")
def prediction_available() -> dict:
    manifest = load_manifest()
    modes = {}
    for mode in ["demo", "current"]:
        species = manifest.get(mode, {}).get("species", {})
        modes[mode] = {
            "species": [
                {
                    "species_id": species_id,
                    "available": payload.get("available", False),
                    "prediction_date": payload.get("prediction_date"),
                    "target_date": payload.get("target_date"),
                    "confidence": payload.get("model_confidence"),
                    "reason": payload.get("reason"),
                    "audit_status": payload.get("audit_status"),
                }
                for species_id, payload in species.items()
            ]
        }
    return {"modes": modes, "manifest_path": str(MANIFEST_PATH.relative_to(PROJECT_ROOT))}


@router.get("/predictions/map")
def prediction_map(
    mode: str = Query(default="demo", pattern="^(demo|current)$"),
    species_id: str = Query(...),
    date: str | None = Query(default=None),
    model_source: str = Query(default="scikit_learn", pattern="^(scikit_learn|deep_learning)$"),
) -> dict:
    manifest = load_manifest()
    species = manifest.get(mode, {}).get("species", {})
    entry = species.get(species_id)
    if not entry:
        raise HTTPException(status_code=404, detail={"message": "Species is not present in prediction manifest.", "available": prediction_available()})
    if not entry.get("available"):
        raise HTTPException(status_code=404, detail={"message": "Prediction unavailable for this species.", "entry": entry, "available": prediction_available()})
    source_dates = available_500m_dates_for_source(species_id, model_source)
    if mode == "current":
        requested_dates = entry.get("available_dates") or [entry.get("prediction_date"), entry.get("target_date")]
        available_dates = [item for item in requested_dates if item in source_dates] or source_dates
    else:
        available_dates = source_dates or entry.get("available_dates") or [entry.get("prediction_date"), entry.get("target_date")]
    selected_date = date or entry.get("prediction_date")
    if selected_date not in set(filter(None, available_dates)) and available_dates:
        selected_date = available_dates[-1]
    if selected_date not in set(filter(None, available_dates)):
        raise HTTPException(status_code=404, detail={"message": "Requested date is not available for this species/mode.", "entry": entry})
    path = PROJECT_ROOT / entry["file_path"]
    geojson = read_prediction_geojson(path, entry, species_id, selected_date, model_source=model_source)
    return {
        "metadata": {
            "mode": mode,
            "model_source": model_source,
            "species_id": species_id,
            "common_name": entry.get("common_name"),
            "prediction_date": selected_date,
            "target_date": selected_date,
            "available_dates": available_dates,
            "data_source_dates": entry.get("data_source_dates", {}),
            "model_confidence": "Experimental" if model_source == "deep_learning" else entry.get("model_confidence"),
            "feature_set_name": "deep_mlp_tabular_oceanographic" if model_source == "deep_learning" else entry.get("feature_set_name"),
            "available_layers": entry.get("available_layers", []),
            "notes": entry.get("notes"),
            "audit_status": entry.get("audit_status"),
            "warning": entry.get("warning"),
            "score_explanation": (
                "Deep learning MLP relative habitat suitability score; experimental sidecar model, not true catch probability."
                if model_source == "deep_learning"
                else entry.get("score_explanation")
            ),
            "grid_resolution_m_estimate": entry.get("grid_resolution_m_estimate"),
            "source_resolution_note": entry.get("source_resolution_note"),
            "rating_distribution": rating_distribution(geojson),
            "feature_count": len(geojson.get("features", [])),
        },
        "geojson": geojson,
    }


@router.get("/predictions/spots")
def prediction_spots(
    mode: str = Query(default="demo", pattern="^(demo|current)$"),
    species_id: str = Query(...),
    date: str | None = Query(default=None),
    model_source: str = Query(default="scikit_learn", pattern="^(scikit_learn|deep_learning)$"),
    radius_m: int = Query(default=500, ge=500, le=2000),
    limit: int = Query(default=30, ge=1, le=50),
    min_separation_km: float = Query(default=4.0, ge=0.5, le=20.0),
) -> dict:
    payload = prediction_map(mode=mode, species_id=species_id, date=date, model_source=model_source)
    spots = recommended_spots(payload["geojson"], radius_m=radius_m, limit=limit, min_separation_km=min_separation_km)
    return {
        "metadata": {
            **payload["metadata"],
            "spot_count": len(spots),
            "recommendation_radius_m": radius_m,
            "min_separation_km": min_separation_km,
            "model_grid_resolution_note": "500m display grid is available, but source environmental data and training grid are coarser. Spots are ranked habitat-suitability candidates, not exact fish positions.",
        },
        "geojson": {"type": "FeatureCollection", "features": spots},
    }
