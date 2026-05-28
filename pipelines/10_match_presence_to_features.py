from __future__ import annotations

from pipeline_lib import append_provenance, cfg, ensure_dirs, haversine_km, in_bbox, nearest_grid_value, save_dataframe, write_json
from training_prep_lib import TARGET_SPECIES, grid_id, load_best_occurrences, load_feature_grid


def match_species(species_id: str) -> dict:
    import pandas as pd

    occ = load_best_occurrences(species_id)
    if occ.empty:
        return {"input_cleaned": 0, "matched": 0, "status": "no_clean_occurrences"}
    rows = []
    stats = {
        "input_cleaned": int(len(occ)),
        "matched": 0,
        "dropped_missing_feature_date": 0,
        "dropped_missing_sst": 0,
        "dropped_land_cell": 0,
        "dropped_outside_bbox": 0,
        "high_match_distance_count": 0,
    }
    for date_text, group in occ.groupby("date"):
        features = load_feature_grid(str(date_text))
        if features.empty:
            stats["dropped_missing_feature_date"] += int(len(group))
            continue
        features = features.copy()
        features["match_lat"] = features["lat"].astype(float).round(4)
        features["match_lon"] = features["lon"].astype(float).round(4)
        lookup = features.set_index(["match_lat", "match_lon"])
        for item in group.itertuples():
            lat = float(item.decimalLatitude)
            lon = float(item.decimalLongitude)
            if not in_bbox(lat, lon, cfg.TRAIN_BBOX):
                stats["dropped_outside_bbox"] += 1
                continue
            grid_lat = nearest_grid_value(lat)
            grid_lon = nearest_grid_value(lon)
            try:
                feature = lookup.loc[(grid_lat, grid_lon)]
            except KeyError:
                stats["dropped_missing_feature_date"] += 1
                continue
            if isinstance(feature, pd.DataFrame):
                feature = feature.iloc[0]
            if not bool(feature.get("has_sst", False)) or pd.isna(feature.get("sst_c")):
                stats["dropped_missing_sst"] += 1
                continue
            if "ocean_mask" in feature.index and pd.notna(feature.get("ocean_mask")) and not bool(feature.get("ocean_mask")):
                stats["dropped_land_cell"] += 1
                continue
            match_distance = haversine_km(lat, lon, float(feature["lat"]), float(feature["lon"]))
            high_distance = match_distance > 10
            if high_distance:
                stats["high_match_distance_count"] += 1
            row = feature.to_dict()
            row.update(
                {
                    "species_id": species_id,
                    "scientific_name": cfg.SPECIES_CONFIG[species_id]["scientific_name"],
                    "common_name": cfg.SPECIES_CONFIG[species_id]["common_name"],
                    "date": str(date_text),
                    "occurrence_lat": lat,
                    "occurrence_lon": lon,
                    "grid_lat": float(feature["lat"]),
                    "grid_lon": float(feature["lon"]),
                    "grid_id": feature.get("grid_id", grid_id(float(feature["lat"]), float(feature["lon"]))),
                    "match_distance_km": round(match_distance, 4),
                    "high_match_distance": high_distance,
                    "label": 1,
                    "sample_type": "presence",
                    "source": getattr(item, "source", ""),
                    "source_quality": getattr(item, "source_quality", ""),
                    "occurrence_id": getattr(item, "occurrenceID", ""),
                    "dataset_name": getattr(item, "datasetName", ""),
                }
            )
            rows.append(row)
    presence_columns = [
        "species_id",
        "scientific_name",
        "common_name",
        "date",
        "occurrence_lat",
        "occurrence_lon",
        "grid_lat",
        "grid_lon",
        "grid_id",
        "match_distance_km",
        "high_match_distance",
        "label",
        "sample_type",
        "source",
        "source_quality",
        "occurrence_id",
        "dataset_name",
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        df = pd.DataFrame(columns=presence_columns)
    outputs = save_dataframe(
        df,
        cfg.DATA / "interim" / "matched_presence" / f"{species_id}_presence.csv",
        cfg.DATA / "interim" / "matched_presence" / f"{species_id}_presence.parquet",
    )
    stats["matched"] = int(len(df))
    stats["outputs"] = outputs
    append_provenance(
        {
            "dataset_name": f"{species_id}_matched_presence",
            "source_name": "OBIS/GBIF/ALA cleaned occurrence matched to daily feature grid",
            "source_url_or_access_method": "Local cleaned occurrence + date-aligned feature grid",
            "spatial_bbox": cfg.TRAIN_BBOX,
            "time_range": f"{cfg.START_DATE_FULL} to {cfg.END_DATE_FIRST_RUN}",
            "variables": "presence label + environmental features",
            "raw_file_path": "data/interim/occurrence_clean",
            "processed_file_path": outputs.get("csv", ""),
            "estimated_size_mb": "<100",
            "actual_size_mb": outputs.get("csv_size_mb", ""),
            "license_or_terms_note": "Occurrence source licenses retained per row where available",
            "used_for_training": True,
            "notes": "Presence-only data; not complete ground truth.",
        }
    )
    return stats


def main() -> None:
    ensure_dirs()
    summary = {}
    for species_id in TARGET_SPECIES:
        summary[species_id] = match_species(species_id)
        print(species_id, summary[species_id])
    write_json(cfg.DATA / "interim" / "matched_presence" / "matched_presence_summary.json", summary)


if __name__ == "__main__":
    main()
