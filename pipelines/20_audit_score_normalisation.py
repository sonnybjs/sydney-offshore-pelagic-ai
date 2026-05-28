from __future__ import annotations

import pandas as pd

from model_audit_lib import (
    TARGET_SPECIES,
    add_spatial_bins,
    ensure_audit_dirs,
    freeze_prediction_manifest,
    prediction_candidates,
    score_distribution,
    species_audit_dir,
    table_counts,
)
from pipeline_lib import write_json


def audit_species(species_id: str) -> dict:
    files = prediction_candidates(species_id)
    reports = []
    for path in files:
        try:
            from model_audit_lib import load_prediction_table

            df = load_prediction_table(path)
            dist = score_distribution(df)
            binned = add_spatial_bins(df)
            high = binned[pd.to_numeric(binned.get("score"), errors="coerce") >= 90] if "score" in binned.columns else pd.DataFrame()
            dist.update(
                {
                    "file": str(path),
                    "high_score_depth_bins": table_counts(high, "depth_bin"),
                    "high_score_coast_distance_bins": table_counts(high, "coast_distance_bin"),
                    "high_score_shelf_distance_bins": table_counts(high, "shelf_distance_bin"),
                    "high_score_lat_bins": table_counts(high, "lat_bin"),
                    "high_score_lon_bins": table_counts(high, "lon_bin"),
                }
            )
            reports.append(dist)
        except Exception as exc:
            reports.append({"file": str(path), "error": f"{type(exc).__name__}: {exc}"})
    status = {
        "species_id": species_id,
        "file_count": len(files),
        "saturation_detected": any(item.get("saturation") for item in reports),
        "clipping_or_normalisation_issue_detected": any(item.get("clipping_or_normalisation_issue") for item in reports),
        "files": reports,
        "recommendation": "Use strict percentile ranking and rating thresholds: Prime top 5%, Good 5-15%, Possible 15-40%, Low bottom 60%.",
    }
    out_dir = species_audit_dir(species_id)
    write_json(out_dir / "score_distribution_audit.json", status)
    lines = [f"# Score Distribution Audit: {species_id}", ""]
    for item in reports:
        lines.append(f"## {item.get('file')}")
        for key in ["cell_count", "min", "p10", "median", "p90", "p95", "p99", "max", "percent_ge_90", "percent_eq_100", "saturation", "clipping_or_normalisation_issue", "error"]:
            if key in item:
                lines.append(f"- {key}: `{item[key]}`")
        lines.append("")
    (out_dir / "score_distribution_audit.md").write_text("\n".join(lines), encoding="utf-8")
    return status


def main() -> None:
    ensure_audit_dirs()
    freeze_prediction_manifest()
    summary = {species_id: audit_species(species_id) for species_id in TARGET_SPECIES}
    write_json(species_audit_dir("_summary") / "score_distribution_audit.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
