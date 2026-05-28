# Data Download Status

Last updated: 2026-05-27

## Downloaded Or Saved Locally

- `data/raw/source_metadata/nsw_dpi_fads.html`: NSW DPI Fish Aggregating Devices official page HTML.
- `data/processed/nsw_dpi/fads.csv`: parsed FAD coordinate rows exposed in the downloaded NSW DPI table.
- `data/processed/nsw_dpi/fads.geojson`: same FAD rows as GeoJSON points.
- `data/raw/source_metadata/nasa_mur_cmr.json`: NASA Earthdata CMR collection metadata for `MUR-JPL-L4-GLOB-v4.1`.
- `data/raw/source_metadata/gebco_downloads.html`: GEBCO download application entrypoint HTML.
- `data/raw/source_metadata/aodn_portal.html`: AODN portal entrypoint HTML.
- `data/raw/source_metadata/download_manifest.json`: source URLs, status, and output manifest.

## Not Downloaded Yet

- Full NASA MUR SST granules are not downloaded yet. Use Earthdata/PO.DAAC access workflows and cache only a Sydney/NSW offshore subset.
- Full GEBCO bathymetry grids are not downloaded yet. The current GEBCO grid is multi-GB globally; use user-defined subset or OPeNDAP.
- IMOS/AODN current/chlorophyll/SLA datasets are not downloaded yet. The portal metadata is saved; a specific product must be selected next.
- Copernicus Marine physics/current data is not present in the training samples yet. The columns `uo`, `vo`, `current_speed`, `current_edge_score`, `zos`, `sla_gradient`, and `eddy_score` currently contain no real values, so the existing selected models were not trained with current data.
- Copernicus Marine toolbox is installed in `.venv-pipeline`, but account environment variables are not configured yet. The latest setup check found `copernicusmarine_cli_found=true` and `copernicus_env_found=false`.

## 500m / Current Upgrade Status

- Requested recommendation radius: 500 m.
- Requested high-resolution prediction grid: `0.005` degrees, roughly 500 m in latitude around Sydney.
- Current production training/prediction grid: `0.05` degrees, roughly 5 km.
- A 500 m Sydney display grid is feasible, but it must be driven by real source-resolution environmental features. Interpolating the current 5 km grid would make the map look precise without adding real information.
- A generated audit is available at `data/processed/reports/CURRENT_500M_UPGRADE_AUDIT.md`.

To run the first current-data smoke test, configure Copernicus Marine credentials in the shell that runs the pipeline, then run:

```bash
python pipelines/06_download_copernicus_physics_subset.py
```

The script is scoped to East Coast `TRAIN_BBOX`, one occurrence-aligned date for the smoke test, surface layer only, and variables `uo`, `vo`, `zos`.

## Important Notes

- NSW DPI currently lists many Sydney-region FAD rows as retrieved for winter maintenance with no coordinates exposed in the table, so the parsed dataset contains only coordinate rows present in the downloaded page.
- These data files are for future feature engineering and model training. They are not used as live operational fishing guidance in v0.1.
