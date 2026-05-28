from datetime import datetime

from pipeline_lib import cfg, ensure_dirs, rating, try_write_parquet, write_json
from pipeline_lib import ROOT


FEATURES = [
    "sst_c",
    "sst_gradient",
    "sst_front_strength",
    "depth_m",
    "slope",
    "distance_to_200m_contour",
    "distance_to_1000m_contour",
    "distance_to_shelf_break",
    "month_sin",
    "month_cos",
]


def main() -> None:
    import joblib
    import pandas as pd
    import importlib.util

    ensure_dirs()
    spec = importlib.util.spec_from_file_location("build_features_mod", cfg.ROOT / "pipelines" / "09_build_feature_grid.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    date_text = datetime.utcnow().date().isoformat()
    grid = mod.build_features(date_text, cfg.PREDICT_BBOX)
    outputs = []
    for model_file in (cfg.DATA / "processed" / "models").glob("*_model.joblib"):
        bundle = joblib.load(model_file)
        species_id = bundle["species_id"]
        model = bundle["model"]
        if model is None:
            continue
        scores = model.predict_proba(grid[FEATURES])[:, 1] * 100
        pred = grid.copy()
        pred["species_id"] = species_id
        pred["score"] = scores.round(2)
        pred["rating"] = pred["score"].apply(rating)
        pred["model_type"] = bundle["model_type"]
        pred["data_sources_available"] = "sst,bathymetry,structure_proxy"
        pred["confidence"] = "Medium"
        pred["top_drivers"] = "sst_c,sst_front_strength,distance_to_shelf_break"
        pred["explanation"] = "Relative habitat suitability based on SST/front/depth/shelf-break proxy features."
        pred["limitations"] = "Presence-background model; not exact fish location; current/chlorophyll unavailable in first run."
        parquet_out = try_write_parquet(pred, cfg.DATA / "processed" / "predictions" / f"{date_text}_{species_id}_sydney_heatmap.parquet")
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(row.lon), float(row.lat)]},
                "properties": {
                    "species_id": species_id,
                    "date": date_text,
                    "lat": float(row.lat),
                    "lon": float(row.lon),
                    "score": float(row.score),
                    "rating": row.rating,
                    "model_type": row.model_type,
                    "data_sources_available": row.data_sources_available,
                    "confidence": row.confidence,
                    "sst_c": float(row.sst_c),
                    "sst_gradient": float(row.sst_gradient),
                    "sst_front_strength": float(row.sst_front_strength),
                    "current_speed": None,
                    "current_direction_degrees": None,
                    "chl_log": None,
                    "chl_edge_score": None,
                    "depth_m": float(row.depth_m),
                    "distance_to_shelf_break": float(row.distance_to_shelf_break),
                    "distance_to_nearest_fad_km": None if pd.isna(row.distance_to_nearest_fad_km) else float(row.distance_to_nearest_fad_km),
                    "top_drivers": row.top_drivers.split(","),
                    "explanation": [row.explanation],
                    "limitations": [row.limitations],
                },
            }
            for row in pred.nlargest(500, "score").itertuples()
        ]
        geojson = {"type": "FeatureCollection", "features": features}
        geojson_out = cfg.DATA / "processed" / "predictions" / f"{date_text}_{species_id}_sydney_heatmap.geojson"
        write_json(geojson_out, geojson)
        outputs.append({"species_id": species_id, "parquet": str(parquet_out.relative_to(cfg.ROOT)), "geojson": str(geojson_out.relative_to(cfg.ROOT))})
    write_json(cfg.DATA / "processed" / "predictions" / "prediction_summary.json", {"date": date_text, "outputs": outputs})
    print({"date": date_text, "outputs": outputs})


if __name__ == "__main__":
    main()
