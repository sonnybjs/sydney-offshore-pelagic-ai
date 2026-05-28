# Training Data Preparation

This stage prepares aligned presence/background samples for later habitat suitability modelling. It does not train models.

## Date Alignment

Dynamic ocean features must match the occurrence date. SST is required for v1 and should use the same date as the occurrence. Rolling SST features must only use previous dates: `sst_3d_change` compares date vs date-3 and `sst_7d_change` compares date vs date-7. Future dates should not be used for strict training because they can leak information.

Static features do not need date alignment. Bathymetry, slope, shelf-break distance, contour distance, FAD distance, Browns Mountain distance, and POI distance can be reused across dates.

## Presence And Background Labels

Presence rows come from public occurrence records and have `label = 1`. These records are presence-only and biased by observer effort, reporting behaviour, vessel range, and data-source coverage.

Background rows have `label = 0`, but they are not true absence. They are pseudo-absence / available ocean environment samples. Background samples are drawn from the same dates as the presence samples so the later model does not simply learn seasonal/date bias.

The output supports relative habitat suitability and hotspot scoring. It is not true catch probability and it does not identify exact fish locations.

## Missing Data

Required for v1:

- cleaned occurrence record
- daily occurrence date
- valid lat/lon
- date-aligned SST
- same-date background grid

Strongly recommended:

- GEBCO bathymetry
- shelf-break/depth features

Optional:

- currents / sea surface height
- chlorophyll
- FAD / POI structure

If SST is missing, the date is skipped for v1 training. The pipeline prints a `SUPPLEMENTARY DATA DOWNLOAD CHECK` and records the skipped date. It does not fabricate SST.

If bathymetry is missing, the pipeline can continue with `has_bathymetry = false`, but downstream training should be treated as lower confidence. If physics or chlorophyll are missing, columns remain `NaN` and missing flags are set.

## Supplementation

Occurrence data can be supplemented from OBIS, GBIF, and later ALA, using the NSW / East Coast bbox only. GEBCO should use a safe subset file or official subset endpoint only. MUR SST should use remote subset access only.

Do not download Western Australia, full Australia, global MUR, or global GEBCO. If an estimated raw/cache download exceeds 10 GB, stop and ask before proceeding.

## Commands

```bash
cd sydney-offshore-pelagic-ai
python -m pip install -r pipelines/requirements.txt
python pipelines/run_prepare_training_data.py
```

Inspect:

```bash
data/processed/reports/TRAINING_DATASET_REPORT.md
data/processed/reports/training_dataset_summary.json
data/processed/reports/DATA_PROVENANCE_LOG.csv
```

## Expected Outputs

Per species:

```bash
data/processed/training/{species_id}_training_samples.csv
data/processed/training/{species_id}_training_samples.parquet
```

Combined:

```bash
data/processed/training/all_species_training_samples.csv
data/processed/training/all_species_training_samples.parquet
```

Outputs are produced only when required date-aligned SST and matched presence/background samples exist.
