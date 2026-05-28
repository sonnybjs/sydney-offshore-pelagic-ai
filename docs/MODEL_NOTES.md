# Model Notes

v0.1 uses a transparent rule-based model. It scores SST suitability, SST gradients, fronts, current edges, depth class, shelf break, canyons, FAD-like points, structure, seasonality, chlorophyll-edge placeholder, sea-level-anomaly placeholder and data confidence.

SST matters because species occupy preferred thermal ranges. Fronts and gradients matter because bait and predators may concentrate near water-mass boundaries. Currents matter because they create edges, convergence and flow over structure. Shelf breaks, canyons, seamounts and FAD-like structure matter because they can concentrate bait and create predictable habitat.

This is not exact fish location prediction. It is a habitat suitability and fishing decision-support demo using synthetic data.

Future ML versions can compare logistic regression, XGBoost and LightGBM against the rule model. Training data will need careful treatment because catch reports are biased by where people fish, absence is not true absence, weather and boat range influence reports, and satellite data can be cloud affected.

## First Real Baseline

The first training pipeline uses presence-background modelling. It trains one model per species when enough OBIS presence records exist, using 0.05 degree feature grids. The initial minimum feature set is SST/front-compatible features, bathymetry/depth proxies, shelf-break distance proxies, FAD/Browns distances, and seasonality. Copernicus current/chlorophyll columns are retained as nullable fields until subset access is configured.
## Training data alignment, data supplementation, and pseudo-absence design

Training rows must represent a species, date, grid cell, environmental feature set, and label. Dynamic environmental features are matched to the occurrence date. SST is required for v1; rolling SST change must use previous dates only. Bathymetry and structure features are static.

Presence records from OBIS, GBIF, and later ALA are presence-only public records. They are not complete ground truth and do not include comparable no-catch effort. Background samples are pseudo-absence / available environment samples drawn from the same dates as presence samples. They support relative habitat suitability modelling, not true catch probability.

If occurrence data is sparse, the audit may supplement from public/open sources within the NSW / East Coast scope only. If SST is missing for a date, the preparation pipeline attempts documented safe supplementation and otherwise skips that date. Optional current, sea-surface-height, and chlorophyll features may be `NaN` with missing flags.

No model output should be described as exact fish location, guaranteed fish school, live fish GPS, or certain catch prediction.

## First ML Training Workflow

The real-model training workflow now implements candidate training, evaluation, tuning/selection, prediction export, and reporting in `pipelines/14_train_models.py` through `pipelines/18_export_model_artifacts.py`.

Required baseline models are Logistic Regression, Random Forest, and HistGradientBoostingClassifier. Optional LightGBM, XGBoost, and MaxEnt-style tooling are attempted only when available and are not hard dependencies. Candidate selection prioritises validation PR-AUC, then top-10% hit rate, then ROC-AUC, because the product needs to rank relative habitat suitability rather than classify exact fish presence.

After the SST acquisition and training-sample rebuild, the first selected real-model artifacts exist for several species. The frontend prediction demo currently exposes the three requested species only: Yellowfin Tuna, Mahi Mahi / Dolphinfish, and Striped Marlin. Of those, only Mahi Mahi has a selected trained model available for map display at this stage. Yellowfin Tuna and Striped Marlin remain unavailable in the trained-model map until enough date-aligned training samples and selected model artifacts exist.

## Prediction Map Deployment

The prediction map reads precomputed GeoJSON files from `data/processed/predictions/` through backend file-serving endpoints. API requests do not run model training or heavy inference.

DEMO mode uses historical trained-model prediction files. CURRENT / TOMORROW mode targets the next day and uses the latest available SST if target-day SST is not yet available. For the 2026-05-28 current prediction, the Mahi Mahi model uses SST sourced from 2026-05-25, static bathymetry, and missing flags for unavailable current/chlorophyll data.

All map labels should describe the output as relative habitat suitability / hotspot score. They must not describe it as exact fish location, guaranteed catch, live fish GPS, or true catch probability.

## 500m Grid And Current Data Upgrade

The requested 500 m map should be treated as a high-resolution candidate-hotspot grid, not a guarantee of fish position. The current trained models were built from 0.05 degree feature grids, which are roughly 5 km around Sydney. A 0.005 degree display grid is feasible for the Sydney prediction bbox, but it should not be populated by simply interpolating 5 km model inputs and then described as more precise.

Ocean-current features are planned model predictors, but the current training datasets have no real `uo`, `vo`, `current_speed`, `current_edge_score`, `zos`, `sla_gradient`, or `eddy_score` values. Retraining with current data should only happen after a real surface-only East Coast subset is downloaded and aligned to occurrence dates.

For the next corrected model cycle:

- download or ingest Copernicus Marine surface physics for occurrence-aligned dates only;
- rebuild daily feature grids with non-null current and sea-surface-height features;
- rebuild presence/background training samples;
- retrain and audit models without coordinate leakage;
- generate a 500 m Sydney prediction grid from real environmental features or clearly label any resampling.
