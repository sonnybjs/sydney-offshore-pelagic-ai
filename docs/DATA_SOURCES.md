# Future Data Sources

## Audit-Ready Sources

### OBIS Occurrence Data

Use OBIS occurrence data for the first marine species presence-data audit. The audit scope is target species only and the NSW / East Coast TRAIN_BBOX only. OBIS records are presence/occurrence records, not catch/no-catch effort data.

### GBIF Occurrence Data

Use GBIF occurrence search as a public supplement when OBIS is sparse. The audit and training-prep scope is the same target species, TRAIN_BBOX or approved East Coast extension only, and date windows no earlier than 2002-06-01 for MUR-matched training. GBIF data is not complete ground truth and must be deduplicated against OBIS.

### ALA Occurrence Data

ALA is planned as an Australian occurrence supplement. It should use the same species, bbox, date, and provenance rules. If unavailable or not yet integrated, the pipeline should document that status rather than fabricating records.

### NASA MUR SST v4.1

Use NASA MUR SST v4.1 as the daily sea surface temperature predictor. The target variable is `analysed_sst`; later derived features include `sst_c`, `sst_gradient`, `sst_front_strength`, `sst_3d_change`, and `sst_7d_change`. The audit only performs a one-date remote subset smoke test for PREDICT_BBOX. Do not download global MUR files or full training history during the audit.

Current map status: the CURRENT / TOMORROW prediction pipeline uses remote bbox subset access for the Sydney prediction bbox. For the 2026-05-28 target run, the latest available SST source date used by the Mahi Mahi prediction was 2026-05-25, and this latency is shown in the UI.

### GEBCO Bathymetry

Use GEBCO for static depth and shelf-break context. Later derived features include `depth_m`, `slope`, contour distances, and shelf-break distance. The audit only reads a local subset file at `data/raw/bathymetry/gebco/gebco_nsw_subset.nc`. Do not download the global GEBCO grid.

### Future Copernicus Marine Physics

Use Copernicus Marine physics later for surface currents and sea-surface-height predictors. Planned variables are `uo`, `vo`, `zos`, with optional `thetao` and `mlotst`. Use subset access only, surface layer only, and unique occurrence dates only.

Current map status: no Copernicus physics file is used by the deployed frontend prediction demo yet. The current prediction files record physics as unavailable and retain missing-data flags.

### Future Copernicus Ocean Colour / Chlorophyll

Use Copernicus Ocean Colour later for productivity and chlorophyll-edge predictors. Planned variables are `CHL` and `CHL_gradient` if available. Handle cloud gaps with nearest valid date search within +/- 3 days.

Current map status: chlorophyll is not yet used by the deployed frontend prediction demo. The current prediction files record chlorophyll as unavailable and retain missing-data flags.

### NSW DPI Game Fish Tagging And FADs

Use NSW DPI tagging and FAD information later for validation, local prior, and POI/structure features. The audit must not scrape. Placeholder points must be marked `demo_only=true` and `verified=false`.

## IMOS / AODN OceanCurrent

SST, ocean colour/chlorophyll, sea level anomaly, surface current, waves and East Australian Current context.

Current local status: AODN portal metadata has been saved for discovery only; no large AODN dataset has been downloaded.

## Copernicus Marine

Operational forecast products, currents, temperature, salinity, chlorophyll and mixed layer depth if available.

## NASA MUR SST

Daily global 1 km SST and historical SST training features.

Current local status: NASA Earthdata CMR metadata for `MUR-JPL-L4-GLOB-v4.1` has been saved. Full global MUR files have not been downloaded.

## GEBCO

Bathymetry, shelf break, canyon and seamount/ridge proxies.

Current local status: GEBCO download entrypoint metadata has been saved. Full global GEBCO has not been downloaded. The pipeline is ready for a bbox subset NetCDF in `data/raw/bathymetry/gebco/`.

## NSW DPI

Game Fish Tagging Program maps and reports, FAD information, recreational fishing rules and species notes.

Current local status: the FAD public page HTML has been downloaded and coordinate rows exposed in the table have been parsed to CSV/GeoJSON under `data/processed/nsw_dpi/`. Sydney-region FAD rows may be unavailable while listed as retrieved for winter maintenance.

## User Catch Logs

Species, date/time, approximate GPS, kept/released, lure/bait, sea condition, notes and optional photos later.

## Weather / Marine Forecast Later

Wind, swell, barometer and safety flags only.
