# Sydney Offshore Pelagic AI Map

Local v0.1 demo for offshore pelagic habitat suitability around Sydney and nearby NSW waters.

The app predicts habitat suitability, pelagic hotspot score, bite probability and likely productive oceanographic zones. It does not know exact real-time fish locations, does not show live fish GPS and does not guarantee catches.

## Why Offshore Pelagic First

Offshore pelagics respond strongly to oceanographic structure: SST bands, fronts, current edges, shelf breaks, canyons, seamounts, FAD-like structure and seasonal water movement. That makes them a good first domain for a transparent rule-based decision-support demo.

## v0.1 Includes

- FastAPI backend
- Next.js dashboard
- mock SST, fronts, currents and offshore POIs
- rule-based scoring for seven offshore pelagic species
- GeoJSON hotspot output
- fallback frontend data if backend is offline
- tests for health, species, scoring, hotspots and mock ocean status

## v0.1 Does Not Include

- real-time fish locations
- paid APIs or API keys
- real satellite ingestion
- Docker requirement
- large geospatial datasets
- legal, navigation or marine safety advice

## Run Backend

```bash
cd sydney-offshore-pelagic-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run Tests

```bash
cd sydney-offshore-pelagic-ai/backend
source .venv/bin/activate
pytest
```

## Run Frontend

```bash
cd sydney-offshore-pelagic-ai/frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

If the dev server blocks local browser resources or controls do not respond, use the stable static mode:

```bash
cd sydney-offshore-pelagic-ai/frontend
npm run build
npm run serve:static
```

Open `http://127.0.0.1:3000` and hard refresh the browser.

## Current Limitations

All v0.1 data is synthetic and approximate. Coordinates and POIs are demo-only and not verified fishing marks. Scoring is rule-based and should be treated as transparent model exploration, not operational fishing intelligence.

## Roadmap

Future versions add MapLibre, real SST, bathymetry, currents, chlorophyll, sea level anomaly, catch logs, local ML baselines and forecast-style uncertainty.

## Initial Data Download

```bash
cd sydney-offshore-pelagic-ai
python3 scripts/download_training_sources.py
```

This downloads lightweight official source material and parses exposed NSW DPI FAD coordinate rows. It does not download multi-GB global SST or bathymetry grids by default.

## Minimum Real-Data Training Pipeline

```bash
cd sydney-offshore-pelagic-ai
python3 -m pip install -r pipelines/requirements.txt
python3 pipelines/run_minimum_pipeline.py
```

The minimum pipeline uses East Coast OBIS occurrence records, first-run feature grids, presence-background sampling, scikit-learn baseline models, and exports precomputed Sydney prediction GeoJSON files for the backend.
