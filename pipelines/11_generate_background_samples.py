from __future__ import annotations

import random

from pipeline_lib import append_provenance, cfg, ensure_dirs, read_table, save_dataframe, write_json
from training_prep_lib import TARGET_SPECIES, load_feature_grid


BACKGROUND_RATIO = 10
MAX_BACKGROUND_PER_SPECIES = 200_000


def generate_species(species_id: str) -> dict:
    import pandas as pd

    presence_path = cfg.DATA / "interim" / "matched_presence" / f"{species_id}_presence.csv"
    if not presence_path.exists():
        return {"presence_count": 0, "background_count": 0, "status": "missing_presence"}
    presence = read_table(presence_path)
    if presence.empty:
        empty = pd.DataFrame(
            columns=[
                "species_id",
                "date",
                "grid_lat",
                "grid_lon",
                "grid_id",
                "label",
                "sample_type",
                "background_strategy",
            ]
        )
        outputs = save_dataframe(
            empty,
            cfg.DATA / "interim" / "background_samples" / f"{species_id}_background.csv",
            cfg.DATA / "interim" / "background_samples" / f"{species_id}_background.parquet",
        )
        return {
            "presence_count": 0,
            "background_count": 0,
            "status": "empty_presence",
            "outputs": outputs,
            "note": "No background samples generated because no date-aligned presence samples exist.",
        }
    rows = []
    insufficient_dates = 0
    random.seed(42)
    for date_text, group in presence.groupby("date"):
        features = load_feature_grid(str(date_text))
        if features.empty:
            insufficient_dates += 1
            continue
        candidates = features[features["has_sst"].astype(bool) & features["sst_c"].notna()].copy()
        if "ocean_mask" in candidates.columns and candidates["ocean_mask"].notna().any():
            candidates = candidates[candidates["ocean_mask"].fillna(True).astype(bool)]
        presence_cells = set(group["grid_id"].dropna().astype(str))
        candidates = candidates[~candidates["grid_id"].astype(str).isin(presence_cells)]
        if candidates.empty:
            insufficient_dates += 1
            continue
        needed = min(len(group) * BACKGROUND_RATIO, MAX_BACKGROUND_PER_SPECIES - len(rows))
        replace = needed > len(candidates)
        if replace:
            insufficient_dates += 1
        sample = candidates.sample(n=needed, replace=replace, random_state=(hash((species_id, date_text)) & 0xFFFFFFFF))
        for item in sample.to_dict("records"):
            item.update(
                {
                    "species_id": species_id,
                    "scientific_name": cfg.SPECIES_CONFIG[species_id]["scientific_name"],
                    "common_name": cfg.SPECIES_CONFIG[species_id]["common_name"],
                    "grid_lat": item.get("lat"),
                    "grid_lon": item.get("lon"),
                    "label": 0,
                    "sample_type": "background",
                    "background_strategy": "same_date_random_ocean",
                    "occurrence_lat": float("nan"),
                    "occurrence_lon": float("nan"),
                    "match_distance_km": float("nan"),
                    "high_match_distance": False,
                    "source": "background",
                    "source_quality": "background",
                    "occurrence_id": "",
                    "dataset_name": "",
                }
            )
            rows.append(item)
        if len(rows) >= MAX_BACKGROUND_PER_SPECIES:
            break
    df = pd.DataFrame(rows)
    outputs = save_dataframe(
        df,
        cfg.DATA / "interim" / "background_samples" / f"{species_id}_background.csv",
        cfg.DATA / "interim" / "background_samples" / f"{species_id}_background.parquet",
    )
    summary = {
        "presence_count": int(len(presence)),
        "background_count": int(len(df)),
        "dates_used": int(presence["date"].nunique()),
        "average_background_per_presence": 0 if len(presence) == 0 else round(len(df) / len(presence), 4),
        "dates_with_insufficient_background_cells": insufficient_dates,
        "outputs": outputs,
        "note": "Background samples are pseudo-absence / available environment, not true absence.",
    }
    append_provenance(
        {
            "dataset_name": f"{species_id}_background_samples",
            "source_name": "Same-date random ocean background cells",
            "source_url_or_access_method": "Generated from local date-aligned feature grids",
            "spatial_bbox": cfg.TRAIN_BBOX,
            "time_range": "presence dates only",
            "variables": "background label + environmental features",
            "raw_file_path": "data/interim/feature_grid/daily_features",
            "processed_file_path": outputs.get("csv", ""),
            "estimated_size_mb": "<500",
            "actual_size_mb": outputs.get("csv_size_mb", ""),
            "license_or_terms_note": "Derived pseudo-absence/background samples",
            "used_for_training": True,
            "notes": "Background samples are not true absences.",
        }
    )
    return summary


def main() -> None:
    ensure_dirs()
    summary = {}
    for species_id in TARGET_SPECIES:
        summary[species_id] = generate_species(species_id)
        print(species_id, summary[species_id])
    write_json(cfg.DATA / "interim" / "background_samples" / "background_summary.json", summary)


if __name__ == "__main__":
    main()
