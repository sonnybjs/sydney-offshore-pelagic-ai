from __future__ import annotations

from pipeline_lib import cfg, ensure_dirs, read_table, save_dataframe, write_json
from modeling_lib import TARGET_SPECIES, confidence_for, load_training_samples, now_utc, species_dir


def metric_sort_frame(candidates):
    import pandas as pd

    frame = candidates.copy()
    for col in ["validation_pr_auc", "validation_top_10_hit_rate", "validation_roc_auc"]:
        frame[col] = pd.to_numeric(frame.get(col), errors="coerce")
    frame["validation_pr_auc_sort"] = frame["validation_pr_auc"].fillna(-1)
    frame["validation_top_10_sort"] = frame["validation_top_10_hit_rate"].fillna(-1)
    frame["validation_roc_sort"] = frame["validation_roc_auc"].fillna(-1)
    frame["coordinate_penalty"] = frame.get("feature_set_name", "").astype(str).eq("coordinates_allowed_as_bias_check").astype(int)
    return frame.sort_values(
        ["validation_pr_auc_sort", "validation_top_10_sort", "validation_roc_sort", "coordinate_penalty"],
        ascending=[False, False, False, True],
    )


def choose_production_candidate(ranked):
    best = ranked.iloc[0]
    best_pr = float(best.get("validation_pr_auc_sort", -1) or -1)
    best_top10 = float(best.get("validation_top_10_sort", -1) or -1)
    non_coordinate = ranked[ranked.get("feature_set_name", "").astype(str) != "coordinates_allowed_as_bias_check"]
    if not non_coordinate.empty:
        acceptable = non_coordinate[
            (non_coordinate["validation_pr_auc_sort"] >= best_pr - 0.02)
            & (non_coordinate["validation_top_10_sort"] >= best_top10 - 0.05)
        ]
        if not acceptable.empty:
            return acceptable.iloc[0]
    return best


def extract_feature_importance(bundle, data, species_id: str):
    import pandas as pd

    feature_columns = bundle["feature_columns"]
    model = bundle["model"]
    final_model = model.named_steps.get("model") if hasattr(model, "named_steps") else model
    values = None
    if hasattr(final_model, "feature_importances_"):
        values = final_model.feature_importances_
    elif hasattr(final_model, "coef_"):
        values = abs(final_model.coef_[0])
    if values is None:
        return pd.DataFrame(columns=["feature", "importance"])
    out = pd.DataFrame({"feature": feature_columns, "importance": values})
    out = out.sort_values("importance", ascending=False)
    save_dataframe(out, cfg.DATA / "processed" / "metrics" / f"{species_id}_feature_importance.csv")
    return out


def select_species(species_id: str) -> dict:
    import joblib

    out_dir = species_dir(species_id)
    candidates = read_table(out_dir / "candidate_results.csv")
    data = load_training_samples(species_id)
    if candidates.empty or "status" not in candidates.columns or not (candidates["status"] == "trained").any():
        payload = {
            "species_id": species_id,
            "status": "not_selected",
            "reason": "no trained candidates available",
            "confidence_level": "Rule-based only",
        }
        write_json(out_dir / "model_metadata.json", payload)
        return payload

    trained = candidates[candidates["status"] == "trained"].copy()
    ranked = metric_sort_frame(trained)
    best = choose_production_candidate(ranked).to_dict()
    candidate_id = best["candidate_id"]
    candidate_path = out_dir / f"{candidate_id}.joblib"
    if not candidate_path.exists():
        payload = {"species_id": species_id, "status": "not_selected", "reason": f"candidate artifact missing: {candidate_id}"}
        write_json(out_dir / "model_metadata.json", payload)
        return payload

    bundle = joblib.load(candidate_path)
    best_model_path = out_dir / "best_model.joblib"
    joblib.dump(bundle, best_model_path)
    feature_importance = extract_feature_importance(bundle, data, species_id)

    presence = int((data["label"].astype(int) == 1).sum()) if "label" in data.columns else 0
    background = int((data["label"].astype(int) == 0).sum()) if "label" in data.columns else 0
    validation_metrics = {
        "roc_auc": best.get("validation_roc_auc"),
        "pr_auc": best.get("validation_pr_auc"),
        "top_10_hit_rate": best.get("validation_top_10_hit_rate"),
        "brier_score": best.get("validation_brier_score"),
    }
    test_metrics = {
        "roc_auc": best.get("test_roc_auc"),
        "pr_auc": best.get("test_pr_auc"),
        "top_10_hit_rate": best.get("test_top_10_hit_rate"),
    }
    confidence = confidence_for(presence, validation_metrics, test_metrics)
    metadata = {
        "species_id": species_id,
        "common_name": cfg.SPECIES_CONFIG[species_id]["common_name"],
        "status": "selected",
        "model_type": best.get("model_name"),
        "candidate_id": candidate_id,
        "feature_set_name": best.get("feature_set_name"),
        "feature_columns": bundle["feature_columns"],
        "train_sample_count": int(best.get("samples", 0) or 0),
        "presence_count": presence,
        "background_count": background,
        "selected_metric": "validation_pr_auc_then_top10_then_roc_auc",
        "validation_metrics": validation_metrics,
        "test_metrics": test_metrics,
        "confidence_level": confidence,
        "limitations": [
            "Presence/background model, not true catch probability.",
            "Public occurrence data is biased by observation and fishing effort.",
            "Predictions are relative habitat suitability, not exact fish locations.",
            "Coordinate-heavy models may reflect spatial sampling bias.",
        ],
        "training_timestamp": now_utc(),
    }
    write_json(out_dir / "model_metadata.json", metadata)
    write_json(out_dir / "feature_list.json", bundle["feature_columns"])
    rows = ranked.drop(columns=[c for c in ranked.columns if c.endswith("_sort") or c == "coordinate_penalty"], errors="ignore")
    save_dataframe(rows, out_dir / "candidate_results_ranked.csv")
    report_lines = [
        f"# {species_id} Selected Model Report",
        "",
        f"Selected candidate: `{candidate_id}`",
        f"Model type: `{metadata['model_type']}`",
        f"Feature set: `{metadata['feature_set_name']}`",
        f"Confidence: {confidence}",
        "",
        "This model estimates relative habitat suitability from presence/background data. It does not identify exact fish locations or true catch probability.",
        "",
        "## Top Features",
        "",
    ]
    if not feature_importance.empty:
        for row in feature_importance.head(12).itertuples():
            report_lines.append(f"- `{row.feature}`: {round(float(row.importance), 6)}")
    (out_dir / "selected_model_report.md").write_text("\n".join(report_lines), encoding="utf-8")
    return metadata


def main() -> None:
    ensure_dirs()
    summary = {species_id: select_species(species_id) for species_id in TARGET_SPECIES}
    write_json(cfg.DATA / "processed" / "metrics" / "selected_model_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
