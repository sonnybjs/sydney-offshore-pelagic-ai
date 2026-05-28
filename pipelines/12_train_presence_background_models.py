import json

from pipeline_lib import cfg, ensure_dirs, try_write_parquet, write_json


MIN_FEATURES = [
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
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import average_precision_score, roc_auc_score
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    ensure_dirs()
    results = {}
    for species_id in cfg.SPECIES_CONFIG:
        presence_path = cfg.DATA / "interim" / "matched_presence" / f"{species_id}_presence.parquet"
        background_path = cfg.DATA / "interim" / "background_samples" / f"{species_id}_background.parquet"
        if not presence_path.exists() or not background_path.exists():
            results[species_id] = {"status": "missing_samples"}
            continue
        presence = pd.read_parquet(presence_path)
        background = pd.read_parquet(background_path)
        if len(presence) < 100 or background.empty:
            results[species_id] = {"status": "insufficient_data", "presence": int(len(presence)), "background": int(len(background))}
            continue
        data = pd.concat([presence, background], ignore_index=True, sort=False)
        data["species_id"] = species_id
        sample_out = try_write_parquet(data, cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.parquet")
        x = data[MIN_FEATURES]
        y = data["label"].astype(int)
        x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.25, stratify=y, random_state=42)
        models = {
            "logistic_regression": Pipeline([("impute", SimpleImputer()), ("scale", StandardScaler()), ("model", LogisticRegression(max_iter=1000))]),
            "hist_gradient_boosting": Pipeline([("impute", SimpleImputer()), ("model", HistGradientBoostingClassifier(random_state=42))]),
        }
        best_name, best_model, best_auc = None, None, -1.0
        metrics = {}
        for name, model in models.items():
            model.fit(x_train, y_train)
            scores = model.predict_proba(x_test)[:, 1]
            roc = roc_auc_score(y_test, scores) if len(set(y_test)) > 1 else None
            pr = average_precision_score(y_test, scores)
            metrics[name] = {"roc_auc": roc, "pr_auc": pr}
            if roc is not None and roc > best_auc:
                best_name, best_model, best_auc = name, model, roc
        model_path = cfg.DATA / "processed" / "models" / f"{species_id}_model.joblib"
        joblib.dump({"species_id": species_id, "model_type": best_name, "features": MIN_FEATURES, "model": best_model}, model_path)
        report = {
            "status": "trained",
            "presence": int(len(presence)),
            "background": int(len(background)),
            "training_samples": str(sample_out.relative_to(cfg.ROOT)),
            "best_model": best_name,
            "metrics": metrics,
            "confidence": "Medium" if len(presence) >= 300 else "Low",
        }
        write_json(cfg.DATA / "processed" / "metrics" / f"{species_id}_metrics.json", report)
        (cfg.DATA / "processed" / "reports" / f"{species_id}_training_report.md").write_text(
            f"# {species_id} Training Report\n\nPresence: {len(presence)}\n\nBackground: {len(background)}\n\nBest model: {best_name}\n\nMetrics:\n\n```json\n{json.dumps(metrics, indent=2)}\n```\n",
            encoding="utf-8",
        )
        results[species_id] = report
        print(species_id, report)
    write_json(cfg.DATA / "processed" / "metrics" / "training_summary.json", results)


if __name__ == "__main__":
    main()
