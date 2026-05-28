from __future__ import annotations

from pipeline_lib import cfg, ensure_dirs, in_bbox, parse_date, read_rows_csv, save_dataframe, write_json


EXPAND_SPECIES = ["yellowfin_tuna", "mahi_mahi", "striped_marlin", "southern_bluefin_tuna"]
START_DATE = cfg.START_DATE_FULL
END_DATE = cfg.END_DATE_FIRST_RUN

COLUMNS = [
    "species_id",
    "common_name",
    "scientificName",
    "decimalLatitude",
    "decimalLongitude",
    "eventDate",
    "date",
    "year",
    "month",
    "day",
    "coordinateUncertaintyInMeters",
    "basisOfRecord",
    "datasetName",
    "institutionCode",
    "occurrenceID",
    "license",
    "source",
    "source_quality",
    "rounded_lat",
    "rounded_lon",
    "in_prediction_bbox",
]


def load_source_rows(source: str, species_id: str) -> list[dict]:
    path = cfg.DATA / "raw" / "occurrence" / source.lower() / f"{species_id}_{source.lower()}_2002_raw.csv"
    return read_rows_csv(path)


def clean_source_rows(source: str, species_id: str, rows: list[dict]) -> tuple[list[dict], dict]:
    meta = cfg.SPECIES_CONFIG[species_id]
    cleaned = []
    seen = set()
    counts = {
        "raw_count": len(rows),
        "removed_missing_coords": 0,
        "removed_missing_date": 0,
        "removed_before_start": 0,
        "removed_after_end": 0,
        "removed_outside_bbox": 0,
        "removed_invalid_coordinates": 0,
        "removed_high_uncertainty": 0,
        "removed_duplicates": 0,
    }
    for row in rows:
        try:
            lat = float(row.get("decimalLatitude") or "")
            lon = float(row.get("decimalLongitude") or "")
        except ValueError:
            counts["removed_missing_coords"] += 1
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            counts["removed_invalid_coordinates"] += 1
            continue
        d = parse_date(row.get("eventDate") or row.get("date_mid") or row.get("date_start") or row.get("date_end"))
        if not d:
            counts["removed_missing_date"] += 1
            continue
        if d.isoformat() < START_DATE:
            counts["removed_before_start"] += 1
            continue
        if d.isoformat() > END_DATE:
            counts["removed_after_end"] += 1
            continue
        if not in_bbox(lat, lon, cfg.TRAIN_BBOX):
            counts["removed_outside_bbox"] += 1
            continue
        uncertainty = row.get("coordinateUncertaintyInMeters")
        uncertainty_value = None
        try:
            if uncertainty not in (None, ""):
                uncertainty_value = float(uncertainty)
            if uncertainty_value is not None and uncertainty_value > 10000:
                counts["removed_high_uncertainty"] += 1
                continue
        except ValueError:
            uncertainty_value = None
        key = (species_id, source, d.isoformat(), round(lat, 4), round(lon, 4))
        if key in seen:
            counts["removed_duplicates"] += 1
            continue
        seen.add(key)
        quality = "high" if uncertainty_value is not None and uncertainty_value <= 1000 else "medium"
        cleaned.append(
            {
                "species_id": species_id,
                "common_name": meta["common_name"],
                "scientificName": row.get("scientificName"),
                "decimalLatitude": lat,
                "decimalLongitude": lon,
                "eventDate": row.get("eventDate") or row.get("date_mid") or row.get("date_start") or row.get("date_end"),
                "date": d.isoformat(),
                "year": d.year,
                "month": d.month,
                "day": d.day,
                "coordinateUncertaintyInMeters": uncertainty,
                "basisOfRecord": row.get("basisOfRecord"),
                "datasetName": row.get("datasetName"),
                "institutionCode": row.get("institutionCode"),
                "occurrenceID": row.get("occurrenceID") or row.get("id") or row.get("gbifID"),
                "license": row.get("license"),
                "source": source,
                "source_quality": quality,
                "rounded_lat": round(lat, 4),
                "rounded_lon": round(lon, 4),
                "in_prediction_bbox": in_bbox(lat, lon, cfg.PREDICT_BBOX),
            }
        )
    return cleaned, counts


def main() -> None:
    import pandas as pd

    ensure_dirs()
    summary = {}
    for species_id in EXPAND_SPECIES:
        all_cleaned = []
        source_counts = {}
        for source in ["OBIS", "GBIF"]:
            cleaned, counts = clean_source_rows(source, species_id, load_source_rows(source, species_id))
            all_cleaned.extend(cleaned)
            source_counts[source] = counts
        deduped = []
        seen = set()
        cross_source_duplicates = 0
        for row in sorted(all_cleaned, key=lambda item: (item["date"], item["source"])):
            key = (row["species_id"], row["date"], row["rounded_lat"], row["rounded_lon"])
            if key in seen:
                cross_source_duplicates += 1
                continue
            seen.add(key)
            deduped.append(row)
        df = pd.DataFrame(deduped, columns=COLUMNS)
        outputs = save_dataframe(
            df,
            cfg.DATA / "interim" / "occurrence_clean" / f"{species_id}_2002_extended_clean.csv",
            cfg.DATA / "interim" / "occurrence_clean" / f"{species_id}_2002_extended_clean.parquet",
        )
        meta = cfg.SPECIES_CONFIG[species_id]
        if df.empty:
            eligibility = "insufficient for ML, use rule-based for now"
            detail = {}
        else:
            eligibility = (
                "trainable"
                if len(df) >= meta["min_records_trainable"]
                else "trainable but low confidence"
                if len(df) >= meta["min_records_low_confidence"]
                else "insufficient for ML, use rule-based for now"
            )
            detail = {
                "year_min": int(df["year"].min()),
                "year_max": int(df["year"].max()),
                "unique_dates": int(df["date"].nunique()),
                "records_in_prediction_bbox": int(df["in_prediction_bbox"].sum()),
            }
        summary[species_id] = {
            "source_counts": source_counts,
            "cross_source_duplicates": cross_source_duplicates,
            "cleaned_count": int(len(df)),
            "training_eligibility": eligibility,
            "outputs": outputs,
            **detail,
        }
        print(species_id, summary[species_id])
    write_json(cfg.DATA / "interim" / "occurrence_clean" / "extended_2002_cleaning_summary.json", summary)


if __name__ == "__main__":
    main()
