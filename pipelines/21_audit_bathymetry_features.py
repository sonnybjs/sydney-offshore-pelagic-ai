from __future__ import annotations

import numpy as np
import pandas as pd

from model_audit_lib import TARGET_SPECIES, ensure_audit_dirs, load_prediction_table, prediction_candidates, species_audit_dir
from pipeline_lib import write_json


def numeric(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index)
    return pd.to_numeric(df[col], errors="coerce")


def correlation(df: pd.DataFrame, a: str, b: str):
    if a not in df.columns or b not in df.columns:
        return None
    sub = df[[a, b]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(sub) < 3 or sub[a].nunique() <= 1 or sub[b].nunique() <= 1:
        return None
    return float(sub[a].corr(sub[b]))


def audit_file(path) -> dict:
    df = load_prediction_table(path)
    depth = numeric(df, "depth_m")
    ocean_mask = df["ocean_mask"] if "ocean_mask" in df.columns else pd.Series([np.nan] * len(df))
    if ocean_mask.dtype == object:
        ocean_bool = ocean_mask.astype(str).str.lower().isin(["true", "1", "yes"])
    else:
        ocean_bool = ocean_mask.fillna(False).astype(bool)
    result = {
        "file": str(path),
        "cell_count": int(len(df)),
        "has_depth_m": "depth_m" in df.columns,
        "depth_min": None if depth.dropna().empty else float(depth.min()),
        "depth_median": None if depth.dropna().empty else float(depth.median()),
        "depth_max": None if depth.dropna().empty else float(depth.max()),
        "cells_depth_le_0": int((depth <= 0).sum()),
        "cells_depth_lt_20": int((depth < 20).sum()),
        "cells_depth_lt_50": int((depth < 50).sum()),
        "cells_depth_gt_200": int((depth > 200).sum()),
        "land_or_non_ocean_cells": int((~ocean_bool).sum()) if "ocean_mask" in df.columns else None,
        "score_depth_correlation": correlation(df, "score", "depth_m"),
        "score_distance_to_shelf_break_correlation": correlation(df, "score", "distance_to_shelf_break"),
        "distance_to_200m_min": None if numeric(df, "distance_to_200m_contour").dropna().empty else float(numeric(df, "distance_to_200m_contour").min()),
        "distance_to_500m_min": None if numeric(df, "distance_to_500m_contour").dropna().empty else float(numeric(df, "distance_to_500m_contour").min()),
        "distance_to_1000m_min": None if numeric(df, "distance_to_1000m_contour").dropna().empty else float(numeric(df, "distance_to_1000m_contour").min()),
        "distance_to_shelf_break_min": None if numeric(df, "distance_to_shelf_break").dropna().empty else float(numeric(df, "distance_to_shelf_break").min()),
    }
    result["bathymetry_suspicious"] = bool(
        result["has_depth_m"] and result["cell_count"] > 0 and result["cells_depth_lt_50"] / max(1, result["cell_count"]) > 0.4
    )
    return result


def audit_species(species_id: str) -> dict:
    reports = []
    for path in prediction_candidates(species_id):
        if path.suffix.lower() == ".geojson":
            sibling = path.with_suffix(".parquet")
            if sibling.exists():
                path = sibling
            elif path.with_suffix(".csv").exists():
                path = path.with_suffix(".csv")
        try:
            reports.append(audit_file(path))
        except Exception as exc:
            reports.append({"file": str(path), "error": f"{type(exc).__name__}: {exc}"})
    status = {
        "species_id": species_id,
        "files": reports,
        "offshore_display_mask_recommendation": "Apply species-specific minimum depth display mask; this prevents invalid display but does not replace model correction.",
    }
    out_dir = species_audit_dir(species_id)
    write_json(out_dir / "bathymetry_features_audit.json", status)
    lines = [f"# Bathymetry Feature Audit: {species_id}", ""]
    for item in reports:
        lines.append(f"## {item.get('file')}")
        for key, value in item.items():
            if key != "file":
                lines.append(f"- {key}: `{value}`")
        lines.append("")
    (out_dir / "bathymetry_features_audit.md").write_text("\n".join(lines), encoding="utf-8")
    return status


def main() -> None:
    ensure_audit_dirs()
    summary = {species_id: audit_species(species_id) for species_id in TARGET_SPECIES}
    print(summary)


if __name__ == "__main__":
    main()
