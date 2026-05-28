from __future__ import annotations

import math

from pipeline_lib import append_provenance, cfg, ensure_dirs, file_size_mb, write_json
from training_prep_lib import (
    ENV_COLUMNS,
    feature_grid_path,
    grid_id,
    load_all_best_occurrences,
    load_bathymetry,
    load_structure_points,
    load_verified_sst,
    nearest_structure,
    seasonality,
)

PRINTED_SUPPLEMENT_CHECKS = 0
MAX_SUPPLEMENT_CHECK_PRINTS = 5


def weather_cell(value: float) -> float:
    return round(round(float(value) / 0.5) * 0.5, 4)


def load_lunar_features():
    import pandas as pd

    path = cfg.DATA / "interim" / "feature_grid" / "lunar" / "lunar_features_by_date.csv"
    parquet = path.with_suffix(".parquet")
    if parquet.exists():
        return pd.read_parquet(parquet)
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def load_weather_features():
    import pandas as pd

    path = cfg.DATA / "interim" / "feature_grid" / "weather" / "open_meteo_weather_features.csv"
    parquet = path.with_suffix(".parquet")
    if parquet.exists():
        return pd.read_parquet(parquet)
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def load_physics_features(date_text: str):
    import pandas as pd

    path = cfg.DATA / "interim" / "feature_grid" / "physics" / f"physics_features_{date_text}.csv"
    parquet = path.with_suffix(".parquet")
    if parquet.exists():
        return pd.read_parquet(parquet)
    if path.exists():
        return pd.read_csv(path)
    return pd.DataFrame()


def supplementary_sst_check(date_text: str, reason: str) -> dict:
    global PRINTED_SUPPLEMENT_CHECKS
    payload = {
        "title": "SUPPLEMENTARY DATA DOWNLOAD CHECK",
        "missing_dataset": "NASA MUR SST v4.1",
        "reason": reason,
        "proposed_replacement_source": "NASA MUR official ERDDAP/OPeNDAP/cloud subset route",
        "exact_bbox": cfg.TRAIN_BBOX,
        "exact_date_range": [date_text, date_text],
        "variables": ["analysed_sst"],
        "estimated_size": "<50 MB per date if remote subset is available",
        "destination_path": f"data/interim/feature_grid/sst/sst_features_{date_text}.csv",
        "affects": "required dynamic environmental feature",
        "leakage_risk": "no future dates allowed; same date or previous-date fallback only",
        "under_10gb": True,
        "action": "No automatic bulk download attempted because verified MUR endpoint is not configured. Date will be skipped for v1 training.",
    }
    if PRINTED_SUPPLEMENT_CHECKS < MAX_SUPPLEMENT_CHECK_PRINTS:
        print(payload)
    elif PRINTED_SUPPLEMENT_CHECKS == MAX_SUPPLEMENT_CHECK_PRINTS:
        print(
            {
                "title": "SUPPLEMENTARY DATA DOWNLOAD CHECK",
                "message": "Further missing-SST checks suppressed in console; full per-date details are written to daily_features_training_prep_summary.json.",
            }
        )
    PRINTED_SUPPLEMENT_CHECKS += 1
    return payload


def save_daily_grid(df, date_text: str) -> dict:
    out = feature_grid_path(date_text).with_suffix(".parquet")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    return {"parquet": str(out.relative_to(cfg.ROOT)), "parquet_size_mb": file_size_mb(out)}


def build_static_features(bathy, structures):
    import pandas as pd

    if not bathy.empty:
        static = bathy.copy()
        static["lat"] = static["lat"].astype(float).round(4)
        static["lon"] = static["lon"].astype(float).round(4)
    else:
        static = pd.DataFrame()
    if not static.empty:
        structure_rows = [nearest_structure(float(row.lat), float(row.lon), structures) for row in static.itertuples()]
        structure_df = pd.DataFrame(structure_rows)
        static = pd.concat([static.reset_index(drop=True), structure_df.reset_index(drop=True)], axis=1)
        static["has_structure"] = bool(structures)
    return static


def build_grid_for_date(date_text: str, static, lunar, weather) -> tuple[object | None, dict]:
    import pandas as pd

    sst, sst_status = load_verified_sst(date_text)
    if sst.empty:
        return None, {"date": date_text, "status": "skipped_missing_required_sst", "sst_status": sst_status, "supplement_check": supplementary_sst_check(date_text, sst_status)}

    sst = sst.copy()
    if "date" not in sst.columns:
        sst["date"] = date_text
    for col in ["sst_gradient", "sst_front_strength", "sst_3d_change", "sst_7d_change"]:
        if col not in sst.columns:
            sst[col] = math.nan
    sst["grid_id"] = [grid_id(lat, lon) for lat, lon in zip(sst["lat"], sst["lon"])]

    grid = sst[["date", "lat", "lon", "grid_id", "sst_c", "sst_gradient", "sst_front_strength", "sst_3d_change", "sst_7d_change"]].copy()
    grid["sst_missing_flag"] = grid["sst_c"].isna()
    grid["sst_source_date"] = date_text
    grid["sst_date_offset_days"] = 0

    if not static.empty:
        grid = grid.merge(static, on=["lat", "lon"], how="left")
        grid["has_bathymetry"] = grid["depth_m"].notna()
    else:
        for col in ["depth_m", "slope", "distance_to_200m_contour", "distance_to_500m_contour", "distance_to_1000m_contour", "distance_to_shelf_break"]:
            grid[col] = math.nan
        grid["ocean_mask"] = math.nan
        grid["has_bathymetry"] = False
        grid["ocean_mask_unknown"] = True
        for col in ["distance_to_nearest_fad_km", "distance_to_browns_mountain_km", "distance_to_nearest_poi_km", "nearest_poi_type"]:
            grid[col] = math.nan if col != "nearest_poi_type" else ""
        grid["has_structure"] = False

    physics = load_physics_features(date_text)
    physics_cols = ["uo", "vo", "current_speed", "current_direction_degrees", "current_edge_score", "zos", "sla_gradient", "eddy_score"]
    if not physics.empty:
        keep_cols = ["date", "lat", "lon"] + [col for col in physics_cols + ["physics_missing_flag", "physics_source_date", "physics_date_offset_days", "has_physics"] if col in physics.columns]
        physics = physics[keep_cols].copy()
        physics["lat"] = physics["lat"].astype(float).round(4)
        physics["lon"] = physics["lon"].astype(float).round(4)
        grid = grid.merge(physics, on=["date", "lat", "lon"], how="left")
        for col in physics_cols:
            if col not in grid.columns:
                grid[col] = math.nan
        grid["physics_missing_flag"] = grid.get("physics_missing_flag", True).fillna(True)
        grid["physics_source_date"] = grid.get("physics_source_date", "").fillna("")
        grid["physics_date_offset_days"] = grid.get("physics_date_offset_days", math.nan)
        grid["has_physics"] = grid[["uo", "vo", "current_speed"]].notna().any(axis=1)
    else:
        for col in physics_cols:
            grid[col] = math.nan
        grid["physics_missing_flag"] = True
        grid["physics_source_date"] = ""
        grid["physics_date_offset_days"] = math.nan
        grid["has_physics"] = False

    for col in ["chl", "chl_log", "chl_gradient", "chl_edge_score"]:
        grid[col] = math.nan
    grid["chl_missing_flag"] = True
    grid["chl_source_date"] = ""
    grid["chl_date_offset_days"] = math.nan
    grid["has_chl"] = False

    for key, value in seasonality(date_text).items():
        grid[key] = value

    if not lunar.empty:
        lunar_row = lunar[lunar["date"].astype(str) == date_text]
        if not lunar_row.empty:
            for col in ["moon_age_days", "moon_phase_fraction", "moon_illumination", "moon_phase_sin", "moon_phase_cos"]:
                grid[col] = float(lunar_row.iloc[0][col])
            grid["moon_phase_label"] = str(lunar_row.iloc[0].get("moon_phase_label", ""))
            grid["has_lunar"] = True
        else:
            for col in ["moon_age_days", "moon_phase_fraction", "moon_illumination", "moon_phase_sin", "moon_phase_cos"]:
                grid[col] = math.nan
            grid["moon_phase_label"] = ""
            grid["has_lunar"] = False
    else:
        for col in ["moon_age_days", "moon_phase_fraction", "moon_illumination", "moon_phase_sin", "moon_phase_cos"]:
            grid[col] = math.nan
        grid["moon_phase_label"] = ""
        grid["has_lunar"] = False

    weather_cols = [
        "surface_pressure_hpa_mean",
        "surface_pressure_hpa_min",
        "surface_pressure_hpa_max",
        "pressure_msl_hpa_mean",
        "wind_speed_10m_kmh_mean",
        "wind_speed_10m_kmh_max",
        "precipitation_mm_sum",
        "wind_direction_10m_deg_circular_mean",
    ]
    grid["weather_lat"] = grid["lat"].apply(weather_cell)
    grid["weather_lon"] = grid["lon"].apply(weather_cell)
    if not weather.empty:
        w = weather[weather["date"].astype(str) == date_text].copy()
        if not w.empty:
            grid = grid.merge(w[["date", "weather_lat", "weather_lon"] + weather_cols], on=["date", "weather_lat", "weather_lon"], how="left")
            grid["has_weather"] = grid["surface_pressure_hpa_mean"].notna()
        else:
            for col in weather_cols:
                grid[col] = math.nan
            grid["has_weather"] = False
    else:
        for col in weather_cols:
            grid[col] = math.nan
        grid["has_weather"] = False

    for col in ["o2", "dissolved_oxygen", "oxygen_saturation"]:
        grid[col] = math.nan
    grid["oxygen_missing_flag"] = True
    grid["has_oxygen"] = False

    grid["has_sst"] = grid["sst_c"].notna()
    grid["feature_set_name"] = grid.apply(
        lambda row: "sst_bathy_structure" if row["has_bathymetry"] and row["has_structure"] else "sst_bathy_only" if row["has_bathymetry"] else "sst_only",
        axis=1,
    )
    if "ocean_mask" in grid.columns and grid["ocean_mask"].notna().any():
        grid = grid[(grid["ocean_mask"].isna()) | (grid["ocean_mask"].astype(bool))]
    return grid, {"date": date_text, "status": "built", "cells": int(len(grid)), "feature_set": sorted(grid["feature_set_name"].dropna().unique().tolist())}


def main() -> None:
    ensure_dirs()
    occurrences = load_all_best_occurrences()
    dates = sorted(occurrences["date"].dropna().unique().tolist()) if not occurrences.empty else []
    bathy = load_bathymetry()
    structures = load_structure_points()
    static = build_static_features(bathy, structures)
    lunar = load_lunar_features()
    weather = load_weather_features()
    summary = {"dates_requested": len(dates), "built": 0, "skipped": 0, "items": []}
    for date_text in dates:
        df, item = build_grid_for_date(date_text, static, lunar, weather)
        if df is None or df.empty:
            summary["skipped"] += 1
            summary["items"].append(item)
            continue
        outputs = save_daily_grid(df, date_text)
        item["outputs"] = outputs
        summary["built"] += 1
        summary["items"].append(item)
        append_provenance(
            {
                "dataset_name": f"daily_feature_grid_{date_text}",
                "source_name": "Prepared local feature grid",
                "source_url_or_access_method": "Local aligned SST/bathymetry/structure files",
                "spatial_bbox": cfg.TRAIN_BBOX,
                "time_range": date_text,
                "variables": ",".join([c for c in df.columns if c in ENV_COLUMNS]),
                "raw_file_path": "",
                "processed_file_path": outputs.get("csv", ""),
                "estimated_size_mb": "<50",
                "actual_size_mb": outputs.get("csv_size_mb", ""),
                "license_or_terms_note": "Derived local training feature table; source licenses inherited from inputs",
                "used_for_training": True,
                "notes": "Dynamic SST must match date; optional physics/chl are NaN when unavailable.",
            }
        )
    write_json(cfg.DATA / "interim" / "feature_grid" / "daily_features_training_prep_summary.json", summary)
    compact_summary = {key: value for key, value in summary.items() if key != "items"}
    compact_summary["items_detail_path"] = "data/interim/feature_grid/daily_features_training_prep_summary.json"
    print(compact_summary)


if __name__ == "__main__":
    main()
