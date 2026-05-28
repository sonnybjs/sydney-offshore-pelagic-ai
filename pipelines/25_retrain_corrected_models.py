from __future__ import annotations

import glob
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from model_audit_lib import MODELS_CORRECTED, TARGET_SPECIES, TRAINING_AUDIT, ensure_audit_dirs, min_depth_for
from modeling_lib import MINIMUM_FEATURES, OPTIONAL_FEATURES, evaluate_scores
from pipeline_lib import read_table, save_dataframe, write_json


def usable(df: pd.DataFrame, cols: list[str]) -> list[str]:
    out = []
    banned = {"grid_lat", "grid_lon", "lat", "lon", "occurrence_lat", "occurrence_lon"}
    for col in cols:
        if col in banned or col not in df.columns:
            continue
        s = pd.to_numeric(df[col], errors="coerce")
        if s.notna().sum() > 0 and s.nunique(dropna=True) > 1 and s.isna().mean() <= 0.8:
            out.append(col)
    return out


def models():
    return {
        "logistic_regression_balanced": Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", LogisticRegression(max_iter=1200, class_weight="balanced", random_state=42))]),
        "random_forest_conservative": Pipeline([("impute", SimpleImputer(strategy="median")), ("model", RandomForestClassifier(n_estimators=240, max_depth=8, min_samples_leaf=10, max_features="sqrt", class_weight="balanced_subsample", random_state=42, n_jobs=-1))]),
        "hist_gradient_boosting_conservative": Pipeline([("impute", SimpleImputer(strategy="median")), ("model", HistGradientBoostingClassifier(max_iter=180, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=25, l2_regularization=0.5, random_state=42))]),
    }


def split(df: pd.DataFrame):
    train = df[df["date"].astype(str) <= "2020-12-31"]
    val = df[(df["date"].astype(str) >= "2021-01-01") & (df["date"].astype(str) <= "2022-12-31")]
    test = df[df["date"].astype(str) >= "2023-01-01"]
    if train["label"].nunique() < 2 or val["label"].nunique() < 2:
        from sklearn.model_selection import train_test_split

        train, holdout = train_test_split(df, test_size=0.30, stratify=df["label"], random_state=42)
        val, test = train_test_split(holdout, test_size=0.50, stratify=holdout["label"], random_state=42)
        return train, val, test, "stratified_random_low_data"
    return train, val, test, "temporal_holdout"


def train_candidate(df: pd.DataFrame, features: list[str], model_name: str, model, source_file: str) -> dict:
    train, val, test, split_strategy = split(df)
    if train.empty or val.empty or train["label"].nunique() < 2 or val["label"].nunique() < 2:
        return {"status": "skipped", "reason": "insufficient split", "model": model_name}
    model.fit(train[features], train["label"].astype(int))
    val_scores = model.predict_proba(val[features])[:, 1]
    row = {
        "status": "trained",
        "source_file": source_file,
        "model": model_name,
        "features": features,
        "feature_count": len(features),
        "split_strategy": split_strategy,
        "train_samples": int(len(train)),
        "validation_samples": int(len(val)),
        "test_samples": int(len(test)),
        "presence": int((df["label"] == 1).sum()),
        "background": int((df["label"] == 0).sum()),
        "validation": evaluate_scores(val["label"].astype(int), val_scores),
        "model_object": model,
    }
    if not test.empty and test["label"].nunique() == 2:
        row["test"] = evaluate_scores(test["label"].astype(int), model.predict_proba(test[features])[:, 1])
    return row


def confidence(row: dict) -> str:
    presence = row.get("presence", 0)
    val = row.get("validation", {})
    if presence < 100:
        return "Rule-based only"
    if presence >= 300 and (val.get("roc_auc") or 0) >= 0.65 and (val.get("top_10_hit_rate") or 0) >= 0.35:
        return "Medium"
    return "Low"


def train_species(species_id: str) -> dict:
    out_dir = MODELS_CORRECTED / species_id
    out_dir.mkdir(parents=True, exist_ok=True)
    files = glob.glob(str(TRAINING_AUDIT / f"{species_id}_offshore_constrained_background_ratio*_training_samples.parquet"))
    files += glob.glob(str(TRAINING_AUDIT / f"{species_id}_environment_stratified_background_ratio*_training_samples.parquet"))
    files += glob.glob(str(TRAINING_AUDIT / f"{species_id}_spatial_buffered_background_ratio*_training_samples.parquet"))
    if not files:
        status = {"species_id": species_id, "status": "not_trained", "reason": "no audit training samples"}
        write_json(out_dir / "model_metadata.json", status)
        return status
    rows = []
    candidate_objects = []
    for file in files[:9]:
        df = read_table(Path(file))
        if df.empty or "label" not in df.columns:
            continue
        df = df.copy()
        df["label"] = df["label"].astype(int)
        if "depth_m" in df.columns:
            df = df[pd.to_numeric(df["depth_m"], errors="coerce") >= min_depth_for(species_id, "training")]
        if int((df["label"] == 1).sum()) < 100 or int((df["label"] == 0).sum()) < 100:
            continue
        features = usable(df, MINIMUM_FEATURES + OPTIONAL_FEATURES)
        if len(features) < 4:
            continue
        for model_name, model in models().items():
            result = train_candidate(df, features, model_name, model, file)
            if result.get("status") == "trained":
                candidate_objects.append(result)
                flat = {k: v for k, v in result.items() if k not in {"model_object", "features"}}
                flat["feature_columns"] = ",".join(features)
                flat["validation_pr_auc"] = result["validation"].get("pr_auc")
                flat["validation_roc_auc"] = result["validation"].get("roc_auc")
                flat["validation_top_10_hit_rate"] = result["validation"].get("top_10_hit_rate")
                flat["test_roc_auc"] = (result.get("test") or {}).get("roc_auc")
                rows.append(flat)
    if not candidate_objects:
        status = {"species_id": species_id, "status": "not_trained", "reason": "no viable corrected candidates"}
        write_json(out_dir / "model_metadata.json", status)
        return status
    ranked = sorted(candidate_objects, key=lambda r: ((r["validation"].get("pr_auc") or 0), (r["validation"].get("top_10_hit_rate") or 0), (r["validation"].get("roc_auc") or 0)), reverse=True)
    best = ranked[0]
    joblib.dump({"model": best["model_object"], "feature_columns": best["features"]}, out_dir / "best_model.joblib")
    save_dataframe(pd.DataFrame(rows), out_dir / "candidate_results.csv", out_dir / "candidate_results.parquet")
    metadata = {
        "species_id": species_id,
        "status": "selected_corrected_under_audit",
        "model_type": best["model"],
        "feature_columns": best["features"],
        "source_training_file": best["source_file"],
        "validation_metrics": best["validation"],
        "test_metrics": best.get("test", {}),
        "confidence_level": confidence(best),
        "model_audit_notes": [
            "Corrected model excludes raw coordinates.",
            "Corrected training applies offshore/depth-constrained background strategies.",
            "Scores must be displayed with strict percentile ranking, not loose min-max scaling.",
            "Output remains relative habitat suitability only, not exact fish location or true catch probability.",
        ],
    }
    write_json(out_dir / "model_metadata.json", metadata)
    write_json(out_dir / "feature_list.json", best["features"])
    (out_dir / "selected_model_report.md").write_text(
        f"# Corrected Model: {species_id}\n\nSelected: `{best['model']}`\n\nConfidence: `{metadata['confidence_level']}`\n\nValidation: `{best['validation']}`\n\nThis is relative habitat suitability only.\n",
        encoding="utf-8",
    )
    return metadata


def main() -> None:
    ensure_audit_dirs()
    summary = {species_id: train_species(species_id) for species_id in TARGET_SPECIES}
    write_json(MODELS_CORRECTED / "corrected_training_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
