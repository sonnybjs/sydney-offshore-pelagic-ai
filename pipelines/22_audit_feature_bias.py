from __future__ import annotations

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from model_audit_lib import TARGET_SPECIES, ensure_audit_dirs, feature_importance_from_model, load_training, species_audit_dir
from modeling_lib import evaluate_scores, split_dataset
from pipeline_lib import save_dataframe, write_json


NULL_FEATURE_SETS = {
    "coordinates_only_null_model": ["grid_lat", "grid_lon"],
    "month_only_null_model": ["month_sin", "month_cos", "day_of_year_sin", "day_of_year_cos"],
    "depth_distance_only_null_model": ["depth_m", "slope", "distance_to_200m_contour", "distance_to_500m_contour", "distance_to_1000m_contour", "distance_to_shelf_break"],
    "sst_bathy_season_only": ["sst_c", "sst_gradient", "sst_front_strength", "depth_m", "slope", "month_sin", "month_cos", "day_of_year_sin", "day_of_year_cos"],
}


def usable_features(df: pd.DataFrame, cols: list[str]) -> list[str]:
    out = []
    for col in cols:
        if col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().sum() > 0 and s.nunique(dropna=True) > 1:
            out.append(col)
    return out


def train_null(train: pd.DataFrame, val: pd.DataFrame, cols: list[str]) -> dict:
    if len(cols) < 1 or train.empty or val.empty or train["label"].nunique() < 2 or val["label"].nunique() < 2:
        return {"status": "skipped", "reason": "insufficient data or features"}
    model = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
        ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42)),
    ])
    model.fit(train[cols], train["label"].astype(int))
    scores = model.predict_proba(val[cols])[:, 1]
    return {"status": "evaluated", "features": cols, "validation_metrics": evaluate_scores(val["label"].astype(int), scores)}


def audit_species(species_id: str) -> dict:
    df = load_training(species_id)
    out_dir = species_audit_dir(species_id)
    if df.empty or "label" not in df.columns:
        status = {"species_id": species_id, "status": "skipped", "reason": "missing training data"}
        write_json(out_dir / "feature_bias_audit.json", status)
        return status
    df = df.copy()
    df["label"] = df["label"].astype(int)
    if df["label"].nunique() < 2 or int((df["label"] == 1).sum()) < 2 or int((df["label"] == 0).sum()) < 2:
        status = {
            "species_id": species_id,
            "status": "skipped",
            "reason": "too few presence/background samples for feature bias audit",
            "presence": int((df["label"] == 1).sum()),
            "background": int((df["label"] == 0).sum()),
        }
        write_json(out_dir / "feature_bias_audit.json", status)
        (out_dir / "feature_bias_audit.md").write_text(f"# Feature Bias Audit: {species_id}\n\nSkipped: {status['reason']}\n", encoding="utf-8")
        return status
    try:
        splits, split_strategy = split_dataset(df)
    except Exception as exc:
        status = {"species_id": species_id, "status": "skipped", "reason": f"split failed: {type(exc).__name__}: {exc}"}
        write_json(out_dir / "feature_bias_audit.json", status)
        (out_dir / "feature_bias_audit.md").write_text(f"# Feature Bias Audit: {species_id}\n\nSkipped: {status['reason']}\n", encoding="utf-8")
        return status
    model_path = out_dir.parents[1] / "models" / species_id / "best_model.joblib"
    metadata_path = out_dir.parents[1] / "models" / species_id / "model_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    feature_columns = metadata.get("feature_columns", [])
    importance_rows = []
    if model_path.exists() and feature_columns:
        try:
            bundle = joblib.load(model_path)
            model = bundle.get("model", bundle)
            importance = feature_importance_from_model(model, feature_columns)
            if not importance.empty:
                save_dataframe(importance, out_dir / "feature_importance_audit.csv", out_dir / "feature_importance_audit.parquet")
                importance_rows = importance.head(25).to_dict("records")
        except Exception as exc:
            importance_rows = [{"error": f"{type(exc).__name__}: {exc}"}]
    null_models = {}
    for name, cols in NULL_FEATURE_SETS.items():
        used = usable_features(df, cols)
        null_models[name] = train_null(splits.get("train", pd.DataFrame()), splits.get("validation", pd.DataFrame()), used)
    selected_val = metadata.get("validation_metrics", {})
    best_null_roc = max([m.get("validation_metrics", {}).get("roc_auc") or 0 for m in null_models.values()] + [0])
    best_null_pr = max([m.get("validation_metrics", {}).get("pr_auc") or 0 for m in null_models.values()] + [0])
    selected_roc = selected_val.get("roc_auc") or 0
    selected_pr = selected_val.get("pr_auc") or 0
    suspicious_features = [row.get("feature") for row in importance_rows if str(row.get("feature")) in {"grid_lat", "grid_lon"} or "missing_flag" in str(row.get("feature"))]
    biased = bool(best_null_roc >= selected_roc - 0.03 or best_null_pr >= selected_pr - 0.03 or suspicious_features)
    status = {
        "species_id": species_id,
        "split_strategy": split_strategy,
        "selected_model_type": metadata.get("model_type"),
        "selected_validation_metrics": selected_val,
        "top_feature_importance": importance_rows,
        "null_model_results": null_models,
        "suspicious_features": suspicious_features,
        "model_likely_biased": biased,
        "diagnosis": "If coordinate/depth/month null models approach the selected model, the model may be learning sampling effort or accessibility bias rather than habitat.",
    }
    write_json(out_dir / "feature_bias_audit.json", status)
    lines = [f"# Feature Bias Audit: {species_id}", "", f"- likely biased: `{biased}`", f"- selected model: `{metadata.get('model_type')}`", ""]
    lines.append("## Null Models")
    for name, result in null_models.items():
        lines.append(f"- {name}: `{result}`")
    lines.append("\n## Top Importance")
    for row in importance_rows[:15]:
        lines.append(f"- {row}")
    (out_dir / "feature_bias_audit.md").write_text("\n".join(lines), encoding="utf-8")
    return status


def main() -> None:
    ensure_audit_dirs()
    summary = {species_id: audit_species(species_id) for species_id in TARGET_SPECIES}
    print(summary)


if __name__ == "__main__":
    main()
