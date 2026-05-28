from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from pipeline_lib import cfg, haversine_km, in_bbox, nearest_grid_value, read_table


TARGET_SPECIES = list(cfg.SPECIES_CONFIG.keys())
BROWNS = (-34.05, 151.8)


ENV_COLUMNS = [
    "sst_c",
    "sst_gradient",
    "sst_front_strength",
    "sst_3d_change",
    "sst_7d_change",
    "sst_missing_flag",
    "sst_source_date",
    "sst_date_offset_days",
    "uo",
    "vo",
    "current_speed",
    "current_direction_degrees",
    "current_edge_score",
    "zos",
    "sla_gradient",
    "eddy_score",
    "physics_missing_flag",
    "physics_source_date",
    "physics_date_offset_days",
    "chl",
    "chl_log",
    "chl_gradient",
    "chl_edge_score",
    "chl_missing_flag",
    "chl_source_date",
    "chl_date_offset_days",
    "depth_m",
    "slope",
    "ocean_mask",
    "distance_to_200m_contour",
    "distance_to_500m_contour",
    "distance_to_1000m_contour",
    "distance_to_shelf_break",
    "distance_to_nearest_fad_km",
    "distance_to_browns_mountain_km",
    "distance_to_nearest_poi_km",
    "nearest_poi_type",
    "has_sst",
    "has_bathymetry",
    "has_physics",
    "has_chl",
    "has_structure",
    "feature_set_name",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def candidate_occurrence_files(species_id: str) -> list[Path]:
    base = cfg.DATA / "interim" / "occurrence_clean"
    return [
        base / f"{species_id}_2002_extended_clean.csv",
        base / f"{species_id}_gbif_clean.csv",
        base / f"{species_id}_clean.csv",
    ]


def load_best_occurrences(species_id: str):
    import pandas as pd

    frames = []
    for path in candidate_occurrence_files(species_id):
        if path.exists():
            try:
                frame = pd.read_csv(path)
            except pd.errors.EmptyDataError:
                continue
            if not frame.empty:
                frames.append(frame)
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True, sort=False)
    if "occurrenceID" not in df.columns:
        df["occurrenceID"] = ""
    df["rounded_lat"] = df["decimalLatitude"].astype(float).round(4)
    df["rounded_lon"] = df["decimalLongitude"].astype(float).round(4)
    df = df.drop_duplicates(subset=["species_id", "date", "rounded_lat", "rounded_lon"])
    df = df[df["date"].astype(str).str.len() == 10]
    return df


def load_all_best_occurrences():
    import pandas as pd

    frames = []
    for species_id in TARGET_SPECIES:
        df = load_best_occurrences(species_id)
        if not df.empty:
            frames.append(df)
    return pd.concat(frames, ignore_index=True, sort=False) if frames else pd.DataFrame()


def feature_grid_path(date_text: str) -> Path:
    return cfg.DATA / "interim" / "feature_grid" / "daily_features" / f"features_{date_text}.csv"


def load_feature_grid(date_text: str):
    import pandas as pd

    summary = load_json(cfg.DATA / "interim" / "feature_grid" / "daily_features_training_prep_summary.json", {})
    if summary:
        valid_dates = {item.get("date") for item in summary.get("items", []) if item.get("status") == "built"}
        if date_text not in valid_dates:
            return pd.DataFrame()
    csv_path = feature_grid_path(date_text)
    parquet_path = csv_path.with_suffix(".parquet")
    if parquet_path.exists():
        return pd.read_parquet(parquet_path)
    if csv_path.exists():
        return pd.read_csv(csv_path)
    return pd.DataFrame()


def sst_source_path(date_text: str) -> Path | None:
    base = cfg.DATA / "interim" / "feature_grid" / "sst"
    for name in [f"sst_features_{date_text}", f"sst_test_{date_text}"]:
        for suffix in [".parquet", ".csv"]:
            path = base / f"{name}{suffix}"
            if path.exists():
                return path
    return None


def load_verified_sst(date_text: str):
    import pandas as pd

    path = sst_source_path(date_text)
    if not path:
        return pd.DataFrame(), "missing"
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    source_cols = [col for col in df.columns if "source" in col.lower()]
    if source_cols:
        joined = " ".join(str(df[col].dropna().iloc[0]) for col in source_cols if not df[col].dropna().empty).lower()
        if "synthetic" in joined or "mock" in joined or "proxy" in joined:
            return pd.DataFrame(), "unverified_synthetic_sst"
    required = {"lat", "lon", "sst_c"}
    if not required.issubset(df.columns):
        return pd.DataFrame(), f"missing_required_columns_{sorted(required - set(df.columns))}"
    out = df.copy()
    out["lat"] = out["lat"].astype(float).round(4)
    out["lon"] = out["lon"].astype(float).round(4)
    return out, str(path.relative_to(cfg.ROOT))


def load_bathymetry():
    import pandas as pd

    base = cfg.DATA / "interim" / "feature_grid" / "bathymetry" / "bathymetry_features_0p05.csv"
    if base.exists():
        return pd.read_csv(base)
    parquet = base.with_suffix(".parquet")
    if parquet.exists():
        return pd.read_parquet(parquet)
    return pd.DataFrame()


def load_structure_points() -> list[dict[str, Any]]:
    features = []
    for path in [
        cfg.DATA / "raw" / "structure" / "fad" / "fad_points_demo.geojson",
        cfg.DATA / "raw" / "structure" / "poi" / "offshore_poi_demo.geojson",
    ]:
        if not path.exists():
            continue
        payload = load_json(path, {"features": []})
        for feature in payload.get("features", []):
            lon, lat = feature.get("geometry", {}).get("coordinates", [None, None])
            props = feature.get("properties", {})
            if lat is None or lon is None:
                continue
            features.append({"lat": float(lat), "lon": float(lon), "poi_type": props.get("poi_type", "poi"), "name": props.get("name", "")})
    return features


def nearest_structure(lat: float, lon: float, points: list[dict[str, Any]]) -> dict[str, Any]:
    if not points:
        return {
            "distance_to_nearest_fad_km": math.nan,
            "distance_to_browns_mountain_km": haversine_km(lat, lon, BROWNS[0], BROWNS[1]),
            "distance_to_nearest_poi_km": math.nan,
            "nearest_poi_type": "",
        }
    nearest = min(points, key=lambda item: haversine_km(lat, lon, item["lat"], item["lon"]))
    fad_points = [p for p in points if p["poi_type"] == "fad_demo"]
    fad_dist = min((haversine_km(lat, lon, p["lat"], p["lon"]) for p in fad_points), default=math.nan)
    return {
        "distance_to_nearest_fad_km": fad_dist,
        "distance_to_browns_mountain_km": haversine_km(lat, lon, BROWNS[0], BROWNS[1]),
        "distance_to_nearest_poi_km": haversine_km(lat, lon, nearest["lat"], nearest["lon"]),
        "nearest_poi_type": nearest["poi_type"],
    }


def grid_id(lat: float, lon: float) -> str:
    return f"{lat:.4f}_{lon:.4f}"


def seasonality(date_text: str) -> dict[str, float | int]:
    d = datetime.strptime(date_text, "%Y-%m-%d").date()
    doy = d.timetuple().tm_yday
    return {
        "year": d.year,
        "month": d.month,
        "day_of_year": doy,
        "month_sin": math.sin(2 * math.pi * d.month / 12),
        "month_cos": math.cos(2 * math.pi * d.month / 12),
        "day_of_year_sin": math.sin(2 * math.pi * doy / 365.25),
        "day_of_year_cos": math.cos(2 * math.pi * doy / 365.25),
    }
