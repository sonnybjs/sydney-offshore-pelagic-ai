# Training Pipeline

## Run Order

1. `01_download_occurrence_obis.py`
2. `02_download_occurrence_gbif.py`
3. `03_clean_occurrence.py`
4. `04_build_unique_date_list.py`
5. `05_download_mur_sst_subset.py`
6. `06_download_copernicus_physics_subset.py`
7. `07_download_copernicus_chl_subset.py`
8. `08_prepare_gebco_bathymetry.py`
9. `09_build_feature_grid.py`
10. `10_match_presence_to_features.py`
11. `11_generate_background_samples.py`
12. `12_train_presence_background_models.py`
13. `13_evaluate_models.py`
14. `14_predict_sydney_heatmap.py`
15. `15_export_backend_prediction_files.py`

## Model

One model is trained per species if enough cleaned presence records exist. The first baseline compares Logistic Regression and HistGradientBoostingClassifier from scikit-learn.

## Limitations

Occurrence data is presence-only. Background samples are not true absence. Public data is biased by observation and fishing effort. The model predicts relative habitat suitability, not exact fish locations or catch probability.

