from __future__ import annotations

from itertools import product

from pipeline_lib import cfg, ensure_dirs, save_dataframe, write_json
from modeling_lib import (
    TARGET_SPECIES,
    clean_feature_columns,
    evaluate_scores,
    feature_sets_for,
    load_training_samples,
    poor_result,
    species_dir,
    split_dataset,
    write_empty_candidate_files,
)


MIN_PRESENCE_LOW_CONFIDENCE = 100
MIN_PRESENCE_FULL = 300


def optional_package_status() -> dict[str, bool]:
    status = {}
    for package in ["lightgbm", "xgboost", "elapid"]:
        try:
            __import__(package)
            status[package] = True
        except Exception:
            status[package] = False
    return status


def make_model_candidates():
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    candidates = {
        "logistic_regression_balanced": Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                ("scale", StandardScaler()),
                ("model", LogisticRegression(max_iter=2000, class_weight="balanced", random_state=42)),
            ]
        ),
        "random_forest_baseline": Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=300,
                        max_depth=12,
                        min_samples_leaf=5,
                        max_features="sqrt",
                        class_weight="balanced_subsample",
                        n_jobs=-1,
                        random_state=42,
                    ),
                ),
            ]
        ),
        "hist_gradient_boosting_baseline": Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=0.05,
                        max_iter=300,
                        max_leaf_nodes=31,
                        l2_regularization=0.1,
                        min_samples_leaf=20,
                        random_state=42,
                    ),
                ),
            ]
        ),
    }

    try:
        from lightgbm import LGBMClassifier

        candidates["lightgbm_baseline"] = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "model",
                    LGBMClassifier(
                        n_estimators=500,
                        learning_rate=0.03,
                        num_leaves=31,
                        min_child_samples=20,
                        subsample=0.9,
                        colsample_bytree=0.9,
                        random_state=42,
                        verbose=-1,
                    ),
                ),
            ]
        )
    except Exception:
        pass

    try:
        from xgboost import XGBClassifier

        candidates["xgboost_baseline"] = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "model",
                    XGBClassifier(
                        n_estimators=500,
                        max_depth=5,
                        learning_rate=0.03,
                        subsample=0.9,
                        colsample_bytree=0.9,
                        eval_metric="logloss",
                        random_state=42,
                    ),
                ),
            ]
        )
    except Exception:
        pass

    return candidates


def make_tuned_candidates():
    from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.pipeline import Pipeline

    candidates = {}
    rf_grid = list(product([300], [None, 10, 20], [5, 10], ["sqrt"]))[:6]
    for idx, (n_estimators, max_depth, min_leaf, max_features) in enumerate(rf_grid):
        candidates[f"random_forest_tuned_{idx:02d}"] = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=n_estimators,
                        max_depth=max_depth,
                        min_samples_leaf=min_leaf,
                        max_features=max_features,
                        class_weight="balanced_subsample",
                        n_jobs=-1,
                        random_state=100 + idx,
                    ),
                ),
            ]
        )
    hgb_grid = list(product([0.03, 0.05, 0.1], [300], [15, 31, 63], [0.1], [20]))[:9]
    for idx, (lr, max_iter, leaves, l2, min_leaf) in enumerate(hgb_grid):
        candidates[f"hist_gradient_boosting_tuned_{idx:02d}"] = Pipeline(
            [
                ("impute", SimpleImputer(strategy="median")),
                (
                    "model",
                    HistGradientBoostingClassifier(
                        learning_rate=lr,
                        max_iter=max_iter,
                        max_leaf_nodes=leaves,
                        l2_regularization=l2,
                        min_samples_leaf=min_leaf,
                        random_state=200 + idx,
                    ),
                ),
            ]
        )
    return candidates


def downsample_background(data, ratio: int):
    import pandas as pd

    positives = data[data["label"].astype(int) == 1]
    background = data[data["label"].astype(int) == 0]
    if positives.empty or background.empty:
        return data
    n = min(len(background), len(positives) * ratio)
    sampled = background.sample(n=n, random_state=42) if n < len(background) else background
    return pd.concat([positives, sampled], ignore_index=True, sort=False)


def train_one_species(species_id: str) -> dict:
    import joblib
    import pandas as pd

    out_dir = species_dir(species_id)
    data = load_training_samples(species_id)
    if data.empty:
        return write_empty_candidate_files(species_id, "training sample file is empty; required date-aligned SST features are unavailable", {"samples": 0})
    if "label" not in data.columns:
        return write_empty_candidate_files(species_id, "training sample file has no label column", {"samples": int(len(data))})

    data = data.copy()
    data["label"] = data["label"].astype(int)
    presence_count = int((data["label"] == 1).sum())
    background_count = int((data["label"] == 0).sum())
    data_summary = {"samples": int(len(data)), "presence": presence_count, "background": background_count}
    if presence_count < MIN_PRESENCE_LOW_CONFIDENCE:
        return write_empty_candidate_files(species_id, "fewer than 100 presence records; rule-based only", data_summary)
    if background_count == 0:
        return write_empty_candidate_files(species_id, "no background samples available", data_summary)

    splits, split_strategy = split_dataset(data)
    if splits["validation"].empty or splits["validation"]["label"].nunique() < 2:
        return write_empty_candidate_files(species_id, "validation split is unavailable or single-class", data_summary | {"split_strategy": split_strategy})

    feature_sets = feature_sets_for(data)
    feature_sets = {name: cols for name, cols in feature_sets.items() if len(cols) >= 3}
    if not feature_sets:
        return write_empty_candidate_files(species_id, "no usable environmental feature columns", data_summary)

    rows = []
    trained_models = {}
    package_status = optional_package_status()
    base_candidates = make_model_candidates()
    tuned_candidates = make_tuned_candidates()

    for feature_set_name, feature_columns in feature_sets.items():
        for background_ratio in [10, 5]:
            train_data = downsample_background(splits["train"], background_ratio)
            x_train = train_data[feature_columns]
            y_train = train_data["label"].astype(int)
            if y_train.nunique() < 2:
                continue
            x_val = splits["validation"][feature_columns]
            y_val = splits["validation"]["label"].astype(int)
            x_test = splits["test"][feature_columns] if not splits["test"].empty else pd.DataFrame(columns=feature_columns)
            y_test = splits["test"]["label"].astype(int) if not splits["test"].empty else pd.Series(dtype=int)

            model_pool = dict(base_candidates)
            if feature_set_name in ["full_available_oceanographic", "no_coordinates", "sst_bathy_season"] and background_ratio == 10:
                model_pool.update(tuned_candidates)

            for model_name, model in model_pool.items():
                try:
                    model.fit(x_train, y_train)
                    train_scores = model.predict_proba(x_train)[:, 1]
                    val_scores = model.predict_proba(x_val)[:, 1]
                    test_scores = model.predict_proba(x_test)[:, 1] if not x_test.empty else []
                    train_metrics = evaluate_scores(y_train, train_scores)
                    val_metrics = evaluate_scores(y_val, val_scores)
                    test_metrics = evaluate_scores(y_test, test_scores)
                    reasons = poor_result(val_metrics, train_metrics)
                    candidate_id = f"{feature_set_name}__br{background_ratio}__{model_name}"
                    joblib.dump(
                        {"species_id": species_id, "candidate_id": candidate_id, "feature_columns": feature_columns, "model": model},
                        out_dir / f"{candidate_id}.joblib",
                    )
                    trained_models[candidate_id] = True
                    rows.append(
                        {
                            "species_id": species_id,
                            "candidate_id": candidate_id,
                            "model_name": model_name,
                            "feature_set_name": feature_set_name,
                            "feature_count": len(feature_columns),
                            "background_ratio": background_ratio,
                            "split_strategy": split_strategy,
                            "train_roc_auc": train_metrics.get("roc_auc"),
                            "validation_roc_auc": val_metrics.get("roc_auc"),
                            "validation_pr_auc": val_metrics.get("pr_auc"),
                            "validation_top_10_hit_rate": val_metrics.get("top_10_hit_rate"),
                            "validation_brier_score": val_metrics.get("brier_score"),
                            "test_roc_auc": test_metrics.get("roc_auc"),
                            "test_pr_auc": test_metrics.get("pr_auc"),
                            "test_top_10_hit_rate": test_metrics.get("top_10_hit_rate"),
                            "poor_result_reasons": ";".join(reasons),
                            "status": "trained",
                        }
                    )
                except Exception as exc:
                    rows.append(
                        {
                            "species_id": species_id,
                            "candidate_id": f"{feature_set_name}__br{background_ratio}__{model_name}",
                            "model_name": model_name,
                            "feature_set_name": feature_set_name,
                            "background_ratio": background_ratio,
                            "status": "failed",
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

    results = pd.DataFrame(rows)
    outputs = save_dataframe(results, out_dir / "candidate_results.csv")
    save_dataframe(results, cfg.DATA / "processed" / "metrics" / f"{species_id}_candidate_metrics.csv")
    write_json(
        out_dir / "training_run_metadata.json",
        {
            "species_id": species_id,
            "data_summary": data_summary,
            "split_strategy": split_strategy,
            "optional_package_status": package_status,
            "candidate_count": int(len(results)),
            "outputs": outputs,
            "note": "Presence/background training. Scores are relative habitat suitability, not exact fish locations or true catch probability.",
        },
    )
    return {"species_id": species_id, "status": "candidate_models_trained", **data_summary, "candidate_count": int(len(results))}


def main() -> None:
    ensure_dirs()
    (cfg.DATA / "processed" / "figures").mkdir(parents=True, exist_ok=True)
    summary = {species_id: train_one_species(species_id) for species_id in TARGET_SPECIES}
    write_json(cfg.DATA / "processed" / "metrics" / "candidate_training_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
