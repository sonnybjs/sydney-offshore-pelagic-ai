from pipeline_lib import cfg, ensure_dirs, in_bbox, parse_date, read_rows_csv, save_dataframe, write_json


CLEAN_COLUMNS = [
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


def clean_species(species_id: str) -> dict:
    import pandas as pd

    meta = cfg.SPECIES_CONFIG[species_id]
    raw_path = cfg.DATA / "raw" / "occurrence" / "obis" / f"{species_id}_obis_raw.csv"
    if not raw_path.exists():
        legacy_path = cfg.DATA / "raw" / "occurrence" / "obis" / f"{species_id}_raw.csv"
        raw_path = legacy_path
    rows = read_rows_csv(raw_path)
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
        if d.isoformat() < cfg.START_DATE_FIRST_RUN:
            counts["removed_before_start"] += 1
            continue
        if d.isoformat() > cfg.END_DATE_FIRST_RUN:
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
        key = (species_id, d.isoformat(), round(lat, 4), round(lon, 4))
        if key in seen:
            counts["removed_duplicates"] += 1
            continue
        seen.add(key)
        if uncertainty_value is not None and uncertainty_value <= 1000:
            source_quality = "high"
        elif uncertainty_value is None or uncertainty_value <= 10000:
            source_quality = "medium"
        else:
            source_quality = "low"
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
                "occurrenceID": row.get("occurrenceID") or row.get("id"),
                "license": row.get("license"),
                "source": "OBIS",
                "source_quality": source_quality,
                "rounded_lat": round(lat, 4),
                "rounded_lon": round(lon, 4),
                "in_prediction_bbox": in_bbox(lat, lon, cfg.PREDICT_BBOX),
            }
        )
    df = pd.DataFrame(cleaned, columns=CLEAN_COLUMNS)
    outputs = save_dataframe(
        df,
        cfg.DATA / "interim" / "occurrence_clean" / f"{species_id}_clean.csv",
        cfg.DATA / "interim" / "occurrence_clean" / f"{species_id}_clean.parquet",
    )
    if df.empty:
        return {**counts, "cleaned_count": 0, "status": "empty", "training_eligibility": "insufficient for ML, use rule-based for now", "outputs": outputs}
    min_trainable = meta["min_records_trainable"]
    min_low = meta["min_records_low_confidence"]
    eligibility = (
        "trainable"
        if len(df) >= min_trainable
        else "trainable but low confidence"
        if len(df) >= min_low
        else "insufficient for ML, use rule-based for now"
    )
    return {
        **counts,
        "cleaned_count": int(len(df)),
        "year_min": int(df["year"].min()),
        "year_max": int(df["year"].max()),
        "unique_dates": int(df["date"].nunique()),
        "records_in_prediction_bbox": int(df["in_prediction_bbox"].sum()),
        "training_eligibility": eligibility,
        "outputs": outputs,
    }


def main() -> None:
    ensure_dirs()
    summary = {}
    for species_id in cfg.SPECIES_CONFIG:
        summary[species_id] = clean_species(species_id)
        print(species_id, summary[species_id])
    write_json(cfg.DATA / "interim" / "occurrence_clean" / "cleaning_summary.json", summary)


if __name__ == "__main__":
    main()
