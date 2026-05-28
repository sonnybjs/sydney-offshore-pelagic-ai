from __future__ import annotations

from pipeline_lib import cfg, ensure_dirs, read_table, save_dataframe, write_json
from modeling_lib import TARGET_SPECIES, figures_dir, load_training_samples, species_dir


def plot_label_distribution(species_id: str, data) -> list[str]:
    outputs = []
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return outputs
    if data.empty or "label" not in data.columns:
        return outputs
    fig_dir = figures_dir(species_id)
    if "month" in data.columns:
        pivot = data.groupby(["month", "label"]).size().unstack(fill_value=0)
        ax = pivot.plot(kind="bar", figsize=(8, 4), title=f"{species_id} monthly label distribution")
        ax.set_xlabel("Month")
        ax.set_ylabel("Samples")
        path = fig_dir / "monthly_label_distribution.png"
        plt.tight_layout()
        plt.savefig(path, dpi=140)
        plt.close()
        outputs.append(str(path.relative_to(cfg.ROOT)))
    return outputs


def evaluate_species(species_id: str) -> dict:
    import pandas as pd

    data = load_training_samples(species_id)
    candidate_path = species_dir(species_id) / "candidate_results.csv"
    candidates = read_table(candidate_path)
    if data.empty:
        report = {
            "species_id": species_id,
            "status": "not_evaluated",
            "reason": "training sample file is empty",
            "presence": 0,
            "background": 0,
            "candidate_count": int(len(candidates)),
        }
        write_json(cfg.DATA / "processed" / "metrics" / f"{species_id}_metrics.json", report)
        return report

    presence = int((data["label"].astype(int) == 1).sum()) if "label" in data.columns else 0
    background = int((data["label"].astype(int) == 0).sum()) if "label" in data.columns else 0
    feature_missingness = {}
    for col in data.columns:
        if col not in {"label", "date", "species_id", "sample_type"}:
            missing = float(data[col].isna().mean())
            if missing > 0:
                feature_missingness[col] = round(missing, 4)

    trained = candidates[candidates["status"] == "trained"].copy() if not candidates.empty and "status" in candidates.columns else pd.DataFrame()
    if not trained.empty:
        trained["validation_pr_auc_sort"] = pd.to_numeric(trained.get("validation_pr_auc"), errors="coerce").fillna(-1)
        trained["validation_top_10_sort"] = pd.to_numeric(trained.get("validation_top_10_hit_rate"), errors="coerce").fillna(-1)
        trained["validation_roc_sort"] = pd.to_numeric(trained.get("validation_roc_auc"), errors="coerce").fillna(-1)
        ranking = trained.sort_values(
            ["validation_pr_auc_sort", "validation_top_10_sort", "validation_roc_sort"],
            ascending=False,
        )
        best = ranking.iloc[0].to_dict()
    else:
        best = None

    figures = plot_label_distribution(species_id, data)
    report = {
        "species_id": species_id,
        "status": "evaluated" if best else "not_evaluated",
        "presence": presence,
        "background": background,
        "presence_background_ratio": None if presence == 0 else round(background / presence, 4),
        "candidate_count": int(len(candidates)),
        "trained_candidate_count": int(len(trained)),
        "best_candidate": best,
        "feature_missingness": feature_missingness,
        "figures": figures,
        "interpretation_note": "Metrics rank presence/background contrast only. They are not true catch probability or exact fish-location accuracy.",
    }
    write_json(cfg.DATA / "processed" / "metrics" / f"{species_id}_metrics.json", report)
    md = [
        f"# {species_id} Evaluation Report",
        "",
        f"Status: {report['status']}",
        f"Presence samples: {presence}",
        f"Background samples: {background}",
        f"Candidate models: {len(candidates)}",
        "",
        "The labels are presence/background, not true catch/no-catch observations. Scores are relative habitat suitability.",
    ]
    if best:
        md.extend(["", "## Best Validation Candidate", "", "```json", str(best), "```"])
    (cfg.DATA / "processed" / "reports" / f"{species_id}_model_evaluation_report.md").write_text("\n".join(md), encoding="utf-8")
    return report


def main() -> None:
    ensure_dirs()
    summary = {species_id: evaluate_species(species_id) for species_id in TARGET_SPECIES}
    rows = []
    for species_id, payload in summary.items():
        best = payload.get("best_candidate") or {}
        rows.append(
            {
                "species_id": species_id,
                "status": payload.get("status"),
                "presence": payload.get("presence"),
                "background": payload.get("background"),
                "candidate_count": payload.get("candidate_count"),
                "best_candidate_id": best.get("candidate_id"),
                "validation_pr_auc": best.get("validation_pr_auc"),
                "validation_roc_auc": best.get("validation_roc_auc"),
                "validation_top_10_hit_rate": best.get("validation_top_10_hit_rate"),
            }
        )
    import pandas as pd

    save_dataframe(pd.DataFrame(rows), cfg.DATA / "processed" / "metrics" / "model_evaluation_summary.csv")
    write_json(cfg.DATA / "processed" / "metrics" / "model_evaluation_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
