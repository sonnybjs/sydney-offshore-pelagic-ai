# Data Download Plan

The pipeline downloads only NSW/East Coast subsets or metadata needed to discover subset downloads.

## First Run Limits

- raw/cache target: `<=10 GB`
- processed feature tables: `<=5 GB`
- model artifacts: `<=500 MB`
- prediction outputs: `<=1 GB`

The first runnable pipeline avoids full global MUR SST, full global GEBCO, full-depth Copernicus products, full Australia, Western Australia, and South Australia.

## Sources

- OBIS occurrence data: downloaded by species and East Coast bbox.
- GBIF/ALA: optional/manual import for now.
- NASA MUR SST: metadata saved; processed SST-compatible features are scaffolded for the first run until remote subset access is wired.
- Copernicus physics/chlorophyll: status files are written if credentials/setup are missing.
- GEBCO: supports manual bbox NetCDF placement later; first run uses a depth proxy so the model pipeline can execute.
- NSW DPI FAD: official page HTML and parsed exposed coordinate rows are saved.

## Run

```bash
cd sydney-offshore-pelagic-ai
python3 -m pip install -r pipelines/requirements.txt
python3 pipelines/run_minimum_pipeline.py
```

