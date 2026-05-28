# Roadmap

## v0.1

Local app, mock ocean data, species scoring, hotspot GeoJSON, dashboard, map placeholder and tests.

## v0.2

MapLibre map, real bathymetry subset, real/curated FAD points and better POI layers.

## v0.3

Real SST from NASA MUR or IMOS, SST gradient/front computation and daily cached data.

## v0.4

Current vectors from IMOS/Copernicus, chlorophyll layer and sea level anomaly layer.

## v0.5

User catch log, local SQLite, CSV import/export and private notes.

## v0.6

Train ML baseline with XGBoost, LightGBM or logistic regression; compare rule versus ML and calibrate outputs.

Current implementation note: the v0.6 training workflow scripts exist and run safely, but real ML training is blocked until verified date-aligned MUR SST features are available. The pipeline must not use synthetic/proxy SST as real model input.

## v0.7

Forecast mode, 1-3 day offshore prediction and uncertainty display.

Current implementation note: the first frontend map deployment supports DEMO and CURRENT / TOMORROW modes from precomputed model prediction files. CURRENT mode currently works where a selected trained model exists, with Mahi Mahi available and Yellowfin Tuna / Striped Marlin shown as unavailable until model artifacts are produced.

## v0.8

Sydney Estuary Bite Window module for mulloway, kingfish and flathead with tide/rainfall integration.
