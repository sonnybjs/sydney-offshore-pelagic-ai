from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from urllib.parse import quote

from pipeline_lib import cfg, ensure_dirs, file_size_mb, rating, save_dataframe, write_json
from prediction_manifest_lib import DEMO_SPECIES, load_existing_manifest, species_entry, write_manifest
from training_prep_lib import grid_id, load_bathymetry, load_structure_points, nearest_structure, seasonality


TARGET_DATE = "2026-05-28"
ERDDAP_BASE = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.csvp"


def erddap_url(date_text: str) -> str:
    bbox = cfg.PREDICT_BBOX
    time = quote(f"{date_text}T09:00:00Z", safe="")
    return (
        f"{ERDDAP_BASE}?analysed_sst"
        f"[({time})]"
        f"[({bbox['south_lat']}):5:({bbox['north_lat']})]"
        f"[({bbox['west_lon']}):5:({bbox['east_lon']})]"
    )


def compute_gradient(df):
    import numpy as np
    import pandas as pd

    pivot = df.pivot(index="lat", columns="lon", values="sst_c").sort_index().sort_index(axis=1)
    gy, gx = np.gradient(pivot.values.astype(float))
    grad = pd.DataFrame(np.hypot(gx, gy), index=pivot.index, columns=pivot.columns).stack().reset_index()
    grad.columns = ["lat", "lon", "sst_gradient"]
    out = df.merge(grad, on=["lat", "lon"], how="left")
    out["sst_front_strength"] = out["sst_gradient"].clip(lower=0)
    return out


def try_load_mur(date_text: str):
    import pandas as pd

    raw = pd.read_csv(erddap_url(date_text))
    lower = {col.lower(): col for col in raw.columns}
    lat_col = next(col for key, col in lower.items() if key.startswith("latitude"))
    lon_col = next(col for key, col in lower.items() if key.startswith("longitude"))
    sst_col = next(col for key, col in lower.items() if key.startswith("analysed_sst"))
    df = raw[[lat_col, lon_col, sst_col]].copy()
    df.columns = ["lat", "lon", "sst_c"]
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce").round(4)
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce").round(4)
    df["sst_c"] = pd.to_numeric(df["sst_c"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    return compute_gradient(df)


def latest_available_sst(target_date: str) -> tuple[str, object, list[dict]]:
    attempts = []
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    for offset in range(0, 31):
        day = (target - timedelta(days=offset)).isoformat()
        try:
            df = try_load_mur(day)
            attempts.append({"date": day, "status": "success", "cell_count": int(len(df))})
            return day, df, attempts
        except Exception as exc:
            attempts.append({"date": day, "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    raise RuntimeError(f"No MUR SST available within 30 days before {target_date}: {attempts[-3:]}")


def build_prediction_grid(target_date: str):
    import pandas as pd

    sst_source_date, sst, attempts = latest_available_sst(target_date)
    sst = sst.copy()
    sst["date"] = target_date
    sst["grid_id"] = [grid_id(lat, lon) for lat, lon in zip(sst["lat"], sst["lon"])]
    sst["sst_3d_change"] = math.nan
    sst["sst_7d_change"] = math.nan
    sst["sst_missing_flag"] = sst["sst_c"].isna()
    sst["sst_source_date"] = sst_source_date
    sst["sst_date_offset_days"] = (datetime.strptime(target_date, "%Y-%m-%d").date() - datetime.strptime(sst_source_date, "%Y-%m-%d").date()).days

    bathy = load_bathymetry()
    if not bathy.empty:
        bathy = bathy.copy()
        bathy["lat"] = bathy["lat"].astype(float).round(4)
        bathy["lon"] = bathy["lon"].astype(float).round(4)
        sst = sst.merge(bathy, on=["lat", "lon"], how="left")
        sst["has_bathymetry"] = sst["depth_m"].notna()
    else:
        for col in ["depth_m", "slope", "distance_to_200m_contour", "distance_to_500m_contour", "distance_to_1000m_contour", "distance_to_shelf_break"]:
            sst[col] = math.nan
        sst["ocean_mask"] = math.nan
        sst["has_bathymetry"] = False

    structures = load_structure_points()
    structure_df = pd.DataFrame([nearest_structure(float(row.lat), float(row.lon), structures) for row in sst.itertuples()])
    sst = pd.concat([sst.reset_index(drop=True), structure_df.reset_index(drop=True)], axis=1)
    sst["has_structure"] = bool(structures)

    for col in ["uo", "vo", "current_speed", "current_direction_degrees", "current_edge_score", "zos", "sla_gradient", "eddy_score", "chl", "chl_log", "chl_gradient", "chl_edge_score", "o2", "dissolved_oxygen", "oxygen_saturation"]:
        sst[col] = math.nan
    sst["has_physics"] = False
    sst["has_chl"] = False
    sst["has_oxygen"] = False
    sst["physics_missing_flag"] = True
    sst["chl_missing_flag"] = True
    sst["oxygen_missing_flag"] = True
    sst["physics_source_date"] = None
    sst["chl_source_date"] = None
    sst["has_sst"] = sst["sst_c"].notna()
    sst["has_lunar"] = False
    sst["has_weather"] = False
    for key, value in seasonality(target_date).items():
        sst[key] = value
    sst["feature_set_name"] = "current_sst_bathy_structure"
    if "ocean_mask" in sst.columns and sst["ocean_mask"].notna().any():
        sst = sst[(sst["ocean_mask"].isna()) | (sst["ocean_mask"].astype(bool))]
    return sst, {"sst_source_date": sst_source_date, "attempts": attempts}


def relative_scores(scores):
    import numpy as np

    arr = np.asarray(scores, dtype=float)
    if len(arr) == 0:
        return arr
    if np.nanmax(arr) - np.nanmin(arr) < 1e-9:
        return np.full_like(arr, 50.0)
    ranks = arr.argsort().argsort()
    return ranks / max(1, len(arr) - 1) * 100


def predict_species(species_id: str, grid, target_date: str, source_dates: dict):
    import joblib

    model_path = cfg.DATA / "processed" / "models" / species_id / "best_model.joblib"
    meta_path = cfg.DATA / "processed" / "models" / species_id / "model_metadata.json"
    if not model_path.exists() or not meta_path.exists():
        return {"species_id": species_id, "status": "unavailable", "reason": "No selected trained model."}
    meta = __import__("json").loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("status") != "selected":
        return {"species_id": species_id, "status": "unavailable", "reason": meta.get("reason", "No selected trained model.")}
    bundle = joblib.load(model_path)
    features = bundle["feature_columns"]
    pred_grid = grid.copy()
    for col in features:
        if col not in pred_grid.columns:
            pred_grid[col] = math.nan
    raw = bundle["model"].predict_proba(pred_grid[features])[:, 1]
    pred_grid["score"] = relative_scores(raw).round(2)
    pred_grid["rating"] = pred_grid["score"].apply(rating)
    pred_grid["species_id"] = species_id
    pred_grid["common_name"] = meta.get("common_name", species_id)
    pred_grid["mode"] = "current"
    pred_grid["target_date"] = target_date
    pred_grid["prediction_date"] = target_date
    pred_grid["confidence"] = meta.get("confidence_level", "Low")
    pred_grid["model_type"] = meta.get("model_type")
    pred_grid["feature_set_name"] = meta.get("feature_set_name")
    pred_grid["data_sources_available"] = "sst,bathymetry,structure"
    out_base = cfg.DATA / "processed" / "predictions" / f"{target_date}_{species_id}_current_sydney_heatmap"
    outputs = save_dataframe(pred_grid, out_base.with_suffix(".csv"), out_base.with_suffix(".parquet"))
    features_geo = []
    for row in pred_grid.nlargest(min(1000, len(pred_grid)), "score").to_dict("records"):
        features_geo.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
                "properties": {
                    "species_id": species_id,
                    "common_name": row["common_name"],
                    "mode": "current",
                    "target_date": target_date,
                    "prediction_date": target_date,
                    "date": target_date,
                    "score": float(row["score"]),
                    "rating": row["rating"],
                    "confidence": row["confidence"],
                    "model_type": row["model_type"],
                    "feature_set_name": row["feature_set_name"],
                    "top_drivers": features[:5],
                    "explanation": ["Relative habitat suitability estimated from available SST, bathymetry, structure and seasonality features."],
                    "limitations": ["Not exact fish location.", "Not guaranteed catch.", "Current/chlorophyll/oxygen unavailable in this first current run."],
                    "sst_source_date": source_dates["sst_source_date"],
                    "physics_source_date": None,
                    "chl_source_date": None,
                    "has_sst": bool(row.get("has_sst", False)),
                    "has_bathymetry": bool(row.get("has_bathymetry", False)),
                    "has_physics": False,
                    "has_chl": False,
                    "data_sources_available": row["data_sources_available"],
                    "sst_c": None if math.isnan(float(row.get("sst_c", math.nan))) else float(row["sst_c"]),
                    "depth_m": None if math.isnan(float(row.get("depth_m", math.nan))) else float(row["depth_m"]),
                },
            }
        )
    geojson_path = out_base.with_suffix(".geojson")
    write_json(geojson_path, {"type": "FeatureCollection", "features": features_geo})
    return {"species_id": species_id, "status": "written", "geojson": str(geojson_path.relative_to(cfg.ROOT)), "outputs": outputs}


def main() -> None:
    ensure_dirs()
    grid, source_info = build_prediction_grid(TARGET_DATE)
    outputs = [predict_species(species_id, grid, TARGET_DATE, source_info) for species_id in DEMO_SPECIES]
    manifest = load_existing_manifest()
    current_species = {}
    for species_id in DEMO_SPECIES:
        path = cfg.DATA / "processed" / "predictions" / f"{TARGET_DATE}_{species_id}_current_sydney_heatmap.geojson"
        current_species[species_id] = species_entry(species_id, "current", path if path.exists() else None, target_date=TARGET_DATE)
        if current_species[species_id].get("available"):
            current_species[species_id]["data_source_dates"]["sst"] = source_info["sst_source_date"]
            current_species[species_id]["data_source_dates"]["physics"] = None
            current_species[species_id]["data_source_dates"]["chl"] = None
    manifest["current"] = {"mode": "current", "target_date": TARGET_DATE, "species": current_species, "notes": "Current mode targets tomorrow and uses latest available SST if target-day SST is unavailable."}
    write_manifest(manifest)
    summary = {"status": "completed", "target_date": TARGET_DATE, "sst_source_date": source_info["sst_source_date"], "outputs": outputs}
    write_json(cfg.DATA / "processed" / "predictions" / "current_prediction_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
