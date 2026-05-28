from __future__ import annotations

import glob

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from model_audit_lib import TARGET_SPECIES, TRAINING_AUDIT, ensure_audit_dirs, species_audit_dir
from modeling_lib import MINIMUM_FEATURES, OPTIONAL_FEATURES, evaluate_scores
from pipeline_lib import read_table, write_json


NULL_SETS = {
    "month_only": ["month_sin", "month_cos", "day_of_year_sin", "day_of_year_cos"],
    "coordinates_only": ["grid_lat", "grid_lon"],
    "depth_distance_only": ["depth_m", "slope", "distance_to_shelf_break", "distance_to_200m_contour", "distance_to_1000m_contour"],
}


def usable(df: pd.DataFrame, cols: list[str]) -> list[str]:
    out = []
    for col in cols:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce")
            if s.notna().sum() > 0 and s.nunique(dropna=True) > 1:
                out.append(col)
    return out


def model(kind: str):
    if kind == "logistic":
        return Pipeline([("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler()), ("model", LogisticRegression(max_iter=1000, class_weight="balanced", random_state=42))])
    return Pipeline([("impute", SimpleImputer(strategy="median")), ("model", HistGradientBoostingClassifier(max_iter=160, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=20, random_state=42))])


def split_temporal(df: pd.DataFrame):
    train = df[df["date"].astype(str) <= "2020-12-31"]
    val = df[(df["date"].astype(str) >= "2021-01-01") & (df["date"].astype(str) <= "2022-12-31")]
    test = df[df["date"].astype(str) >= "2023-01-01"]
    return train, val, test


def split_spatial_block(df: pd.DataFrame):
    data = df.copy()
    if not {"grid_lat", "grid_lon"}.issubset(data.columns):
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    data["block_id"] = np.floor(pd.to_numeric(data["grid_lat"], errors="coerce")).astype(str) + "_" + np.floor(pd.to_numeric(data["grid_lon"], errors="coerce")).astype(str)
    blocks = sorted(data["block_id"].dropna().unique())
    if len(blocks) < 3:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    val_blocks = set(blocks[::5])
    test_blocks = set(blocks[2::5])
    val = data[data["block_id"].isin(val_blocks)]
    test = data[data["block_id"].isin(test_blocks)]
    train = data[~data["block_id"].isin(val_blocks | test_blocks)]
    return train, val, test


def split_spatial_temporal(df: pd.DataFrame):
    train, val, test = split_spatial_block(df)
    if train.empty:
        return train, val, test
    train = train[train["date"].astype(str) <= "2020-12-31"]
    val = val[(val["date"].astype(str) >= "2021-01-01") & (val["date"].astype(str) <= "2022-12-31")]
    test = test[test["date"].astype(str) >= "2023-01-01"]
    return train, val, test


def run_eval(df: pd.DataFrame, features: list[str], split_name: str, split_func, kind: str = "hgb") -> dict:
    train, val, test = split_func(df)
    if train.empty or val.empty or train["label"].nunique() < 2 or val["label"].nunique() < 2 or len(features) < 2:
        return {"status": "skipped", "reason": "insufficient split/classes/features", "features": features}
    clf = model(kind)
    clf.fit(train[features], train["label"].astype(int))
    val_scores = clf.predict_proba(val[features])[:, 1]
    result = {
        "status": "evaluated",
        "split": split_name,
        "model": kind,
        "features": features,
        "train_samples": int(len(train)),
        "validation_samples": int(len(val)),
        "test_samples": int(len(test)),
        "validation": evaluate_scores(val["label"].astype(int), val_scores),
    }
    if not test.empty and test["label"].nunique() == 2:
        result["test"] = evaluate_scores(test["label"].astype(int), clf.predict_proba(test[features])[:, 1])
    return result


def audit_file(path: str) -> dict:
    df = read_table(pd.Path(path) if hasattr(pd, "Path") else __import__("pathlib").Path(path))
    if df.empty or "label" not in df.columns:
        return {"file": path, "status": "skipped_empty"}
    df = df.copy()
    df["label"] = df["label"].astype(int)
    main_features = usable(df, MINIMUM_FEATURES + OPTIONAL_FEATURES)
    results = {
        "file": path,
        "samples": int(len(df)),
        "presence": int((df["label"] == 1).sum()),
        "background": int((df["label"] == 0).sum()),
        "main_temporal": run_eval(df, main_features, "temporal_holdout", split_temporal, "hgb"),
        "main_spatial_block": run_eval(df, main_features, "spatial_block_cv_proxy", split_spatial_block, "hgb"),
        "main_spatial_temporal": run_eval(df, main_features, "spatial_temporal_holdout", split_spatial_temporal, "hgb"),
        "leave_nearshore_out_sanity": {},
        "null_models": {},
    }
    if "depth_m" in df.columns:
        offshore = df[pd.to_numeric(df["depth_m"], errors="coerce") >= 100]
        results["leave_nearshore_out_sanity"] = run_eval(offshore, main_features, "leave_nearshore_out_sanity", split_temporal, "hgb")
    for name, cols in NULL_SETS.items():
        results["null_models"][name] = run_eval(df, usable(df, cols), name, split_temporal, "logistic")
    val = results["main_spatial_temporal"].get("validation", {}) if isinstance(results["main_spatial_temporal"], dict) else {}
    null_roc = max([(r.get("validation") or {}).get("roc_auc") or 0 for r in results["null_models"].values()] + [0])
    results["beats_null_models"] = bool((val.get("roc_auc") or 0) > null_roc + 0.03)
    return results


def audit_species(species_id: str) -> dict:
    files = glob.glob(str(TRAINING_AUDIT / f"{species_id}_*_training_samples.parquet")) or glob.glob(str(TRAINING_AUDIT / f"{species_id}_*_training_samples.csv"))
    selected = [f for f in files if "offshore_constrained_background_ratio5" in f] or files[:3]
    reports = [audit_file(path) for path in selected[:5]]
    status = {"species_id": species_id, "evaluated_files": reports}
    out_dir = species_audit_dir(species_id)
    write_json(out_dir / "validation_audit.json", status)
    lines = [f"# Spatiotemporal Validation Audit: {species_id}", ""]
    for item in reports:
        lines.append(f"## {item.get('file')}")
        lines.append(f"- samples: `{item.get('samples')}`")
        lines.append(f"- main spatial-temporal: `{item.get('main_spatial_temporal')}`")
        lines.append(f"- null models: `{item.get('null_models')}`")
        lines.append("")
    (out_dir / "validation_audit.md").write_text("\n".join(lines), encoding="utf-8")
    return status


def main() -> None:
    ensure_audit_dirs()
    summary = {species_id: audit_species(species_id) for species_id in TARGET_SPECIES}
    print(summary)


if __name__ == "__main__":
    main()
