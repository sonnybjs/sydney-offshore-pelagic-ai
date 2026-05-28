from pipeline_lib import cfg, bbox_to_wkt, ensure_dirs, file_size_mb, parse_date, request_json, write_json, write_rows_csv


FIELDS = [
    "scientificName", "decimalLatitude", "decimalLongitude", "eventDate", "year", "month", "day",
    "coordinateUncertaintyInMeters", "basisOfRecord", "datasetName", "institutionCode", "occurrenceID",
    "license", "id", "date_start", "date_mid", "date_end", "date_year"
]


def download_species(species_id: str, scientific_name: str) -> list[dict]:
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
        print(f"{species_id}: downloaded {len(rows)} / {total}")
        if not batch or len(rows) >= total:
            break
        offset += page_size
    out_dir = cfg.DATA / "raw" / "occurrence" / "obis"
    audit_rows = []
    for row in rows:
        parsed = parse_date(row.get("eventDate") or row.get("date_mid") or row.get("date_start"))
        if parsed and not (cfg.START_DATE_FIRST_RUN <= parsed.isoformat() <= cfg.END_DATE_FIRST_RUN):
            continue
        audit_rows.append(row)
    payload = {
        "species_id": species_id,
        "scientific_name": scientific_name,
        "bbox": cfg.TRAIN_BBOX,
        "requested_date_range": [cfg.START_DATE_FIRST_RUN, cfg.END_DATE_FIRST_RUN],
        "note": "OBIS date filtering is applied locally if not supported by the API response.",
        "records": audit_rows,
    }
    write_json(out_dir / f"{species_id}_obis_raw.json", payload)
    cleaned = [{**{field: row.get(field) for field in FIELDS}, "species_id": species_id, "source": "OBIS"} for row in audit_rows]
    csv_path = out_dir / f"{species_id}_obis_raw.csv"
    write_rows_csv(csv_path, cleaned, FIELDS + ["species_id", "source"])
    return audit_rows


def main() -> None:
    ensure_dirs()
    print("OBIS occurrence download - audit only")
    print(
        {
            "bbox": cfg.TRAIN_BBOX,
            "date_range": [cfg.START_DATE_FIRST_RUN, cfg.END_DATE_FIRST_RUN],
            "estimated_size": "<100 MB for selected species and TRAIN_BBOX; stop if >500 MB",
        }
    )
    summary = {}
    for species_id, meta in cfg.SPECIES_CONFIG.items():
        try:
            rows = download_species(species_id, meta["scientific_name"])
            csv_path = cfg.DATA / "raw" / "occurrence" / "obis" / f"{species_id}_obis_raw.csv"
            json_path = cfg.DATA / "raw" / "occurrence" / "obis" / f"{species_id}_obis_raw.json"
            summary[species_id] = {
                "raw_count": len(rows),
                "status": "downloaded",
                "csv": str(csv_path.relative_to(cfg.ROOT)),
                "csv_size_mb": file_size_mb(csv_path),
                "json": str(json_path.relative_to(cfg.ROOT)),
                "json_size_mb": file_size_mb(json_path),
            }
        except Exception as exc:
            summary[species_id] = {"raw_count": 0, "status": f"failed: {type(exc).__name__}: {exc}"}
            print(summary[species_id]["status"])
    total_mb = sum(item.get("csv_size_mb", 0) + item.get("json_size_mb", 0) for item in summary.values())
    summary["_audit"] = {
        "total_raw_mb": round(total_mb, 4),
        "safe_under_500mb": total_mb < 500,
        "will_not_download": ["Western Australia", "full Australia", "global datasets"],
    }
    if total_mb > 500:
        write_json(cfg.DATA / "raw" / "occurrence" / "obis" / "obis_download_summary.json", summary)
        raise SystemExit("OBIS raw download exceeded 500 MB audit safety rule.")
    write_json(cfg.DATA / "raw" / "occurrence" / "obis" / "obis_download_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
