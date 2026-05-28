from __future__ import annotations

from datetime import datetime, timezone

from pipeline_lib import cfg, ensure_dirs, format_bbox, markdown_table


def read_json(path, default):
    import json

    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    ensure_dirs()
    confirmation = read_json(cfg.DATA / "cache" / "downloads" / "audit_download_confirmation.json", {})
    obis = read_json(cfg.DATA / "raw" / "occurrence" / "obis" / "obis_download_summary.json", {})
    gbif = read_json(cfg.DATA / "raw" / "occurrence" / "gbif" / "gbif_download_summary.json", {})
    cleaning = read_json(cfg.DATA / "interim" / "occurrence_clean" / "cleaning_summary.json", {})
    gbif_cleaning = read_json(cfg.DATA / "interim" / "occurrence_clean" / "gbif_cleaning_summary.json", {})
    extended_2002 = read_json(cfg.DATA / "interim" / "occurrence_clean" / "extended_2002_cleaning_summary.json", {})
    dates = read_json(cfg.DATA / "interim" / "date_lists" / "unique_training_dates_summary.json", {})
    mur = read_json(cfg.DATA / "interim" / "env_raw_index" / "mur_sst_smoke_summary.json", {})
    gebco = read_json(cfg.DATA / "interim" / "env_raw_index" / "gebco_status.json", {})
    structure = read_json(cfg.DATA / "interim" / "env_raw_index" / "structure_placeholder_status.json", {})

    dataset_rows = confirmation.get("dataset_rows", [])
    dataset_table = markdown_table(
        ["Dataset", "Purpose", "Spatial scope", "Time scope", "Variables", "Download now?", "Expected size", "Safety rule"],
        dataset_rows,
    ) if dataset_rows else "Confirmation file was not found."

    occurrence_rows = []
    for species_id, meta in cfg.SPECIES_CONFIG.items():
        raw = obis.get(species_id, {})
        clean = cleaning.get(species_id, {})
        gbif_raw = gbif.get(species_id, {})
        gbif_clean = gbif_cleaning.get(species_id, {})
        occurrence_rows.append(
            [
                species_id,
                meta["scientific_name"],
                raw.get("raw_count", "n/a"),
                clean.get("cleaned_count", "n/a"),
                gbif_raw.get("raw_count", "n/a"),
                gbif_clean.get("cleaned_count", "n/a"),
                clean.get("unique_dates", "n/a"),
                clean.get("records_in_prediction_bbox", "n/a"),
                gbif_clean.get("training_eligibility", clean.get("training_eligibility", "n/a")),
            ]
        )
    occurrence_table = markdown_table(
        ["Species ID", "Scientific name", "Raw OBIS", "Cleaned OBIS", "Raw GBIF", "Cleaned GBIF", "OBIS unique dates", "OBIS prediction bbox records", "Best audit eligibility"],
        occurrence_rows,
    )

    extended_rows = []
    for species_id in ["yellowfin_tuna", "mahi_mahi", "striped_marlin", "southern_bluefin_tuna"]:
        meta = cfg.SPECIES_CONFIG[species_id]
        item = extended_2002.get(species_id, {})
        extended_rows.append(
            [
                species_id,
                meta["scientific_name"],
                item.get("cleaned_count", "n/a"),
                item.get("unique_dates", "n/a"),
                item.get("year_min", "n/a"),
                item.get("year_max", "n/a"),
                item.get("records_in_prediction_bbox", "n/a"),
                item.get("training_eligibility", "not run"),
            ]
        )
    extended_table = markdown_table(
        ["Species ID", "Scientific name", "Cleaned 2002+", "Unique dates", "Year min", "Year max", "Prediction bbox records", "Eligibility"],
        extended_rows,
    )

    report = f"""# Data Audit Report

Project: Sydney Offshore Pelagic AI Map

Audit generated: {datetime.now(timezone.utc).isoformat()}

This audit checks whether enough real data exists around Sydney / NSW East Coast to later train offshore pelagic relative habitat suitability models. It does not train models and does not claim exact fish locations.

## Spatial Scope

- Prediction bbox: {format_bbox(cfg.PREDICT_BBOX)}
- Training bbox: {format_bbox(cfg.TRAIN_BBOX)}
- Optional extended East Coast bbox: {format_bbox(cfg.OPTIONAL_EXTENDED_BBOX)}
- This audit does not download Western Australia, full Australia, or global datasets.

## Dataset Confirmation

{dataset_table}

Estimated first-run raw/cache size: <= 0.2 GB for this audit, under the {cfg.RAW_DOWNLOAD_SIZE_LIMIT_GB} GB hard limit.

## Species And Date Range

- First audit range: {cfg.START_DATE_FIRST_RUN} to {cfg.END_DATE_FIRST_RUN}
- Full possible range later if records are sparse: {cfg.START_DATE_FULL} to {cfg.END_DATE_FIRST_RUN}
- MUR SST starts at {cfg.START_DATE_FULL}; occurrence records before that are not useful for MUR-matched training.

{occurrence_table}

## Extended 2002 Occurrence Audit

This optional audit expands only tuna/marlin/mahi/SBT back to {cfg.START_DATE_FULL}, still inside TRAIN_BBOX only. It does not include Western Australia, full Australia, or global downloads.

{extended_table}

## Unique Date List

- Total unique dates before sampling: {dates.get('total_unique_dates_before_sampling', 'n/a')}
- Total rows after sampling: {dates.get('total_rows_after_sampling', 'n/a')}
- Date min: {dates.get('date_min', 'n/a')}
- Date max: {dates.get('date_max', 'n/a')}
- Output: {dates.get('outputs', {}).get('csv', 'n/a')}

## NASA MUR SST Smoke Test

- Status: {mur.get('status', 'n/a')}
- Test date: {mur.get('date', cfg.MUR_AUDIT_DATE)}
- BBox: {mur.get('bbox', cfg.PREDICT_BBOX)}
- Cell count: {mur.get('cell_count', 'n/a')}
- Min SST C: {mur.get('min_sst_c', 'n/a')}
- Max SST C: {mur.get('max_sst_c', 'n/a')}
- Mean SST C: {mur.get('mean_sst_c', 'n/a')}
- Missing percentage: {mur.get('missing_percentage', 'n/a')}
- Gradient computed: {mur.get('gradient_computed', 'n/a')}
- Error if any: {mur.get('error', 'none')}

## GEBCO Status

- Status: {gebco.get('status', 'n/a')}
- Expected local file: {gebco.get('expected_path', 'data/raw/bathymetry/gebco/gebco_nsw_subset.nc')}
- Instructions: {gebco.get('instructions', 'docs/GEBCO_DOWNLOAD_INSTRUCTIONS.md')}
- Rule: no global GEBCO download is performed by this audit.
- Automatic subset status: {read_json(cfg.DATA / 'interim' / 'env_raw_index' / 'gebco_auto_download_status.json', {}).get('status', 'not_run')}

## FAD / POI Placeholder Status

- Status: {structure.get('status', 'n/a')}
- FAD placeholder count: {structure.get('fad_points', 'n/a')}
- POI placeholder count: {structure.get('poi_points', 'n/a')}
- All placeholder points are demo_only=true and verified=false.

## Future Copernicus Plan

Copernicus Marine physics and chlorophyll are not downloaded in this audit. Later integration should use remote subset access, surface layer only for physics, and unique occurrence dates only. Physics variables planned: `uo`, `vo`, `zos`, optional `thetao` and `mlotst`. Chlorophyll variables planned: `CHL` and `CHL_gradient` if available, with nearest valid date search within +/- 3 days for cloud gaps.

## Limitations

- OBIS is occurrence/presence data, not catch/no-catch effort data.
- Background samples later are not true absence.
- Sydney-only records may be sparse.
- The East Coast corridor is used to learn habitat preference while avoiding Western Australia.
- MUR SST gives temperature context, not fish location.
- GEBCO gives bathymetry context, not live fish data.
- Copernicus current/chlorophyll are planned but not downloaded in this audit.
- This project predicts relative habitat suitability / hotspot score, not exact fish locations.

## Recommended Next Step

If OBIS counts are sparse for yellowfin tuna, striped marlin, or yellowtail kingfish in 2015-2025, run a second audit extending only those species back to {cfg.START_DATE_FULL}. Then add verified remote MUR subset access for occurrence dates before building training samples.
"""
    out = cfg.ROOT / "docs" / "DATA_AUDIT_REPORT.md"
    out.write_text(report, encoding="utf-8")
    print({"status": "written", "report": str(out.relative_to(cfg.ROOT))})


if __name__ == "__main__":
    main()
