from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from pipeline_lib import cfg, ensure_dirs, file_size_mb, format_bbox, write_json


TARGET_SPECIES = ["mahi_mahi", "southern_bluefin_tuna", "yellowtail_kingfish", "yellowfin_tuna", "striped_marlin"]
CURRENT_COLUMNS = ["uo", "vo", "current_speed", "current_direction_degrees", "current_edge_score", "zos", "sla_gradient", "eddy_score"]


def count_grid_cells(bbox: dict[str, float], resolution: float) -> int:
    lat_count = math.floor((bbox["north_lat"] - bbox["south_lat"]) / resolution) + 1
    lon_count = math.floor((bbox["east_lon"] - bbox["west_lon"]) / resolution) + 1
    return lat_count * lon_count


def read_training(species_id: str) -> pd.DataFrame:
    base = cfg.DATA / "processed" / "training" / f"{species_id}_training_samples"
    parquet = base.with_suffix(".parquet")
    csv = base.with_suffix(".csv")
    if parquet.exists():
        return pd.read_parquet(parquet)
    if csv.exists():
        return pd.read_csv(csv)
    return pd.DataFrame()


def inspect_species(species_id: str) -> dict:
    df = read_training(species_id)
    if df.empty:
        return {"species_id": species_id, "status": "missing_or_empty_training_dataset"}
    presence = int((df.get("label") == 1).sum()) if "label" in df.columns else 0
    background = int((df.get("label") == 0).sum()) if "label" in df.columns else 0
    current_non_null = {col: int(df[col].notna().sum()) if col in df.columns else 0 for col in CURRENT_COLUMNS}
    has_any_current = any(value > 0 for value in current_non_null.values())
    return {
        "species_id": species_id,
        "rows": int(len(df)),
        "presence": presence,
        "background": background,
        "current_non_null_counts": current_non_null,
        "has_real_current_features": has_any_current,
        "has_physics_values": sorted(df["has_physics"].dropna().astype(str).unique().tolist()) if "has_physics" in df.columns else [],
        "physics_missing_values": sorted(df["physics_missing_flag"].dropna().astype(str).unique().tolist()) if "physics_missing_flag" in df.columns else [],
        "trainability_for_current_retrain": "blocked_missing_current_features" if not has_any_current else "ready_for_current_feature_retrain",
    }


def make_report(summary: dict) -> str:
    lines = [
        "# Current Data and 500m Upgrade Audit",
        "",
        f"Generated: {summary['generated_at']}",
        "",
        "This report checks whether the existing training datasets can honestly be retrained with ocean-current predictors and whether the requested 500m prediction grid is feasible.",
        "",
        "The model output remains relative habitat suitability / hotspot score, not exact fish location or guaranteed catch probability.",
        "",
        "## Spatial Scope",
        "",
        f"- Prediction bbox: {format_bbox(cfg.PREDICT_BBOX)}",
        f"- Training bbox: {format_bbox(cfg.TRAIN_BBOX)}",
        f"- Current production grid: {cfg.PREDICT_GRID_RESOLUTION_DEG} degrees, about 5 km",
        f"- Requested high-resolution grid: {cfg.HIGH_RES_PREDICT_GRID_RESOLUTION_DEG} degrees, about 500 m latitude spacing",
        "",
        "## 500m Grid Estimate",
        "",
        f"- Prediction cells at 0.05 degrees: {summary['grid_estimate']['prediction_cells_0p05']:,}",
        f"- Prediction cells at 0.005 degrees: {summary['grid_estimate']['prediction_cells_0p005']:,}",
        f"- Training corridor cells at 0.005 degrees per date: {summary['grid_estimate']['training_cells_0p005_per_date']:,}",
        "",
        "A 500m prediction map is feasible for Sydney display, but a true 500m training dataset across 1,000 dates would be very large. It must use real high-resolution environmental features, not interpolation from the current 5km training grid.",
        "",
        "## Current Feature Status",
        "",
        "| Species | Rows | Presence | Current features available? | Retrain status |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for item in summary["species"]:
        lines.append(
            f"| {item['species_id']} | {item.get('rows', 0):,} | {item.get('presence', 0):,} | "
            f"{'yes' if item.get('has_real_current_features') else 'no'} | {item.get('trainability_for_current_retrain', item.get('status'))} |"
        )
    lines.extend(
        [
            "",
            "## Decision",
            "",
            f"- Can retrain with real current data now: **{'yes' if summary['can_retrain_with_currents_now'] else 'no'}**",
            "- Reason: existing training datasets contain no non-null `uo`, `vo`, `current_speed`, `current_edge_score`, `zos`, `sla_gradient`, or `eddy_score` values.",
            "- The Copernicus physics downloader is currently a setup/credentials stub. It has not produced feature files for occurrence dates.",
            "",
            "## Required Next Step",
            "",
            "1. Configure a real Copernicus Marine subset access method for surface-only East Coast physics.",
            "2. Download only occurrence-aligned dates and bbox subsets.",
            "3. Rebuild daily feature grids so current columns are non-null.",
            "4. Rebuild presence/background training samples.",
            "5. Retrain and audit corrected models.",
            "6. Generate a 500m Sydney prediction grid only from real or source-resolution-supported features.",
            "",
            "Do not treat a 500m interpolation from the old 5km grid as increased model precision.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    ensure_dirs()
    species = [inspect_species(species_id) for species_id in TARGET_SPECIES]
    prediction_cells_0p05 = count_grid_cells(cfg.PREDICT_BBOX, cfg.PREDICT_GRID_RESOLUTION_DEG)
    prediction_cells_0p005 = count_grid_cells(cfg.PREDICT_BBOX, cfg.HIGH_RES_PREDICT_GRID_RESOLUTION_DEG)
    training_cells_0p005 = count_grid_cells(cfg.TRAIN_BBOX, cfg.HIGH_RES_TRAIN_GRID_RESOLUTION_DEG)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "audit current-feature availability and 500m grid feasibility before retraining",
        "prediction_bbox": cfg.PREDICT_BBOX,
        "training_bbox": cfg.TRAIN_BBOX,
        "requested_recommendation_radius_m": cfg.REQUESTED_RECOMMENDATION_RADIUS_M,
        "grid_estimate": {
            "prediction_resolution_deg_current": cfg.PREDICT_GRID_RESOLUTION_DEG,
            "prediction_resolution_deg_requested": cfg.HIGH_RES_PREDICT_GRID_RESOLUTION_DEG,
            "prediction_cells_0p05": prediction_cells_0p05,
            "prediction_cells_0p005": prediction_cells_0p005,
            "training_cells_0p005_per_date": training_cells_0p005,
            "note": "500m prediction is display-feasible; 500m training over all dates is large and must use real source features.",
        },
        "species": species,
        "can_retrain_with_currents_now": any(item.get("has_real_current_features") for item in species),
        "blocking_reason": "No non-null ocean-current/physics features exist in current training datasets.",
        "required_sources": {
            "currents": "Copernicus Marine surface-only bbox/date subset for uo, vo, zos",
            "sst": "NASA MUR SST subset; raw resolution is about 0.01 degree, so 500m display may be interpolated unless higher-resolution source exists.",
            "bathymetry": "GEBCO subset; can support finer static depth features if processed at finer grid.",
        },
    }
    out_json = cfg.DATA / "processed" / "reports" / "current_500m_upgrade_audit.json"
    out_md = cfg.DATA / "processed" / "reports" / "CURRENT_500M_UPGRADE_AUDIT.md"
    write_json(out_json, summary)
    out_md.write_text(make_report(summary), encoding="utf-8")
    print(json.dumps({"status": "written", "json": str(out_json), "md": str(out_md), "json_size_mb": file_size_mb(out_json)}, indent=2))


if __name__ == "__main__":
    main()
