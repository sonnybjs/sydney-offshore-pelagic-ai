from __future__ import annotations

import json

from pipeline_lib import cfg, ensure_dirs, in_bbox, read_table, save_dataframe, write_json
from modeling_lib import TARGET_SPECIES, rating_from_score, species_dir
from training_prep_lib import feature_grid_path


def available_prediction_grid_dates() -> list[str]:
    summary_path = cfg.DATA / "interim" / "feature_grid" / "daily_features_training_prep_summary.json"
    if not summary_path.exists():
        return []
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    return sorted([item["date"] for item in payload.get("items", []) if item.get("status") == "built"])


def load_prediction_grid():
    import pandas as pd

    dates = available_prediction_grid_dates()
    for date_text in reversed(dates):
        grid = read_table(feature_grid_path(date_text))
        if grid.empty:
            continue
        grid = grid.copy()
        grid = grid[
            grid.apply(lambda row: in_bbox(float(row["lat"]), float(row["lon"]), cfg.PREDICT_BBOX), axis=1)
        ]
        if not grid.empty:
            if "grid_lat" not in grid.columns:
                grid["grid_lat"] = grid["lat"]
            if "grid_lon" not in grid.columns:
                grid["grid_lon"] = grid["lon"]
            return date_text, grid
    return None, pd.DataFrame()


def score_to_relative_0_100(scores):
    import numpy as np

    s = np.asarray(scores, dtype=float)
    if len(s) == 0:
        return s
    if np.nanmax(s) - np.nanmin(s) < 1e-9:
        return np.full_like(s, 50.0)
    ranks = s.argsort().argsort()
    return ranks / max(1, len(s) - 1) * 100


def explain_row(row, feature_columns: list[str]) -> tuple[list[str], list[str]]:
    drivers = []
    explanations = []
    if "sst_c" in feature_columns and row.get("sst_c") is not None:
        drivers.append("sst_c")
        explanations.append("SST is included as a core habitat suitability feature.")
    if "sst_front_strength" in feature_columns:
        drivers.append("sst_front_strength")
        explanations.append("SST front strength contributes to the relative hotspot score.")
    if "distance_to_shelf_break" in feature_columns:
        drivers.append("distance_to_shelf_break")
        explanations.append("Shelf-break proximity is represented in the model features.")
    if "distance_to_nearest_fad_km" in feature_columns:
        drivers.append("distance_to_nearest_fad_km")
        explanations.append("FAD/structure proximity is included where available.")
    if "month_sin" in feature_columns or "month_cos" in feature_columns:
        drivers.append("seasonality")
        explanations.append("Seasonal timing is included via cyclic date features.")
    return drivers[:5], explanations or ["Relative suitability estimated from available environmental predictors."]


def predict_species(species_id: str, date_text: str, grid) -> dict:
    import joblib
    import pandas as pd

    metadata_path = species_dir(species_id) / "model_metadata.json"
    model_path = species_dir(species_id) / "best_model.joblib"
    if not metadata_path.exists() or not model_path.exists():
        return {"species_id": species_id, "status": "skipped_no_selected_model"}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("status") != "selected":
        return {"species_id": species_id, "status": "skipped_model_not_selected", "reason": metadata.get("reason")}
    bundle = joblib.load(model_path)
    feature_columns = bundle["feature_columns"]
    missing = [col for col in feature_columns if col not in grid.columns]
    if missing:
        return {"species_id": species_id, "status": "skipped_missing_prediction_features", "missing": missing}
    model = bundle["model"]
    raw_scores = model.predict_proba(grid[feature_columns])[:, 1]
    relative_scores = score_to_relative_0_100(raw_scores)
    pred = grid.copy()
    pred["species_id"] = species_id
    pred["common_name"] = cfg.SPECIES_CONFIG[species_id]["common_name"]
    pred["score"] = relative_scores.round(2)
    pred["rating"] = pred["score"].apply(rating_from_score)
    pred["confidence"] = metadata.get("confidence_level", "Low")
    pred["model_type"] = metadata.get("model_type")
    pred["feature_set_name"] = metadata.get("feature_set_name")
    pred["data_sources_available"] = ",".join(
        name
        for name, flag in [
            ("sst", pred.get("has_sst", pd.Series([False])).any()),
            ("bathymetry", pred.get("has_bathymetry", pd.Series([False])).any()),
            ("physics", pred.get("has_physics", pd.Series([False])).any()),
            ("chlorophyll", pred.get("has_chl", pd.Series([False])).any()),
            ("structure", pred.get("has_structure", pd.Series([False])).any()),
        ]
        if bool(flag)
    )
    parquet_out = save_dataframe(
        pred,
        cfg.DATA / "processed" / "predictions" / f"{date_text}_{species_id}_sydney_heatmap.csv",
        cfg.DATA / "processed" / "predictions" / f"{date_text}_{species_id}_sydney_heatmap.parquet",
    )

    features = []
    for row in pred.nlargest(min(1000, len(pred)), "score").to_dict("records"):
        drivers, explanation = explain_row(row, feature_columns)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]},
                "properties": {
                    "species_id": species_id,
                    "common_name": row["common_name"],
                    "date": date_text,
                    "lat": float(row["lat"]),
                    "lon": float(row["lon"]),
                    "score": float(row["score"]),
                    "rating": row["rating"],
                    "confidence": row["confidence"],
                    "model_type": row["model_type"],
                    "feature_set_name": row["feature_set_name"],
                    "top_drivers": drivers,
                    "explanation": explanation,
                    "limitations": [
                        "Relative habitat suitability only.",
                        "Not exact fish location or true catch probability.",
                        "Presence/background data can reflect observation and fishing effort bias.",
                    ],
                    "data_sources_available": row["data_sources_available"],
                },
            }
        )
    geojson = {"type": "FeatureCollection", "features": features}
    geojson_out = cfg.DATA / "processed" / "predictions" / f"{date_text}_{species_id}_sydney_heatmap.geojson"
    write_json(geojson_out, geojson)
    return {
        "species_id": species_id,
        "status": "written",
        "date": date_text,
        "features": len(features),
        "geojson": str(geojson_out.relative_to(cfg.ROOT)),
        "parquet_or_csv": parquet_out,
    }


def main() -> None:
    ensure_dirs()
    date_text, grid = load_prediction_grid()
    if date_text is None or grid.empty:
        summary = {
            "status": "skipped",
            "reason": "no verified prediction feature grid is available; refusing to use synthetic/proxy grid for real model heatmap",
            "outputs": [],
        }
        write_json(cfg.DATA / "processed" / "predictions" / "real_model_prediction_summary.json", summary)
        print(summary)
        return
    outputs = [predict_species(species_id, date_text, grid) for species_id in TARGET_SPECIES]
    summary = {"status": "completed", "date": date_text, "outputs": outputs}
    write_json(cfg.DATA / "processed" / "predictions" / "real_model_prediction_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
