from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd

from model_audit_lib import (
    MODELS_CORRECTED,
    PRED_CORRECTED,
    TARGET_SPECIES,
    candidate_grid_for_prediction,
    ensure_audit_dirs,
    offshore_mask,
    predict_proba_or_score,
    score_distribution,
    strict_percentile_scores,
    strict_rating,
    write_geojson,
)
from pipeline_lib import cfg, save_dataframe, write_json


def explain(row: pd.Series) -> list[str]:
    notes = []
    if pd.notna(row.get("sst_c")):
        notes.append(f"SST feature available ({float(row['sst_c']):.1f} C).")
    if pd.notna(row.get("sst_front_strength")):
        notes.append("SST front proxy contributes to the ranking.")
    if pd.notna(row.get("depth_m")):
        notes.append(f"Depth passes offshore display mask ({float(row['depth_m']):.0f} m).")
    if pd.notna(row.get("distance_to_shelf_break")):
        notes.append("Shelf-break distance is included where available.")
    return notes[:4] or ["Relative suitability ranked within the prediction grid."]


def predict_species(species_id: str, date_text: str, grid: pd.DataFrame) -> dict:
    model_dir = MODELS_CORRECTED / species_id
    model_path = model_dir / "best_model.joblib"
    metadata_path = model_dir / "model_metadata.json"
    if not model_path.exists() or not metadata_path.exists():
        return {"species_id": species_id, "status": "skipped_no_corrected_model"}
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if not str(metadata.get("status", "")).startswith("selected"):
        return {"species_id": species_id, "status": "skipped_model_not_selected", "metadata_status": metadata.get("status")}
    bundle = joblib.load(model_path)
    feature_columns = bundle["feature_columns"]
    pred = grid.copy()
    for col in feature_columns:
        if col not in pred.columns:
            pred[col] = np.nan
    raw = predict_proba_or_score(bundle["model"], pred[feature_columns])
    pred["raw_model_score"] = raw
    pred["display_mask_passed"] = offshore_mask(pred, species_id, "display")
    pred["percentile_score"] = np.nan
    passed = pred["display_mask_passed"].fillna(False).astype(bool)
    pred.loc[passed, "percentile_score"] = strict_percentile_scores(raw[passed.to_numpy()])
    pred["score_0_100"] = pred["percentile_score"].round(2)
    pred["score"] = pred["score_0_100"]
    pred["rating"] = [strict_rating(score, ok) for score, ok in zip(pred["percentile_score"], pred["display_mask_passed"])]
    pred["species_id"] = species_id
    pred["common_name"] = cfg.SPECIES_CONFIG.get(species_id, {}).get("common_name", species_id)
    pred["model_confidence"] = metadata.get("confidence_level", "Low")
    pred["model_type"] = metadata.get("model_type")
    pred["audit_status"] = "corrected_under_audit"
    pred["top_drivers"] = "sst_c,sst_front_strength,depth_m,distance_to_shelf_break"
    pred["explanation"] = pred.apply(lambda row: explain(row), axis=1)
    pred["limitations"] = pred.apply(
        lambda _: [
            "Relative habitat suitability ranking within the prediction area.",
            "Not exact fish location or true catch probability.",
            "Corrected model remains under audit until independent validation improves.",
        ],
        axis=1,
    )
    display = pred[pred["display_mask_passed"].fillna(False).astype(bool)].copy()
    dist = score_distribution(display, "score_0_100")
    csv_path = PRED_CORRECTED / f"{date_text}_{species_id}_corrected_sydney_heatmap.csv"
    save_dataframe(display, csv_path, csv_path.with_suffix(".parquet"))
    property_columns = [
        "species_id",
        "common_name",
        "raw_model_score",
        "percentile_score",
        "score_0_100",
        "score",
        "rating",
        "display_mask_passed",
        "depth_m",
        "distance_to_shelf_break",
        "sst_c",
        "sst_gradient",
        "sst_front_strength",
        "top_drivers",
        "model_confidence",
        "model_type",
        "audit_status",
        "explanation",
        "limitations",
    ]
    write_geojson(display.nlargest(min(1200, len(display)), "score_0_100"), PRED_CORRECTED / f"{date_text}_{species_id}_corrected_sydney_heatmap.geojson", property_columns)
    return {"species_id": species_id, "status": "written", "date": date_text, "display_cells": int(len(display)), "score_distribution": dist}


def main() -> None:
    ensure_audit_dirs()
    date_text, grid = candidate_grid_for_prediction()
    if date_text is None or grid.empty:
        summary = {"status": "skipped", "reason": "no prediction feature grid available"}
        write_json(PRED_CORRECTED / "corrected_prediction_summary.json", summary)
        print(summary)
        return
    outputs = [predict_species(species_id, date_text, grid) for species_id in TARGET_SPECIES]
    summary = {"status": "completed", "date": date_text, "outputs": outputs, "scoring": "strict_percentile_rank_prime_top_5_good_5_15_possible_15_40"}
    write_json(PRED_CORRECTED / "corrected_prediction_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
