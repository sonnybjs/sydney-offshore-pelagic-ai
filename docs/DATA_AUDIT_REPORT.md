# Data Audit Report

Project: Sydney Offshore Pelagic AI Map

Audit generated: 2026-05-26T12:07:25.212807+00:00

This audit checks whether enough real data exists around Sydney / NSW East Coast to later train offshore pelagic relative habitat suitability models. It does not train models and does not claim exact fish locations.

## Spatial Scope

- Prediction bbox: S -36.5, N -32.0, W 150.5, E 154.5
- Training bbox: S -39.0, N -27.0, W 148.5, E 158.5
- Optional extended East Coast bbox: S -44.5, N -25.0, W 145.0, E 160.5
- This audit does not download Western Australia, full Australia, or global datasets.

## Dataset Confirmation

| Dataset | Purpose | Spatial scope | Time scope | Variables | Download now? | Expected size | Safety rule |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OBIS occurrence | Presence/occurrence audit for target species | TRAIN_BBOX: S -39.0, N -27.0, W 148.5, E 158.5 | 2015-01-01 to 2025-12-31 | scientificName, decimalLatitude, decimalLongitude, eventDate, uncertainty, basisOfRecord, dataset metadata | yes | <100 MB expected; stop if >500 MB | Species + TRAIN_BBOX only; no WA, full Australia, or global download |
| NASA MUR SST one-date smoke test | Check remote subset access for future SST features | PREDICT_BBOX: S -36.5, N -32.0, W 150.5, E 154.5 | 2024-02-15 | analysed_sst; derived sst_c, approximate gradient if available | yes | <50 MB expected; stop if >500 MB | One date only; no global files; no full training history |
| GEBCO local subset reader/manual instructions | Bathymetry setup for depth/shelf features | TRAIN_BBOX: S -39.0, N -27.0, W 148.5, E 158.5 | static | elevation/depth; derived depth_m, slope, ocean_mask where local file exists | read local only | <1 GB subset expected | Do not download global GEBCO; read data/raw/bathymetry/gebco/gebco_nsw_subset.nc only |
| Copernicus physics | Future current and sea-surface-height predictors | TRAIN_BBOX later; PREDICT_BBOX later | later unique occurrence dates only | uo, vo, zos; thetao/mlotst optional | no | 0 MB in this audit | Setup/document only; no bulk physics download |
| Copernicus chlorophyll | Future productivity/chlorophyll edge predictors | TRAIN_BBOX later; PREDICT_BBOX later | later unique occurrence dates only | CHL, CHL_gradient if available | no | 0 MB in this audit | Document only; no chlorophyll download |
| NSW DPI/FAD/POI | Future validation, local prior, structure features | Sydney/NSW offshore demo points only | static/manual | demo POI attributes only | no scraping | <1 MB placeholders | Manual/demo placeholder only; mark demo_only=true and verified=false |

Estimated first-run raw/cache size: <= 0.2 GB for this audit, under the 10 GB hard limit.

## Species And Date Range

- First audit range: 2015-01-01 to 2025-12-31
- Full possible range later if records are sparse: 2002-06-01 to 2025-12-31
- MUR SST starts at 2002-06-01; occurrence records before that are not useful for MUR-matched training.

| Species ID | Scientific name | Raw OBIS | Cleaned OBIS | Raw GBIF | Cleaned GBIF | OBIS unique dates | OBIS prediction bbox records | Best audit eligibility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| yellowfin_tuna | Thunnus albacares | 14 | 0 | 7 | 6 | n/a | n/a | insufficient for ML, use rule-based for now |
| mahi_mahi | Coryphaena hippurus | 37 | 0 | 29 | 23 | n/a | n/a | insufficient for ML, use rule-based for now |
| striped_marlin | Kajikia audax | 8 | 0 | 3 | 0 | n/a | n/a | insufficient for ML, use rule-based for now |
| southern_bluefin_tuna | Thunnus maccoyii | 10 | 6 | 7 | 6 | 6 | 5 | insufficient for ML, use rule-based for now |
| yellowtail_kingfish | Seriola lalandi | 418 | 258 | 741 | 571 | 248 | 258 | trainable |

## Extended 2002 Occurrence Audit

This optional audit expands only tuna/marlin/mahi/SBT back to 2002-06-01, still inside TRAIN_BBOX only. It does not include Western Australia, full Australia, or global downloads.

| Species ID | Scientific name | Cleaned 2002+ | Unique dates | Year min | Year max | Prediction bbox records | Eligibility |
| --- | --- | --- | --- | --- | --- | --- | --- |
| yellowfin_tuna | Thunnus albacares | 7 | 7 | 2010 | 2025 | 3 | insufficient for ML, use rule-based for now |
| mahi_mahi | Coryphaena hippurus | 296 | 234 | 2005 | 2025 | 55 | trainable but low confidence |
| striped_marlin | Kajikia audax | 1 | 1 | 2004 | 2004 | 0 | insufficient for ML, use rule-based for now |
| southern_bluefin_tuna | Thunnus maccoyii | 422 | 296 | 2009 | 2020 | 169 | trainable |

## Unique Date List

- Total unique dates before sampling: 254
- Total rows after sampling: 254
- Date min: 2015-01-23
- Date max: 2020-04-09
- Output: data/interim/date_lists/unique_training_dates.csv

## NASA MUR SST Smoke Test

- Status: failed_remote_access
- Test date: 2024-02-15
- BBox: {'south_lat': -36.5, 'north_lat': -32.0, 'west_lon': 150.5, 'east_lon': 154.5}
- Cell count: n/a
- Min SST C: n/a
- Max SST C: n/a
- Mean SST C: n/a
- Missing percentage: n/a
- Gradient computed: n/a
- Error if any: HTTPError: HTTP Error 400: 

## GEBCO Status

- Status: local_subset_missing
- Expected local file: data/raw/bathymetry/gebco/gebco_nsw_subset.nc
- Instructions: docs/GEBCO_DOWNLOAD_INSTRUCTIONS.md
- Rule: no global GEBCO download is performed by this audit.
- Automatic subset status: not_available_via_known_public_api

## FAD / POI Placeholder Status

- Status: written
- FAD placeholder count: 3
- POI placeholder count: 4
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

If OBIS counts are sparse for yellowfin tuna, striped marlin, or yellowtail kingfish in 2015-2025, run a second audit extending only those species back to 2002-06-01. Then add verified remote MUR subset access for occurrence dates before building training samples.
