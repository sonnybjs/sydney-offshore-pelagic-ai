from __future__ import annotations

import json
import math
import os

import numpy as np
import pandas as pd

from pipeline_lib import cfg, ensure_dirs, in_bbox, nearest_grid_value, read_table, write_json
from modeling_lib import species_dir
from training_prep_lib import feature_grid_path


SPECIES = ["mahi_mahi", "southern_bluefin_tuna", "yellowtail_kingfish"]
MAX_GEOJSON_FEATURES = 24000
RATING_EXPORT_LIMITS = {
    "Prime": 5000,
    "Good": 6000,
    "Possible": 8000,
    "Low": 5000,
}
MIN_DISPLAY_DEPTH_M = {
    "mahi_mahi": 8,
    "southern_bluefin_tuna": 50,
    "yellowtail_kingfish": 5,
}
COASTLINE_PROXY = [
    (-36.5, 150.72),
    (-35.1, 150.78),
    (-34.2, 151.16),
    (-33.6, 151.34),
    (-32.0, 151.82),
]


def available_prediction_grid_dates() -> list[str]:
    path = cfg.DATA / "interim" / "feature_grid" / "daily_features_training_prep_summary.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return sorted([item["date"] for item in payload.get("items", []) if item.get("status") == "built"])


def high_res_points() -> pd.DataFrame:
    rows = []
    res = cfg.HIGH_RES_PREDICT_GRID_RESOLUTION_DEG
    lat = cfg.PREDICT_BBOX["south_lat"]
    while lat <= cfg.PREDICT_BBOX["north_lat"] + 1e-12:
        lon = cfg.PREDICT_BBOX["west_lon"]
        while lon <= cfg.PREDICT_BBOX["east_lon"] + 1e-12:
            rows.append({"lat": round(lat, 4), "lon": round(lon, 4)})
            lon += res
        lat += res
    return pd.DataFrame(rows)


def load_source_grid(date_text: str | None = None) -> tuple[str, pd.DataFrame]:
    candidates = [date_text] if date_text else list(reversed(available_prediction_grid_dates()))
    for candidate in candidates:
        if not candidate:
            continue
        grid = read_table(feature_grid_path(candidate))
        if grid.empty:
            continue
        grid = grid.copy()
        grid = grid[grid.apply(lambda row: in_bbox(float(row["lat"]), float(row["lon"]), cfg.PREDICT_BBOX), axis=1)]
        if not grid.empty:
            return candidate, grid
    return "", pd.DataFrame()


def coast_lon_for_lat(lat: float) -> float:
    points = sorted(COASTLINE_PROXY)
    if lat <= points[0][0]:
        return points[0][1]
    if lat >= points[-1][0]:
        return points[-1][1]
    for (lat0, lon0), (lat1, lon1) in zip(points[:-1], points[1:]):
        if lat0 <= lat <= lat1:
            t = (lat - lat0) / (lat1 - lat0)
            return lon0 + (lon1 - lon0) * t
    return points[-1][1]


def add_coast_distance(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    coast_lon = out["lat"].astype(float).apply(coast_lon_for_lat)
    km_per_lon = 111.32 * np.cos(np.radians(out["lat"].astype(float)))
    out["coast_lon_proxy"] = coast_lon
    out["distance_to_coast_km"] = ((out["lon"].astype(float) - coast_lon) * km_per_lon).clip(lower=0)
    out["distance_band"] = pd.cut(
        out["distance_to_coast_km"],
        bins=[-0.1, 20, 50, 100, 1000],
        labels=["nearshore_0_20km", "mid_20_50km", "offshore_50_100km", "far_offshore_100km_plus"],
    ).astype(str)
    return out


def build_500m_grid(date_text: str | None = None) -> tuple[str, pd.DataFrame]:
    date_text, source = load_source_grid(date_text)
    if source.empty:
        return "", source
    source = source.copy()
    source["source_lat"] = source["lat"].astype(float).round(4)
    source["source_lon"] = source["lon"].astype(float).round(4)
    keep_cols = [c for c in source.columns if c not in {"grid_lat", "grid_lon"}]
    source = source[keep_cols].drop_duplicates(["source_lat", "source_lon"])

    high = high_res_points()
    high["source_lat"] = high["lat"].apply(lambda value: nearest_grid_value(value, cfg.PREDICT_GRID_RESOLUTION_DEG))
    high["source_lon"] = high["lon"].apply(lambda value: nearest_grid_value(value, cfg.PREDICT_GRID_RESOLUTION_DEG))
    merged = high.merge(source, on=["source_lat", "source_lon"], how="left", suffixes=("", "_source"))
    for col in ["date", "grid_id"]:
        if f"{col}_source" in merged.columns:
            merged[col] = merged[f"{col}_source"]
    for col in ["lat_source", "lon_source"]:
        if col in merged.columns:
            merged = merged.drop(columns=[col])
    merged["date"] = date_text
    merged["grid_lat"] = merged["lat"]
    merged["grid_lon"] = merged["lon"]
    merged["high_res_grid_resolution_deg"] = cfg.HIGH_RES_PREDICT_GRID_RESOLUTION_DEG
    merged["high_res_grid_resolution_m_estimate"] = cfg.REQUESTED_RECOMMENDATION_RADIUS_M
    merged["source_feature_resolution_deg"] = cfg.PREDICT_GRID_RESOLUTION_DEG
    return date_text, add_coast_distance(merged)


def score_to_percentile(scores) -> np.ndarray:
    s = np.asarray(scores, dtype=float)
    if len(s) == 0:
        return s
    if np.nanmax(s) - np.nanmin(s) < 1e-12:
        return np.full_like(s, 50.0)
    order = s.argsort(kind="mergesort")
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(len(s), dtype=float)
    return ranks / max(1, len(s) - 1) * 100


def percentile_series(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.notna()
    output = pd.Series(np.nan, index=values.index, dtype=float)
    if valid.sum() == 0:
        return output
    if numeric[valid].max() - numeric[valid].min() < 1e-12:
        output.loc[valid] = 50.0
        return output
    output.loc[valid] = numeric[valid].rank(method="first", pct=True) * 100.0
    return output


def contrast_score(out: pd.DataFrame) -> pd.Series:
    """Use local depth-band ranking so nearshore cells are not all the same colour."""
    global_pct = percentile_series(out["raw_model_score"])
    depth_bins = [-1, 20, 50, 100, 200, 500, 1000, 2000, 7000]
    depth_band = pd.cut(out["depth_m"], bins=depth_bins, labels=False, include_lowest=True)
    local_pct = out.groupby(depth_band, observed=True)["raw_model_score"].transform(percentile_series)
    coast_pct = out.groupby(out["distance_band"], observed=True)["raw_model_score"].transform(percentile_series)
    front_pct = percentile_series(out.get("sst_front_strength", pd.Series(np.nan, index=out.index))).fillna(50)
    current_pct = percentile_series(out.get("current_edge_score", pd.Series(np.nan, index=out.index))).fillna(50)
    local_pct = local_pct.fillna(global_pct).fillna(50)
    coast_pct = coast_pct.fillna(local_pct).fillna(50)
    global_pct = global_pct.fillna(50)
    focus_weight = pd.cut(
        out["distance_to_coast_km"],
        bins=[-0.1, 20, 50, 100, 1000],
        labels=[1.0, 0.9, 0.68, 0.48],
    ).astype(float).fillna(0.75)
    score = 0.58 * coast_pct + 0.20 * local_pct + 0.12 * global_pct + 0.06 * front_pct + 0.04 * current_pct
    score = score * focus_weight
    return score.clip(0, 100)


def rating(score: float) -> str:
    if score >= 95:
        return "Prime"
    if score >= 85:
        return "Good"
    if score >= 60:
        return "Possible"
    return "Low"


def stratified_map_export(out: pd.DataFrame) -> pd.DataFrame:
    """Keep the browser payload bounded without exporting only top-ranked cells."""
    pieces = []
    for rating_name, limit in RATING_EXPORT_LIMITS.items():
        group = out[out["rating"] == rating_name]
        if group.empty:
            continue
        if len(group) <= limit:
            pieces.append(group)
            continue
        pieces.append(group.sample(n=limit, random_state=42).sort_values("score", ascending=False))
    if not pieces:
        return out.head(0).copy()
    exported = pd.concat(pieces, ignore_index=True)
    exported = exported.sort_values("score", ascending=False)
    return exported.head(MAX_GEOJSON_FEATURES).copy()


def predict_species(species_id: str, date_text: str, grid: pd.DataFrame) -> dict:
    import joblib

    model_path = species_dir(species_id) / "best_model.joblib"
    metadata_path = species_dir(species_id) / "model_metadata.json"
    if not model_path.exists() or not metadata_path.exists():
        return {"species_id": species_id, "status": "skipped_missing_model"}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("status") != "selected":
        return {"species_id": species_id, "status": "skipped_model_not_selected"}
    bundle = joblib.load(model_path)
    feature_columns = bundle["feature_columns"]
    missing = [col for col in feature_columns if col not in grid.columns]
    if missing:
        return {"species_id": species_id, "status": "skipped_missing_features", "missing": missing}
    raw = bundle["model"].predict_proba(grid[feature_columns])[:, 1]
    raw_global_scores = score_to_percentile(raw)
    export_columns = ["date", "lat", "lon", "source_lat", "source_lon", "sst_c", "sst_gradient", "sst_front_strength", "depth_m", "current_speed", "current_direction_degrees", "current_edge_score", "zos", "sla_gradient", "distance_to_shelf_break", "distance_to_coast_km", "distance_band", "has_physics", "sst_source_date", "physics_source_date", "chl_source_date"]
    for col in export_columns:
        if col not in grid.columns:
            grid[col] = np.nan
    out = grid[export_columns].copy()
    out["species_id"] = species_id
    out["common_name"] = cfg.SPECIES_CONFIG[species_id]["common_name"]
    out["raw_model_score"] = raw
    out["raw_global_percentile_score"] = np.round(raw_global_scores, 2)
    min_depth = MIN_DISPLAY_DEPTH_M.get(species_id, 5)
    out["display_mask_passed"] = out["depth_m"].notna() & (out["depth_m"] >= min_depth) & out["sst_c"].notna()
    out = out[out["display_mask_passed"]].copy()
    out["score"] = np.round(contrast_score(out), 2)
    out["rating"] = out["score"].apply(rating)
    out["model_type"] = metadata.get("model_type")
    out["feature_set_name"] = metadata.get("feature_set_name")
    out["confidence"] = metadata.get("confidence_level", "Low")
    out["grid_resolution_m_estimate"] = cfg.REQUESTED_RECOMMENDATION_RADIUS_M
    out["source_resolution_note"] = "500m display grid resampled from source environmental features; not exact fish position."
    out["score_note"] = "Display score uses coast-distance and depth-band local ranking, with nearshore 0-20km prioritised and far offshore downweighted."
    out["sst_source_date"] = out["sst_source_date"].fillna(date_text) if "sst_source_date" in out.columns else date_text
    out["physics_source_date"] = out["physics_source_date"].where(out["has_physics"].fillna(False).astype(bool), None) if "physics_source_date" in out.columns else np.where(out["has_physics"].fillna(False).astype(bool), date_text, None)
    out["chl_source_date"] = out["chl_source_date"].where(out["chl_source_date"].notna(), None) if "chl_source_date" in out.columns else None
    out["top_drivers"] = "SST, SST front proxy, depth band, coast-distance band, current edge if available"
    out["explanation"] = out.apply(
        lambda row: (
            f"SST {row['sst_c']:.1f}C; depth about {row['depth_m']:.0f}m; "
            f"{row['distance_to_coast_km']:.1f}km from coast proxy; "
            f"current speed {row['current_speed']:.2f}m/s" if pd.notna(row.get("current_speed")) else
            f"SST {row['sst_c']:.1f}C; depth about {row['depth_m']:.0f}m; {row['distance_to_coast_km']:.1f}km from coast proxy."
        ),
        axis=1,
    )
    out["limitations"] = "Relative habitat suitability only; not exact fish location, guaranteed fish school, or true catch probability."

    out_dir = cfg.DATA / "processed" / "predictions_500m"
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / f"{date_text}_{species_id}_500m_sydney_heatmap.parquet"
    csv_path = out_dir / f"{date_text}_{species_id}_500m_sydney_heatmap_top.csv"
    geojson_path = out_dir / f"{date_text}_{species_id}_500m_sydney_heatmap_top.geojson"
    out.to_parquet(parquet_path, index=False)
    map_export = stratified_map_export(out)
    map_export.to_csv(csv_path, index=False)
    features = []
    for row in map_export.to_dict("records"):
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
                "properties": {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in row.items() if k not in {"lat", "lon"}},
            }
        )
    write_json(geojson_path, {"type": "FeatureCollection", "features": features})
    return {
        "species_id": species_id,
        "status": "written",
        "date": date_text,
        "grid_cells": int(len(out)),
        "map_geojson_features": int(len(map_export)),
        "map_export_rating_distribution": map_export["rating"].value_counts().to_dict(),
        "parquet": str(parquet_path.relative_to(cfg.ROOT)),
        "top_csv": str(csv_path.relative_to(cfg.ROOT)),
        "top_geojson": str(geojson_path.relative_to(cfg.ROOT)),
    }


def main() -> None:
    ensure_dirs()
    date_count = int(os.environ.get("DEMO_500M_DATE_COUNT", "10"))
    dates = available_prediction_grid_dates()[-date_count:]
    all_outputs = []
    if not dates:
        summary = {"status": "skipped", "reason": "no source prediction grid available"}
    else:
        grid_cells = 0
        for wanted_date in dates:
            date_text, grid = build_500m_grid(wanted_date)
            if not date_text or grid.empty:
                all_outputs.append({"date": wanted_date, "status": "skipped_no_source_grid"})
                continue
            grid_cells = int(len(grid))
            all_outputs.extend([predict_species(species_id, date_text, grid) for species_id in SPECIES])
        summary = {
            "status": "completed",
            "dates": dates,
            "resolution_deg": cfg.HIGH_RES_PREDICT_GRID_RESOLUTION_DEG,
            "resolution_m_estimate": cfg.REQUESTED_RECOMMENDATION_RADIUS_M,
            "source_feature_resolution_deg": cfg.PREDICT_GRID_RESOLUTION_DEG,
            "grid_cells": grid_cells,
            "outputs": all_outputs,
            "limitations": [
                "500m grid is a display/recommendation grid using resampled source features.",
                "This is relative habitat suitability, not exact fish location or true catch probability.",
            ],
        }
    write_json(cfg.DATA / "processed" / "predictions_500m" / "prediction_500m_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
