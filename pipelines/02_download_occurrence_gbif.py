from __future__ import annotations

from urllib.parse import urlencode

from pipeline_lib import cfg, ensure_dirs, file_size_mb, request_json, write_json, write_rows_csv


GBIF_SPECIES_MATCH = "https://api.gbif.org/v1/species/match"
GBIF_OCCURRENCE_SEARCH = "https://api.gbif.org/v1/occurrence/search"
MAX_RECORDS_PER_SPECIES = 2000

FIELDS = [
    "scientificName",
    "decimalLatitude",
    "decimalLongitude",
    "eventDate",
    "year",
    "month",
    "day",
    "coordinateUncertaintyInMeters",
    "basisOfRecord",
    "datasetName",
    "institutionCode",
    "occurrenceID",
    "license",
    "gbifID",
    "species_id",
    "source",
]


def match_taxon(scientific_name: str) -> int | None:
    payload = request_json(GBIF_SPECIES_MATCH, {"name": scientific_name, "rank": "SPECIES"})
    usage_key = payload.get("usageKey")
    return int(usage_key) if usage_key else None


def download_species(species_id: str, scientific_name: str) -> dict:
    taxon_key = match_taxon(scientific_name)
    if not taxon_key:
        return {"status": "taxon_not_found", "raw_count": 0}

    rows: list[dict] = []
    offset = 0
    limit = 300
    bbox = cfg.TRAIN_BBOX
    while len(rows) < MAX_RECORDS_PER_SPECIES:
        payload = request_json(
            GBIF_OCCURRENCE_SEARCH,
            {
                "taxonKey": taxon_key,
                "hasCoordinate": "true",
                "decimalLatitude": f"{bbox['south_lat']},{bbox['north_lat']}",
                "decimalLongitude": f"{bbox['west_lon']},{bbox['east_lon']}",
                "eventDate": f"{cfg.START_DATE_FIRST_RUN},{cfg.END_DATE_FIRST_RUN}",
                "limit": limit,
                "offset": offset,
            },
        )
        batch = payload.get("results", [])
        if not batch:
            break
        rows.extend(batch)
        total = int(payload.get("count", len(rows)) or len(rows))
        print(f"{species_id}: GBIF downloaded {len(rows)} / {total}")
        if payload.get("endOfRecords") or len(rows) >= total:
            break
        offset += limit

    rows = rows[:MAX_RECORDS_PER_SPECIES]
    out_dir = cfg.DATA / "raw" / "occurrence" / "gbif"
    out_rows = []
    for row in rows:
        out_rows.append(
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
        )
    csv_path = out_dir / f"{species_id}_gbif_raw.csv"
    write_rows_csv(csv_path, out_rows, FIELDS)
    write_json(
        out_dir / f"{species_id}_gbif_raw.json",
        {
            "species_id": species_id,
            "scientific_name": scientific_name,
            "taxon_key": taxon_key,
            "bbox": cfg.TRAIN_BBOX,
            "date_range": [cfg.START_DATE_FIRST_RUN, cfg.END_DATE_FIRST_RUN],
            "max_records_per_species": MAX_RECORDS_PER_SPECIES,
            "records": out_rows,
        },
    )
    return {
        "status": "downloaded",
        "taxon_key": taxon_key,
        "raw_count": len(out_rows),
        "csv": str(csv_path.relative_to(cfg.ROOT)),
        "csv_size_mb": file_size_mb(csv_path),
    }


def main() -> None:
    ensure_dirs()
    print("GBIF occurrence download - audit expansion only")
    print(
        {
            "bbox": cfg.TRAIN_BBOX,
            "date_range": [cfg.START_DATE_FIRST_RUN, cfg.END_DATE_FIRST_RUN],
            "max_records_per_species": MAX_RECORDS_PER_SPECIES,
            "note": "No GBIF bulk download credentials required; this uses the public paged occurrence search API.",
        }
    )
    summary = {}
    for species_id, meta in cfg.SPECIES_CONFIG.items():
        try:
            summary[species_id] = download_species(species_id, meta["scientific_name"])
        except Exception as exc:
            summary[species_id] = {"status": f"failed: {type(exc).__name__}: {exc}", "raw_count": 0}
            print(summary[species_id]["status"])
    total_mb = sum(item.get("csv_size_mb", 0) for item in summary.values())
    summary["_audit"] = {
        "total_csv_mb": round(total_mb, 4),
        "safe_under_500mb": total_mb < 500,
        "will_not_download": ["Western Australia", "full Australia", "global datasets"],
    }
    write_json(cfg.DATA / "raw" / "occurrence" / "gbif" / "gbif_download_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
