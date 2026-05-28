# Data Scripts

`download_training_sources.py` downloads lightweight official source material for future training work.

It currently downloads:

- NSW DPI FAD public page and parses FAD coordinates into CSV/GeoJSON.
- NASA Earthdata CMR metadata for MUR SST.
- GEBCO download entrypoint metadata.
- AODN portal entrypoint metadata.

It does not download large global SST or bathymetry grids by default.

```bash
cd sydney-offshore-pelagic-ai
python3 scripts/download_training_sources.py
```
