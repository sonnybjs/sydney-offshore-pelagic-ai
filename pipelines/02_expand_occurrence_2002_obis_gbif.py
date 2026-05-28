from __future__ import annotations

from pipeline_lib import cfg, bbox_to_wkt, ensure_dirs, file_size_mb, parse_date, request_json, write_json, write_rows_csv


EXPAND_SPECIES = ["yellowfin_tuna", "mahi_mahi", "striped_marlin", "southern_bluefin_tuna"]
START_DATE = cfg.START_DATE_FULL
END_DATE = cfg.END_DATE_FIRST_RUN
MAX_GBIF_RECORDS_PER_SPECIES = 5000

OBIS_FIELDS = [
    "scientificName", "decimalLatitude", "decimalLongitude", "eventDate", "year", "month", "day",
    "coordinateUncertaintyInMeters", "basisOfRecord", "datasetName", "institutionCode", "occurrenceID",
    "license", "id", "date_start", "date_mid", "date_end", "date_year", "species_id", "source"
]

GBIF_FIELDS = [
    "scientificName", "decimalLatitude", "decimalLongitude", "eventDate", "year", "month", "day",
    "coordinateUncertaintyInMeters", "basisOfRecord", "datasetName", "institutionCode", "occurrenceID",
    "license", "gbifID", "species_id", "source"
]


def in_extended_date(row: dict) -> bool:
    parsed = parse_date(row.get("eventDate") or row.get("date_mid") or row.get("date_start") or row.get("date_end"))
    return bool(parsed and START_DATE <= parsed.isoformat() <= END_DATE)


def download_obis_species(species_id: str, scientific_name: str) -> dict:
    rows: list[dict] = []
    offset = 0
    page_size = 5000
    while True:
        payload = request_json(
            cfg.OBIS_API,
            {
                "scientificname": scientific_name,
                "geometry": bbox_to_wkt(cfg.TRAIN_BBOX),
                "size": page_size,
                "offset": offset,
            },
        )
        batch = payload.get("results", [])
        rows.extend(batch)
        total = int(payload.get("total", len(rows)) or len(rows))
        print(f"{species_id}: OBIS fetched {len(rows)} / {total}")
        if not batch or len(rows) >= total:
            break
        offset += page_size
    filtered = [row for row in rows if in_extended_date(row)]
    out_dir = cfg.DATA / "raw" / "occurrence" / "obis"
    out_rows = [{**{field: row.get(field) for field in OBIS_FIELDS}, "species_id": species_id, "source": "OBIS"} for row in filtered]
    csv_path = out_dir / f"{species_id}_obis_2002_raw.csv"
    json_path = out_dir / f"{species_id}_obis_2002_raw.json"
    write_rows_csv(csv_path, out_rows, OBIS_FIELDS)
    write_json(
        json_path,
        {
            "species_id": species_id,
            "scientific_name": scientific_name,
            "bbox": cfg.TRAIN_BBOX,
            "date_range": [START_DATE, END_DATE],
            "records": out_rows,
        },
    )
    return {
        "raw_count": len(out_rows),
        "csv": str(csv_path.relative_to(cfg.ROOT)),
        "csv_size_mb": file_size_mb(csv_path),
        "json": str(json_path.relative_to(cfg.ROOT)),
        "json_size_mb": file_size_mb(json_path),
    }


def gbif_taxon_key(scientific_name: str) -> int | None:
    payload = request_json("https://api.gbif.org/v1/species/match", {"name": scientific_name, "rank": "SPECIES"})
    key = payload.get("usageKey")
    return int(key) if key else None


def download_gbif_species(species_id: str, scientific_name: str) -> dict:
    key = gbif_taxon_key(scientific_name)
    if not key:
        return {"raw_count": 0, "status": "taxon_not_found"}
    rows: list[dict] = []
    offset = 0
    limit = 300
    bbox = cfg.TRAIN_BBOX
    while len(rows) < MAX_GBIF_RECORDS_PER_SPECIES:
        payload = request_json(
            "https://api.gbif.org/v1/occurrence/search",
            {
                "taxonKey": key,
                "hasCoordinate": "true",
                "decimalLatitude": f"{bbox['south_lat']},{bbox['north_lat']}",
                "decimalLongitude": f"{bbox['west_lon']},{bbox['east_lon']}",
                "eventDate": f"{START_DATE},{END_DATE}",
                "limit": limit,
                "offset": offset,
            },
        )
        batch = payload.get("results", [])
        if not batch:
            break
        rows.extend(batch)
        total = int(payload.get("count", len(rows)) or len(rows))
        print(f"{species_id}: GBIF fetched {len(rows)} / {total}")
        if payload.get("endOfRecords") or len(rows) >= total:
            break
        offset += limit
    rows = rows[:MAX_GBIF_RECORDS_PER_SPECIES]
    out_dir = cfg.DATA / "raw" / "occurrence" / "gbif"
    out_rows = [
        {
            "scientificName": row.get("scientificName"),
            "decimalLatitude": row.get("decimalLatitude"),
            "decimalLongitude": row.get("decimalLongitude"),
            "eventDate": row.get("eventDate"),
            "year": row.get("year"),
            "month": row.get("month"),
            "day": row.get("day"),
            "coordinateUncertaintyInMeters": row.get("coordinateUncertaintyInMeters"),
            "basisOfRecord": row.get("basisOfRecord"),
            "datasetName": row.get("datasetName"),
            "institutionCode": row.get("institutionCode"),
            "occurrenceID": row.get("occurrenceID"),
            "license": row.get("license"),
            "gbifID": row.get("gbifID"),
            "species_id": species_id,
            "source": "GBIF",
        }
        for row in rows
    ]
    csv_path = out_dir / f"{species_id}_gbif_2002_raw.csv"
    json_path = out_dir / f"{species_id}_gbif_2002_raw.json"
    write_rows_csv(csv_path, out_rows, GBIF_FIELDS)
    write_json(
        json_path,
        {
            "species_id": species_id,
            "scientific_name": scientific_name,
            "taxon_key": key,
            "bbox": cfg.TRAIN_BBOX,
            "date_range": [START_DATE, END_DATE],
            "records": out_rows,
        },
    )
    return {
        "raw_count": len(out_rows),
        "taxon_key": key,
        "csv": str(csv_path.relative_to(cfg.ROOT)),
        "csv_size_mb": file_size_mb(csv_path),
        "json": str(json_path.relative_to(cfg.ROOT)),
        "json_size_mb": file_size_mb(json_path),
    }


def main() -> None:
    ensure_dirs()
    print("\nEXTENDED OCCURRENCE AUDIT CONFIRMATION\n")
    print(
        {
            "species": EXPAND_SPECIES,
            "bbox": cfg.TRAIN_BBOX,
            "date_range": [START_DATE, END_DATE],
            "sources": ["OBIS", "GBIF public occurrence search"],
            "expected_size": "<100 MB",
            "safety": "East Coast TRAIN_BBOX only; no Western Australia, no full Australia, no global download; no training.",
        }
    )
    summary = {"date_range": [START_DATE, END_DATE], "bbox": cfg.TRAIN_BBOX, "obis": {}, "gbif": {}}
    for species_id in EXPAND_SPECIES:
        meta = cfg.SPECIES_CONFIG[species_id]
        try:
            summary["obis"][species_id] = download_obis_species(species_id, meta["scientific_name"])
        except Exception as exc:
            summary["obis"][species_id] = {"raw_count": 0, "status": f"failed: {type(exc).__name__}: {exc}"}
        try:
            summary["gbif"][species_id] = download_gbif_species(species_id, meta["scientific_name"])
        except Exception as exc:
            summary["gbif"][species_id] = {"raw_count": 0, "status": f"failed: {type(exc).__name__}: {exc}"}
    total_mb = 0.0
    for source in ["obis", "gbif"]:
        for item in summary[source].values():
            total_mb += item.get("csv_size_mb", 0) + item.get("json_size_mb", 0)
    summary["total_raw_mb"] = round(total_mb, 4)
    summary["safe_under_10gb"] = total_mb < cfg.RAW_DOWNLOAD_SIZE_LIMIT_GB * 1024
    write_json(cfg.DATA / "raw" / "occurrence" / "extended_2002_occurrence_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
