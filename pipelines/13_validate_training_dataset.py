from __future__ import annotations

import json

from pipeline_lib import cfg, ensure_dirs, write_json
from training_prep_lib import TARGET_SPECIES


FEATURE_COLUMNS = [
    "sst_c", "sst_gradient", "sst_front_strength", "sst_3d_change", "sst_7d_change",
    "depth_m", "slope", "distance_to_200m_contour", "distance_to_500m_contour",
    "distance_to_1000m_contour", "distance_to_shelf_break", "current_speed",
    "current_direction_degrees", "current_edge_score", "zos", "sla_gradient",
    "eddy_score", "chl_log", "chl_gradient", "chl_edge_score",
    "distance_to_nearest_fad_km", "distance_to_browns_mountain_km", "distance_to_nearest_poi_km",
]


def status_for(df, presence_count: int) -> str:
    if df.empty:
        return "unavailable_missing_required_data"
    has_sst = bool(df.get("has_sst", False).fillna(False).any()) if "has_sst" in df.columns else False
    has_bathy = bool(df.get("has_bathymetry", False).fillna(False).any()) if "has_bathymetry" in df.columns else False
    if not has_sst:
        return "unavailable_missing_required_data"
    if presence_count >= 300 and has_bathy:
        return "trainable_sst_bathy_only"
    if presence_count >= 300:
        return "trainable_full_features"
    if presence_count >= 100:
        return "trainable_low_confidence"
    return "rule_based_only_insufficient_occurrence"


def validate_species(species_id: str) -> dict:
    import pandas as pd

    path = cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.csv"
    if not path.exists():
        return {"status": "unavailable_missing_required_data", "reason": "training sample file not found"}
    df = pd.read_csv(path)
    if df.empty:
        return {"status": "unavailable_missing_required_data", "reason": "training sample file empty"}
    presence = int((df["label"] == 1).sum())
    background = int((df["label"] == 0).sum())
    missingness = {col: round(float(df[col].isna().mean() * 100), 4) for col in FEATURE_COLUMNS if col in df.columns}
    result = {
        "status": status_for(df, presence),
        "total_samples": int(len(df)),
        "presence_samples": presence,
        "background_samples": background,
        "presence_background_ratio": None if presence == 0 else round(background / presence, 4),
        "unique_dates": int(df["date"].nunique()),
        "date_min": str(df["date"].min()),
        "date_max": str(df["date"].max()),
        "year_min": int(df["year"].min()) if "year" in df else None,
        "year_max": int(df["year"].max()) if "year" in df else None,
        "split_counts": {str(k): int(v) for k, v in df.groupby("split").size().to_dict().items()} if "split" in df else {},
        "feature_missingness_pct": missingness,
        "sst_min": None if "sst_c" not in df else float(df["sst_c"].min()),
        "sst_max": None if "sst_c" not in df else float(df["sst_c"].max()),
        "sst_mean": None if "sst_c" not in df else float(df["sst_c"].mean()),
        "depth_min": None if "depth_m" not in df or df["depth_m"].isna().all() else float(df["depth_m"].min()),
        "depth_max": None if "depth_m" not in df or df["depth_m"].isna().all() else float(df["depth_m"].max()),
        "depth_mean": None if "depth_m" not in df or df["depth_m"].isna().all() else float(df["depth_m"].mean()),
        "high_match_distance_presence": int(df.get("high_match_distance", False).fillna(False).sum()) if "high_match_distance" in df else 0,
        "low_source_quality_records": int((df.get("source_quality", "") == "low").sum()) if "source_quality" in df else 0,
        "background_dates_subset_of_presence_dates": set(df[df["label"] == 0]["date"]).issubset(set(df[df["label"] == 1]["date"])),
        "notes": "Labels are presence/background, not catch/no-catch ground truth.",
    }
    return result


def write_report(summary: dict) -> None:
    lines = [
        "# Training Dataset Report",
        "",
        "This report validates training-ready presence/background samples. No model training is performed.",
        "",
        "Occurrence labels are presence-only public records. Background samples are pseudo-absence / available ocean environment, not true absence. Outputs should support relative habitat suitability / hotspot scoring, not exact fish locations or true catch probability.",
        "",
        "Dynamic features must be aligned to occurrence dates. SST is required for v1. Bathymetry and structure are static. Physics and chlorophyll are optional and remain NaN when unavailable.",
        "",
        "## Species Summary",
        "",
        "| Species | Status | Total | Presence | Background | Dates | Date Range |",
        "| --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for species_id, item in summary.items():
        lines.append(
            f"| {species_id} | {item.get('status')} | {item.get('total_samples', 0)} | {item.get('presence_samples', 0)} | {item.get('background_samples', 0)} | {item.get('unique_dates', 0)} | {item.get('date_min', '')} to {item.get('date_max', '')} |"
        )
    lines.extend(
        [
            "",
            "## Missing Data Notes",
            "",
            "- If a species has no training samples, the required date-aligned SST feature grid was unavailable for its occurrence dates.",
            "- Optional physics/chlorophyll missingness does not block v1 samples.",
            "- If GEBCO is missing, bathymetry features remain unavailable and confidence should be lower.",
            "",
            "## Recommended Model Training Sequence",
            "",
            "1. First train only species with status `trainable_sst_bathy_only` or `trainable_low_confidence`.",
            "2. Keep rule-based scoring for species marked `rule_based_only_insufficient_occurrence`.",
            "3. Add verified MUR SST subsets before expanding model training.",
        ]
    )
    report = "\n".join(lines)
    (cfg.DATA / "processed" / "reports" / "TRAINING_DATASET_REPORT.md").write_text(report, encoding="utf-8")
    (cfg.ROOT / "docs" / "TRAINING_DATASET_REPORT.md").write_text(report, encoding="utf-8")


def main() -> None:
    ensure_dirs()
    summary = {species_id: validate_species(species_id) for species_id in TARGET_SPECIES}
    write_json(cfg.DATA / "processed" / "reports" / "training_dataset_summary.json", summary)
    write_report(summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
