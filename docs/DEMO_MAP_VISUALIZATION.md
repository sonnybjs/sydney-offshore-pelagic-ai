# Demo Map Visualization

## Purpose

The frontend map now displays trained-model relative habitat suitability outputs for the Sydney offshore prediction bbox:

- south_lat = -36.5
- north_lat = -32.0
- west_lon = 150.5
- east_lon = 154.5

The map does not show exact fish locations, guaranteed fish schools, live fish GPS, or true catch probability.

## Modes

### DEMO

DEMO mode uses existing historical trained-model prediction files from `data/processed/predictions/`.

For the first deployment, the targeted frontend species are:

- Yellowfin Tuna: unavailable until a trained model exists.
- Mahi Mahi / Dolphinfish: available from `2025-12-22_mahi_mahi_sydney_heatmap.geojson`.
- Striped Marlin: unavailable until a trained model exists.

When a species is unavailable, the UI shows a clear unavailable state instead of falling back to fake predictions.

### CURRENT / TOMORROW

CURRENT mode targets tomorrow's offshore habitat suitability prediction. For this build:

- target date = 2026-05-28
- Mahi Mahi current prediction file = `2026-05-28_mahi_mahi_current_sydney_heatmap.geojson`
- SST source date = 2026-05-25
- physics/current source = unavailable
- chlorophyll source = unavailable
- bathymetry = static

If target-day MUR SST is unavailable because of data latency, the pipeline uses the latest available SST and displays both the target date and SST source date.

## Map Controls

The map uses OpenStreetMap raster tiles with a local coordinate overlay. It supports:

- zoom in
- zoom out
- reset view
- drag pan
- hotspot cell click
- heatmap layer toggle
- SST front proxy toggle
- POI marker toggle

The trained prediction cells are drawn from GeoJSON point features. Scores are converted to a 0-100 relative suitability scale and displayed as:

- Low: 0-29
- Possible: 30-54
- Good: 55-74
- Prime: 75-100

## Regenerating Predictions

Run:

```bash
cd sydney-offshore-pelagic-ai
python pipelines/run_generate_demo_and_current_predictions.py
```

This updates:

- `data/processed/predictions/prediction_manifest.json`
- current-mode prediction GeoJSON where trained models are available

## Backend Endpoints

- `GET /api/predictions/manifest`
- `GET /api/predictions/available`
- `GET /api/predictions/map?mode=demo&species_id=mahi_mahi`
- `GET /api/predictions/map?mode=current&species_id=mahi_mahi`

The backend only reads precomputed files. It does not train models or run heavy inference inside API requests.

## Limitations

The current trained model coverage is incomplete. Yellowfin Tuna and Striped Marlin are unavailable in the frontend model map until reliable training samples and selected model artifacts exist.

The current Mahi Mahi model is low confidence because it is trained from presence/background data, not true catch/no-catch effort data. Background samples are pseudo-absence / available environment samples. Model output should be interpreted as relative habitat suitability only.
