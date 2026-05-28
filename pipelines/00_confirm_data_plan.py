from pipeline_lib import cfg, ensure_dirs, format_bbox, markdown_table, write_json


DATASET_ROWS = [
    [
        "OBIS occurrence",
        "Presence/occurrence audit for target species",
        f"TRAIN_BBOX: {format_bbox(cfg.TRAIN_BBOX)}",
        f"{cfg.START_DATE_FIRST_RUN} to {cfg.END_DATE_FIRST_RUN}",
        "scientificName, decimalLatitude, decimalLongitude, eventDate, uncertainty, basisOfRecord, dataset metadata",
        "yes",
        "<100 MB expected; stop if >500 MB",
        "Species + TRAIN_BBOX only; no WA, full Australia, or global download",
    ],
    [
        "NASA MUR SST one-date smoke test",
        "Check remote subset access for future SST features",
        f"PREDICT_BBOX: {format_bbox(cfg.PREDICT_BBOX)}",
        cfg.MUR_AUDIT_DATE,
        "analysed_sst; derived sst_c, approximate gradient if available",
        "yes",
        "<50 MB expected; stop if >500 MB",
        "One date only; no global files; no full training history",
    ],
    [
        "GEBCO local subset reader/manual instructions",
        "Bathymetry setup for depth/shelf features",
        f"TRAIN_BBOX: {format_bbox(cfg.TRAIN_BBOX)}",
        "static",
        "elevation/depth; derived depth_m, slope, ocean_mask where local file exists",
        "read local only",
        "<1 GB subset expected",
        "Do not download global GEBCO; read data/raw/bathymetry/gebco/gebco_nsw_subset.nc only",
    ],
    [
        "Copernicus physics",
        "Future current and sea-surface-height predictors",
        "TRAIN_BBOX later; PREDICT_BBOX later",
        "later unique occurrence dates only",
        "uo, vo, zos; thetao/mlotst optional",
        "no",
        "0 MB in this audit",
        "Setup/document only; no bulk physics download",
    ],
    [
        "Copernicus chlorophyll",
        "Future productivity/chlorophyll edge predictors",
        "TRAIN_BBOX later; PREDICT_BBOX later",
        "later unique occurrence dates only",
        "CHL, CHL_gradient if available",
        "no",
        "0 MB in this audit",
        "Document only; no chlorophyll download",
    ],
    [
        "NSW DPI/FAD/POI",
        "Future validation, local prior, structure features",
        "Sydney/NSW offshore demo points only",
        "static/manual",
        "demo POI attributes only",
        "no scraping",
        "<1 MB placeholders",
        "Manual/demo placeholder only; mark demo_only=true and verified=false",
    ],
]


def confirmation_payload() -> dict:
    return {
        "title": "DATA DOWNLOAD CONFIRMATION - AUDIT ONLY",
        "prediction_bbox": cfg.PREDICT_BBOX,
        "training_bbox": cfg.TRAIN_BBOX,
        "optional_extended_bbox": cfg.OPTIONAL_EXTENDED_BBOX,
        "species": cfg.SPECIES_CONFIG,
        "estimated_raw_cache_size_gb": 0.2,
        "raw_download_size_limit_gb": cfg.RAW_DOWNLOAD_SIZE_LIMIT_GB,
        "under_limit": True,
        "will_not_download": ["Western Australia", "full Australia", "global datasets"],
        "dataset_rows": DATASET_ROWS,
    }


def main() -> None:
    ensure_dirs()
    headers = ["Dataset", "Purpose", "Spatial scope", "Time scope", "Variables", "Download now?", "Expected size", "Safety rule"]
    payload = confirmation_payload()
    print("\nDATA DOWNLOAD CONFIRMATION - AUDIT ONLY\n")
    print(markdown_table(headers, DATASET_ROWS))
    print("\nTotal expected raw/cache size for this audit: <= 0.2 GB.")
    print(f"Under 10 GB limit: {'yes' if payload['under_limit'] else 'no'}.")
    print("This audit will not download Western Australia, full Australia, or global datasets.")
    if payload["estimated_raw_cache_size_gb"] > cfg.RAW_DOWNLOAD_SIZE_LIMIT_GB:
        raise SystemExit("Estimated raw/cache size exceeds 10 GB. Stop and ask for permission.")
    write_json(cfg.DATA / "cache" / "downloads" / "audit_download_confirmation.json", payload)


if __name__ == "__main__":
    main()
