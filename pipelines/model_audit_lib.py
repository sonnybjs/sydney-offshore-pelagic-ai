from __future__ import annotations

import importlib.util
import json
import math
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pipeline_lib import cfg, haversine_km, read_table, save_dataframe, write_json


ROOT = cfg.ROOT
AUDIT_ROOT = cfg.DATA / "processed" / "model_audit"
PRED_CORRECTED = cfg.DATA / "processed" / "predictions_corrected"
MODELS_CORRECTED = cfg.DATA / "processed" / "models_corrected"
TRAINING_AUDIT = cfg.DATA / "processed" / "training_audit"
BACKGROUND_AUDIT = cfg.DATA / "interim" / "background_samples_audit"


def load_audit_config():
    path = ROOT / "config" / "model_audit_config.py"
    spec = importlib.util.spec_from_file_location("model_audit_config", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


audit_cfg = load_audit_config()
TARGET_SPECIES = audit_cfg.TARGET_AUDIT_SPECIES


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_audit_dirs() -> None:
    for path in [AUDIT_ROOT, PRED_CORRECTED, MODELS_CORRECTED, TRAINING_AUDIT, BACKGROUND_AUDIT]:
        path.mkdir(parents=True, exist_ok=True)
    for species_id in TARGET_SPECIES:
        (AUDIT_ROOT / species_id).mkdir(parents=True, exist_ok=True)
        (MODELS_CORRECTED / species_id).mkdir(parents=True, exist_ok=True)


def species_audit_dir(species_id: str) -> Path:
    path = AUDIT_ROOT / species_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def load_prediction_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".geojson":
        payload = load_json(path, {"features": []})
        rows = []
        for feature in payload.get("features", []):
            props = dict(feature.get("properties") or {})
            coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
            props.setdefault("lon", coords[0])
            props.setdefault("lat", coords[1])
            rows.append(props)
        return pd.DataFrame(rows)
    if path.suffix.lower() == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def prediction_candidates(species_id: str) -> list[Path]:
    root = cfg.DATA / "processed" / "predictions"
    files = []
    for suffix in ["*.parquet", "*.csv", "*.geojson"]:
        files.extend(root.glob(f"*{species_id}*{suffix[1:]}"))
    preferred = []
    seen = set()
    for file in sorted(files):
        stem = file.with_suffix("").name
        if stem in seen and file.suffix != ".parquet":
            continue
        seen.add(stem)
        preferred.append(file)
    return preferred


def score_distribution(df: pd.DataFrame, score_col: str = "score") -> dict[str, Any]:
    if df.empty or score_col not in df.columns:
        return {"cell_count": int(len(df)), "has_score": False}
    scores = pd.to_numeric(df[score_col], errors="coerce").dropna()
    if scores.empty:
        return {"cell_count": int(len(df)), "has_score": False}
    q = scores.quantile([0, .01, .05, .10, .25, .50, .75, .90, .95, .99, 1.0])
    ge90 = int((scores >= 90).sum())
    eq100 = int(np.isclose(scores, 100.0).sum())
    n = int(len(scores))
    return {
        "cell_count": n,
        "has_score": True,
        "min": float(q.loc[0]),
        "p1": float(q.loc[.01]),
        "p5": float(q.loc[.05]),
        "p10": float(q.loc[.10]),
        "p25": float(q.loc[.25]),
        "median": float(q.loc[.50]),
        "p75": float(q.loc[.75]),
        "p90": float(q.loc[.90]),
        "p95": float(q.loc[.95]),
        "p99": float(q.loc[.99]),
        "max": float(q.loc[1.0]),
        "cells_ge_90": ge90,
        "cells_eq_100": eq100,
        "percent_ge_90": float(ge90 / n * 100),
        "percent_eq_100": float(eq100 / n * 100),
        "saturation": bool(ge90 / n * 100 > audit_cfg.SATURATION_PERCENT_GE_90_LIMIT),
        "clipping_or_normalisation_issue": bool(eq100 / n * 100 > audit_cfg.CLIPPING_PERCENT_EQ_100_LIMIT),
    }


def strict_percentile_scores(raw_scores: np.ndarray) -> np.ndarray:
    scores = np.asarray(raw_scores, dtype=float)
    out = np.full(len(scores), np.nan, dtype=float)
    valid = np.isfinite(scores)
    if valid.sum() == 0:
        return out
    ranks = pd.Series(scores[valid]).rank(method="average", pct=True).to_numpy()
    out[valid] = ranks * 100.0
    return out


def strict_rating(percentile_score: float, display_mask_passed: bool = True) -> str:
    if not display_mask_passed or not np.isfinite(percentile_score):
        return "Masked"
    if percentile_score >= 95:
        return "Prime"
    if percentile_score >= 85:
        return "Good"
    if percentile_score >= 60:
        return "Possible"
    return "Low"


def min_depth_for(species_id: str, mode: str = "display") -> float:
    if mode == "training":
        return float(audit_cfg.MIN_DEPTH_TRAINING_BY_SPECIES.get(species_id, 50.0))
    return float(audit_cfg.MIN_DEPTH_DISPLAY_BY_SPECIES.get(species_id, 50.0))


def offshore_mask(df: pd.DataFrame, species_id: str, mode: str = "display") -> pd.Series:
    mask = pd.Series(True, index=df.index)
    if "ocean_mask" in df.columns:
        ocean = df["ocean_mask"]
        if ocean.dtype == object:
            ocean = ocean.astype(str).str.lower().isin(["true", "1", "yes"])
        mask &= ocean.fillna(False).astype(bool)
    if "depth_m" in df.columns:
        mask &= pd.to_numeric(df["depth_m"], errors="coerce").fillna(-999) >= min_depth_for(species_id, mode)
    return mask


def approximate_distance_to_coast_km(df: pd.DataFrame) -> pd.Series:
    # Lightweight proxy for NSW coast longitude in the Sydney/NSW offshore corridor.
    if "lon" not in df.columns:
        return pd.Series(np.nan, index=df.index)
    lons = pd.to_numeric(df["lon"], errors="coerce")
    return ((lons - 150.5).clip(lower=0) * 92.0).astype(float)


def add_spatial_bins(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "depth_m" in out.columns:
        out["depth_bin"] = pd.cut(pd.to_numeric(out["depth_m"], errors="coerce"), [-np.inf, 0, 20, 50, 100, 200, 500, 1000, np.inf]).astype(str)
    if "distance_to_shelf_break" in out.columns:
        out["shelf_distance_bin"] = pd.cut(pd.to_numeric(out["distance_to_shelf_break"], errors="coerce"), [-np.inf, 5, 20, 50, 100, 200, np.inf]).astype(str)
    out["distance_to_coast_km"] = approximate_distance_to_coast_km(out)
    out["coast_distance_bin"] = pd.cut(out["distance_to_coast_km"], [-np.inf, 10, 25, 50, 100, 200, np.inf]).astype(str)
    if {"lat", "lon"}.issubset(out.columns):
        out["lat_bin"] = np.floor(pd.to_numeric(out["lat"], errors="coerce")).astype("Int64").astype(str)
        out["lon_bin"] = np.floor(pd.to_numeric(out["lon"], errors="coerce")).astype("Int64").astype(str)
    return out


def table_counts(df: pd.DataFrame, group_col: str) -> dict[str, int]:
    if group_col not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df[group_col].value_counts(dropna=False).head(30).items()}


def markdown_kv(title: str, payload: dict[str, Any]) -> str:
    lines = [f"# {title}", ""]
    for key, value in payload.items():
        lines.append(f"- {key}: `{value}`")
    return "\n".join(lines) + "\n"


def freeze_prediction_manifest() -> dict[str, Any]:
    ensure_audit_dirs()
    manifest_path = cfg.DATA / "processed" / "predictions" / "prediction_manifest.json"
    manifest = load_json(manifest_path, {})
    if not manifest:
        return {"status": "missing_manifest"}
    backup = manifest_path.with_suffix(".pre_audit_backup.json")
    if not backup.exists():
        shutil.copy2(manifest_path, backup)
    for mode in ["demo", "current"]:
        species = (manifest.get(mode) or {}).get("species", {})
        for entry in species.values():
            if isinstance(entry, dict) and entry.get("available"):
                entry["audit_status"] = "under_audit_nearshore_saturation_detected"
                entry["warning"] = audit_cfg.AUDIT_WARNING
                existing = str(entry.get("notes", ""))
                if audit_cfg.AUDIT_WARNING not in existing:
                    entry["notes"] = f"{audit_cfg.AUDIT_WARNING} {existing}".strip()
    write_json(manifest_path, manifest)
    status = {"status": "frozen", "manifest": str(manifest_path.relative_to(ROOT)), "backup": str(backup.relative_to(ROOT)), "warning": audit_cfg.AUDIT_WARNING}
    write_json(AUDIT_ROOT / "freeze_status.json", status)
    return status


def feature_columns_from_metadata(species_id: str, corrected: bool = False) -> list[str]:
    root = MODELS_CORRECTED if corrected else cfg.DATA / "processed" / "models"
    metadata = load_json(root / species_id / "model_metadata.json", {})
    return list(metadata.get("feature_columns") or load_json(root / species_id / "feature_list.json", []))


def load_training(species_id: str) -> pd.DataFrame:
    path = cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.csv"
    return read_table(path)


def candidate_grid_for_prediction() -> tuple[str | None, pd.DataFrame]:
    pred_summary = load_json(cfg.DATA / "processed" / "predictions" / "real_model_prediction_summary.json", {})
    date_text = pred_summary.get("date") or "2025-12-22"
    path = cfg.DATA / "interim" / "feature_grid" / "daily_features" / f"features_{date_text}.csv"
    if not path.exists() and not path.with_suffix(".parquet").exists():
        return None, pd.DataFrame()
    grid = read_table(path)
    bbox = cfg.PREDICT_BBOX
    if {"lat", "lon"}.issubset(grid.columns):
        grid = grid[
            (pd.to_numeric(grid["lat"], errors="coerce") >= bbox["south_lat"])
            & (pd.to_numeric(grid["lat"], errors="coerce") <= bbox["north_lat"])
            & (pd.to_numeric(grid["lon"], errors="coerce") >= bbox["west_lon"])
            & (pd.to_numeric(grid["lon"], errors="coerce") <= bbox["east_lon"])
        ].copy()
    return date_text, grid


def predict_proba_or_score(model: Any, x: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return np.asarray(model.predict_proba(x)[:, 1], dtype=float)
    if hasattr(model, "decision_function"):
        z = np.asarray(model.decision_function(x), dtype=float)
        return 1 / (1 + np.exp(-z))
    return np.asarray(model.predict(x), dtype=float)


def feature_importance_from_model(model: Any, feature_columns: list[str]) -> pd.DataFrame:
    estimator = model
    if hasattr(model, "named_steps"):
        estimator = model.named_steps.get("model", model)
    values = None
    if hasattr(estimator, "feature_importances_"):
        values = estimator.feature_importances_
    elif hasattr(estimator, "coef_"):
        values = np.ravel(np.abs(estimator.coef_))
    if values is None or len(values) != len(feature_columns):
        return pd.DataFrame(columns=["feature", "importance"])
    return pd.DataFrame({"feature": feature_columns, "importance": values}).sort_values("importance", ascending=False)


def write_geojson(df: pd.DataFrame, path: Path, property_columns: list[str]) -> None:
    features = []
    for row in df.to_dict("records"):
        props = {}
        for col in property_columns:
            val = row.get(col)
            if isinstance(val, (list, tuple)):
                props[col] = list(val)
            elif isinstance(val, np.ndarray):
                props[col] = val.tolist()
            elif pd.isna(val):
                props[col] = None
            elif isinstance(val, (np.integer, np.floating)):
                props[col] = float(val)
            else:
                props[col] = val
        features.append({"type": "Feature", "geometry": {"type": "Point", "coordinates": [float(row["lon"]), float(row["lat"])]}, "properties": props})
    write_json(path, {"type": "FeatureCollection", "features": features})


def summarize_report() -> dict[str, Any]:
    summary = {"generated_at": now_utc(), "species": {}}
    for species_id in TARGET_SPECIES:
        root = species_audit_dir(species_id)
        summary["species"][species_id] = {
            "score_audit": load_json(root / "score_distribution_audit.json", {}),
            "bathymetry_audit": load_json(root / "bathymetry_features_audit.json", {}),
            "feature_bias_audit": load_json(root / "feature_bias_audit.json", {}),
            "validation_audit": load_json(root / "validation_audit.json", {}),
            "corrected_model": load_json(MODELS_CORRECTED / species_id / "model_metadata.json", {}),
        }
    return summary
