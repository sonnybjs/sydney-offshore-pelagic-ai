from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pipeline_lib import cfg, ensure_dirs, rating, read_table, save_dataframe, write_json


TARGET_SPECIES = list(cfg.SPECIES_CONFIG.keys())

MINIMUM_FEATURES = [
    "sst_c",
    "sst_gradient",
    "sst_front_strength",
    "sst_3d_change",
    "sst_7d_change",
    "depth_m",
    "slope",
    "distance_to_200m_contour",
    "distance_to_500m_contour",
    "distance_to_1000m_contour",
    "distance_to_shelf_break",
    "month_sin",
    "month_cos",
    "day_of_year_sin",
    "day_of_year_cos",
]

OPTIONAL_FEATURES = [
    "current_speed",
    "current_direction_degrees",
    "current_edge_score",
    "zos",
    "sla_gradient",
    "eddy_score",
    "chl_log",
    "chl_gradient",
    "chl_edge_score",
    "distance_to_nearest_fad_km",
    "distance_to_browns_mountain_km",
    "distance_to_nearest_poi_km",
    "moon_age_days",
    "moon_phase_fraction",
    "moon_illumination",
    "moon_phase_sin",
    "moon_phase_cos",
    "surface_pressure_hpa_mean",
    "surface_pressure_hpa_min",
    "surface_pressure_hpa_max",
    "pressure_msl_hpa_mean",
    "wind_speed_10m_kmh_mean",
    "wind_speed_10m_kmh_max",
    "precipitation_mm_sum",
    "wind_direction_10m_deg_circular_mean",
    "o2",
    "dissolved_oxygen",
    "oxygen_saturation",
]

FLAG_FEATURES = [
    "has_sst",
    "has_bathymetry",
    "has_physics",
    "has_chl",
    "has_structure",
    "has_lunar",
    "has_weather",
    "has_oxygen",
    "sst_missing_flag",
    "physics_missing_flag",
    "chl_missing_flag",
    "oxygen_missing_flag",
]

COORDINATE_FEATURES = ["grid_lat", "grid_lon"]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def species_dir(species_id: str) -> Path:
    path = cfg.DATA / "processed" / "models" / species_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def figures_dir(species_id: str) -> Path:
    path = cfg.DATA / "processed" / "figures" / species_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_training_samples(species_id: str):
    csv_path = cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.csv"
    parquet_path = csv_path.with_suffix(".parquet")
    if csv_path.exists() and parquet_path.exists() and csv_path.stat().st_mtime > parquet_path.stat().st_mtime:
        import pandas as pd

        return pd.read_csv(csv_path)
    if parquet_path.exists():
        return read_table(csv_path)
    return read_table(csv_path)


def clean_feature_columns(df, candidates: list[str], keep_flags: bool = True) -> list[str]:
    import pandas as pd

    available = [col for col in candidates if col in df.columns]
    keep = []
    for col in available:
        series = df[col]
        if series.empty:
            continue
        if series.isna().all():
            continue
        missing = float(series.isna().mean())
        if missing > 0.80 and not (keep_flags and col in FLAG_FEATURES):
            continue
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() == 0:
            continue
        if numeric.nunique(dropna=True) <= 1 and col not in FLAG_FEATURES:
            continue
        keep.append(col)
    return keep


def feature_sets_for(df) -> dict[str, list[str]]:
    base = MINIMUM_FEATURES + FLAG_FEATURES
    full = MINIMUM_FEATURES + OPTIONAL_FEATURES + FLAG_FEATURES
    return {
        "minimum_sst_bathy": clean_feature_columns(df, MINIMUM_FEATURES),
        "sst_bathy_season": clean_feature_columns(df, base),
        "full_available_oceanographic": clean_feature_columns(df, full),
        "no_coordinates": clean_feature_columns(df, full),
        "coordinates_allowed_as_bias_check": clean_feature_columns(df, full + COORDINATE_FEATURES),
    }


def split_dataset(df):
    import pandas as pd
    from sklearn.model_selection import train_test_split

    data = df.copy()
    if "split" not in data.columns or data["split"].isna().all():
        data["split"] = "train"
        data.loc[(data["date"] >= "2021-01-01") & (data["date"] <= "2022-12-31"), "split"] = "validation"
        data.loc[data["date"] >= "2023-01-01", "split"] = "test"
        data["split_strategy"] = "time_split"
    splits = {name: part.copy() for name, part in data.groupby("split")}
    required = ["train", "validation", "test"]
    valid_time_split = all(name in splits for name in required) and all(splits[name]["label"].nunique() == 2 for name in required)
    if valid_time_split:
        return splits, "time_split"
    if data["label"].nunique() < 2 or len(data) < 20:
        return {"train": data, "validation": pd.DataFrame(), "test": pd.DataFrame()}, "insufficient_for_split"
    train, holdout = train_test_split(data, test_size=0.30, stratify=data["label"], random_state=42)
    val, test = train_test_split(holdout, test_size=0.50, stratify=holdout["label"], random_state=42)
    return {"train": train, "validation": val, "test": test}, "stratified_random_low_data"


def top_k_hit_rate(y_true, scores, fraction: float) -> float | None:
    import numpy as np

    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype=float)
    positives = int(y.sum())
    if len(y) == 0 or positives == 0:
        return None
    n = max(1, int(math.ceil(len(y) * fraction)))
    order = np.argsort(s)[::-1][:n]
    return float(y[order].sum() / positives)


def precision_recall_at_top_k(y_true, scores, fraction: float = 0.10) -> dict[str, float | None]:
    import numpy as np

    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype=float)
    if len(y) == 0:
        return {"precision_at_top_10": None, "recall_at_top_10": None}
    n = max(1, int(math.ceil(len(y) * fraction)))
    order = np.argsort(s)[::-1][:n]
    selected_positive = int(y[order].sum())
    positives = int(y.sum())
    return {
        "precision_at_top_10": float(selected_positive / n),
        "recall_at_top_10": None if positives == 0 else float(selected_positive / positives),
    }


def evaluate_scores(y_true, scores) -> dict[str, Any]:
    import numpy as np
    from sklearn.metrics import average_precision_score, brier_score_loss, confusion_matrix, log_loss, roc_auc_score

    y = np.asarray(y_true).astype(int)
    s = np.clip(np.asarray(scores, dtype=float), 1e-6, 1 - 1e-6)
    out: dict[str, Any] = {
        "sample_count": int(len(y)),
        "presence_count": int(y.sum()),
        "background_count": int((y == 0).sum()),
        "baseline_prevalence": None if len(y) == 0 else float(y.mean()),
    }
    if len(y) == 0 or len(set(y.tolist())) < 2:
        out.update({"roc_auc": None, "pr_auc": None, "log_loss": None, "brier_score": None})
        return out
    out["roc_auc"] = float(roc_auc_score(y, s))
    out["pr_auc"] = float(average_precision_score(y, s))
    out["log_loss"] = float(log_loss(y, s))
    out["brier_score"] = float(brier_score_loss(y, s))
    out["top_5_hit_rate"] = top_k_hit_rate(y, s, 0.05)
    out["top_10_hit_rate"] = top_k_hit_rate(y, s, 0.10)
    out["top_20_hit_rate"] = top_k_hit_rate(y, s, 0.20)
    out.update(precision_recall_at_top_k(y, s, 0.10))
    out["confusion_matrix_threshold_0_5"] = confusion_matrix(y, s >= 0.5).tolist()
    return out


def poor_result(metrics: dict[str, Any], train_metrics: dict[str, Any] | None = None) -> list[str]:
    reasons = []
    if metrics.get("pr_auc") is not None and metrics["pr_auc"] < 0.25:
        reasons.append("validation_pr_auc_below_0_25")
    if metrics.get("roc_auc") is not None and metrics["roc_auc"] < 0.60:
        reasons.append("validation_roc_auc_below_0_60")
    if metrics.get("top_10_hit_rate") is not None and metrics["top_10_hit_rate"] < 0.25:
        reasons.append("validation_top_10_hit_rate_below_0_25")
    if train_metrics and train_metrics.get("roc_auc") is not None and metrics.get("roc_auc") is not None:
        if train_metrics["roc_auc"] - metrics["roc_auc"] > 0.20:
            reasons.append("possible_overfitting_train_validation_gap_gt_0_20")
    return reasons


def confidence_for(presence_count: int, validation: dict[str, Any] | None, test: dict[str, Any] | None) -> str:
    if presence_count < 100:
        return "Rule-based only"
    val_roc = (validation or {}).get("roc_auc")
    val_top = (validation or {}).get("top_10_hit_rate")
    if presence_count >= 1000 and val_roc and val_roc >= 0.75 and val_top and val_top >= 0.50:
        return "High"
    if presence_count >= 300 and val_roc and val_roc >= 0.65 and val_top and val_top >= 0.35:
        return "Medium"
    return "Low"


def write_empty_candidate_files(species_id: str, reason: str, data_summary: dict[str, Any]) -> dict[str, Any]:
    import pandas as pd

    out_dir = species_dir(species_id)
    rows = [
        {
            "species_id": species_id,
            "status": "not_trained",
            "reason": reason,
            **data_summary,
        }
    ]
    save_dataframe(pd.DataFrame(rows), out_dir / "candidate_results.csv")
    write_json(out_dir / "model_metadata.json", {"species_id": species_id, "status": "not_trained", "reason": reason, **data_summary})
    write_json(out_dir / "feature_list.json", [])
    (out_dir / "selected_model_report.md").write_text(
        f"# {species_id} Model Report\n\nStatus: not trained\n\nReason: {reason}\n\nNo exact fish-location or true catch-probability claim is made.\n",
        encoding="utf-8",
    )
    return {"species_id": species_id, "status": "not_trained", "reason": reason, **data_summary}


def rating_from_score(score: float) -> str:
    return rating(score)
