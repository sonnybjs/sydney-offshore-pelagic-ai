from __future__ import annotations

import gzip
import importlib.util
import json
import math
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline_lib import ROOT, cfg, ensure_dirs, write_json


SPECIES = ["mahi_mahi", "southern_bluefin_tuna", "yellowtail_kingfish"]


def load_legacy_500m_module():
    path = ROOT / "pipelines" / "27_generate_500m_prediction_heatmaps.py"
    spec = importlib.util.spec_from_file_location("legacy_500m", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


legacy = load_legacy_500m_module()


def import_torch():
    try:
        import torch
    except Exception as exc:
        raise RuntimeError(
            "PyTorch is required for deep-learning inference. Install with "
            "python -m pip install -r pipelines/requirements-deep-learning.txt"
        ) from exc
    return torch


def transform_with_preprocessor(frame: pd.DataFrame, preprocessor: dict) -> np.ndarray:
    cols = preprocessor["feature_columns"]
    data = frame.copy()
    for col in cols:
        if col not in data.columns:
            data[col] = np.nan
    numeric = data[cols].apply(pd.to_numeric, errors="coerce")
    medians = pd.Series(preprocessor["medians"])
    means = pd.Series(preprocessor["means"])
    stds = pd.Series(preprocessor["stds"]).replace(0, 1.0).fillna(1.0)
    return ((numeric.fillna(medians) - means) / stds).replace([np.inf, -np.inf], 0).fillna(0).to_numpy(dtype=np.float32)


def build_mlp(torch, artifact: dict):
    import torch.nn as nn

    config = artifact["config"]
    feature_count = len(artifact["feature_columns"])
    layers = []
    previous = feature_count
    for width in config["hidden_layers"]:
        layers.extend([nn.Linear(previous, int(width)), nn.BatchNorm1d(int(width)), nn.SiLU(), nn.Dropout(float(config["dropout"]))])
        previous = int(width)
    layers.append(nn.Linear(previous, 1))
    model = nn.Sequential(*layers)
    model.load_state_dict(artifact["model_state_dict"])
    return model


def predict_deep_scores(torch, model, x: np.ndarray, device: str, batch_size: int = 4096) -> np.ndarray:
    model.eval()
    scores = []
    with torch.no_grad():
        for start in range(0, len(x), batch_size):
            batch = torch.tensor(x[start : start + batch_size], dtype=torch.float32, device=device)
            scores.append(torch.sigmoid(model(batch).squeeze(1)).detach().cpu().numpy())
    return np.concatenate(scores) if scores else np.array([], dtype=float)


def write_geojson_gz(geojson_path: Path) -> Path:
    gz_path = geojson_path.with_suffix(geojson_path.suffix + ".gz")
    with geojson_path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    return gz_path


def predict_species(species_id: str, date_text: str, grid: pd.DataFrame, torch, device: str) -> dict:
    model_path = cfg.DATA / "processed" / "deep_models" / species_id / "best_deep_mlp.pt"
    if not model_path.exists():
        return {"species_id": species_id, "date": date_text, "status": "skipped_missing_deep_model"}
    artifact = torch.load(model_path, map_location=device, weights_only=False)
    feature_columns = artifact["feature_columns"]
    missing = [col for col in feature_columns if col not in grid.columns]
    x = transform_with_preprocessor(grid, artifact["preprocessor"])
    model = build_mlp(torch, artifact).to(device)
    raw = predict_deep_scores(torch, model, x, device)
    raw_global_scores = legacy.score_to_percentile(raw)

    export_columns = [
        "date",
        "lat",
        "lon",
        "source_lat",
        "source_lon",
        "sst_c",
        "sst_gradient",
        "sst_front_strength",
        "depth_m",
        "current_speed",
        "current_direction_degrees",
        "current_edge_score",
        "zos",
        "sla_gradient",
        "distance_to_shelf_break",
        "distance_to_coast_km",
        "distance_band",
        "has_physics",
        "sst_source_date",
        "physics_source_date",
        "chl_source_date",
    ]
    working = grid.copy()
    for col in export_columns:
        if col not in working.columns:
            working[col] = np.nan
    out = working[export_columns].copy()
    out["species_id"] = species_id
    out["common_name"] = cfg.SPECIES_CONFIG[species_id]["common_name"]
    out["raw_model_score"] = raw
    out["raw_global_percentile_score"] = np.round(raw_global_scores, 2)
    min_depth = legacy.MIN_DISPLAY_DEPTH_M.get(species_id, 5)
    out["display_mask_passed"] = out["depth_m"].notna() & (out["depth_m"] >= min_depth) & out["sst_c"].notna()
    out = out[out["display_mask_passed"]].copy()
    out["score"] = np.round(legacy.contrast_score(out), 2)
    out["rating"] = out["score"].apply(legacy.rating)
    out["model_source"] = "deep_learning"
    out["model_type"] = "pytorch_mlp_binary_classifier"
    out["feature_set_name"] = "deep_mlp_tabular_oceanographic"
    out["confidence"] = "Experimental"
    out["grid_resolution_m_estimate"] = cfg.REQUESTED_RECOMMENDATION_RADIUS_M
    out["source_resolution_note"] = "500m display grid resampled from source environmental features; deep model is tabular MLP, not raster CNN."
    out["score_note"] = "Display score uses coast-distance and depth-band local ranking for visual comparison with scikit-learn output."
    out["sst_source_date"] = out["sst_source_date"].fillna(date_text) if "sst_source_date" in out.columns else date_text
    out["physics_source_date"] = out["physics_source_date"].where(out["has_physics"].fillna(False).astype(bool), None) if "physics_source_date" in out.columns else np.where(out["has_physics"].fillna(False).astype(bool), date_text, None)
    out["chl_source_date"] = out["chl_source_date"].where(out["chl_source_date"].notna(), None) if "chl_source_date" in out.columns else None
    out["top_drivers"] = "Deep MLP score from SST/front/depth/current/structure/season features where available"
    out["explanation"] = out.apply(
        lambda row: (
            f"Deep MLP score; SST {row['sst_c']:.1f}C; depth about {row['depth_m']:.0f}m; "
            f"{row['distance_to_coast_km']:.1f}km from coast proxy; "
            f"current speed {row['current_speed']:.2f}m/s" if pd.notna(row.get("current_speed")) else
            f"Deep MLP score; SST {row['sst_c']:.1f}C; depth about {row['depth_m']:.0f}m; {row['distance_to_coast_km']:.1f}km from coast proxy."
        ),
        axis=1,
    )
    out["limitations"] = "Experimental deep-learning relative habitat suitability only; not exact fish location, guaranteed fish school, or true catch probability."

    out_dir = cfg.DATA / "processed" / "predictions_500m_deep"
    out_dir.mkdir(parents=True, exist_ok=True)
    parquet_path = out_dir / f"{date_text}_{species_id}_500m_deep_sydney_heatmap.parquet"
    csv_path = out_dir / f"{date_text}_{species_id}_500m_deep_sydney_heatmap_top.csv"
    geojson_path = out_dir / f"{date_text}_{species_id}_500m_deep_sydney_heatmap_top.geojson"
    out.to_parquet(parquet_path, index=False)
    map_export = legacy.stratified_map_export(out)
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
    gz_path = write_geojson_gz(geojson_path)
    return {
        "species_id": species_id,
        "status": "written",
        "date": date_text,
        "device": device,
        "missing_features_filled": missing,
        "grid_cells": int(len(out)),
        "map_geojson_features": int(len(map_export)),
        "map_export_rating_distribution": map_export["rating"].value_counts().to_dict(),
        "parquet": str(parquet_path.relative_to(ROOT)),
        "top_csv": str(csv_path.relative_to(ROOT)),
        "top_geojson": str(geojson_path.relative_to(ROOT)),
        "top_geojson_gz": str(gz_path.relative_to(ROOT)),
    }


def main() -> None:
    ensure_dirs()
    torch = import_torch()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dates = legacy.available_prediction_grid_dates()[-10:]
    outputs = []
    for wanted_date in dates:
        date_text, grid = legacy.build_500m_grid(wanted_date)
        if not date_text or grid.empty:
            outputs.append({"date": wanted_date, "status": "skipped_no_source_grid"})
            continue
        for species_id in SPECIES:
            print(f"deep inference date={date_text} species={species_id} device={device}", flush=True)
            outputs.append(predict_species(species_id, date_text, grid, torch, device))
    summary = {
        "status": "completed",
        "model_source": "deep_learning",
        "dates": dates,
        "species": SPECIES,
        "device": device,
        "outputs": outputs,
        "limitations": [
            "Deep-learning model is an experimental sidecar model.",
            "500m output is relative habitat suitability only, not exact fish location or catch probability.",
        ],
    }
    write_json(cfg.DATA / "processed" / "predictions_500m_deep" / "prediction_500m_deep_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
