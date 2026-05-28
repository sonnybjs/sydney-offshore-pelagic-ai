# Deep Learning Species Distribution Modelling Plan

This project uses public occurrence records and background samples. The deep
learning outputs are relative habitat suitability / hotspot scores, not exact
fish locations, guaranteed schools, or true catch probability.

## Short Literature And Open-Source Review

1. Rew, Cho and Hwang, 2021, "A Robust Prediction Model for Species Distribution Using Bagging Ensembles with Deep Neural Networks"
   - Link: https://doi.org/10.3390/rs13081495
   - Idea: train multiple DNNs on bootstrap-balanced presence/absence or pseudo-absence samples, then ensemble the predictions.
   - Useful here because our labels are imbalanced presence/background samples and spatial sampling bias is a known risk.

2. Botella et al., 2021, "Convolutional neural networks improve species distribution modelling by capturing the spatial structure of the environment"
   - Link: https://doi.org/10.1111/2041-210X.13634
   - Idea: use environmental raster neighbourhood patches around observations, not only point-level covariates.
   - Useful later when we build SST/current/chlorophyll/depth image patches around each 500 m prediction cell.

3. Ryckewaert et al., DeepMaxent, 2024/2026
   - Link: https://arxiv.org/abs/2412.19217
   - Idea: combine neural networks with a MaxEnt-like maximum entropy / Poisson point-process formulation for presence-only data.
   - Useful as a future direction because it targets presence-only data and uneven sampling more directly than binary classification.

4. MALPOLON, 2024
   - Link: https://arxiv.org/abs/2409.18102
   - Idea: a PyTorch framework for deep species distribution models with modular datasets, models, and training recipes.
   - Useful as an implementation reference for keeping deep-SDM code modular and experiment-friendly.

5. TorchGeo
   - Link: https://torchgeo.org/
   - Idea: PyTorch ecosystem library for geospatial deep learning with CRS-aware datasets and spatial samplers.
   - Useful later for CNN/raster-chip models. It is intentionally not a dependency in v1 because it would add heavier geospatial packages.

## Recommended First Model

Use a regularised multilayer perceptron (MLP) on the existing tabular training
samples.

Reasons:

- The current training data is already aligned as `species + date + grid cell + features + label`.
- The features are mostly tabular oceanographic/static variables: SST, SST front, depth, shelf distance, current features, moon/weather flags.
- A CNN needs local raster patches around each sample, which the current pipeline does not yet export.
- An MLP can run on GPU when available through PyTorch, but remains simple enough to compare against Logistic Regression and HistGradientBoostingClassifier.
- The output can be kept as an independent sidecar artifact so the app can switch back to the scikit-learn model at any time.

## Implemented Script

File:

```bash
pipelines/train_deep_model.py
```

Outputs:

```bash
data/processed/deep_models/{species_id}/best_deep_mlp.pt
data/processed/deep_models/{species_id}/preprocessor.json
data/processed/deep_models/{species_id}/feature_list.json
data/processed/deep_models/{species_id}/deep_model_metrics.json
data/processed/deep_models/{species_id}/deep_model_report.md
data/processed/reports/deep_model_training_summary.json
data/processed/reports/DEEP_MODEL_TRAINING_SUMMARY.md
```

The existing scikit-learn outputs under `data/processed/models/` are not
modified.

## Training Design

- Reads `{species_id}_training_samples.parquet` when available, otherwise CSV.
- Skips species with fewer than 100 presence records.
- Removes coordinate columns from the main deep model to reduce spatial sampling bias.
- Keeps numeric environmental features with usable non-empty values.
- Imputes missing values with train-split medians.
- Standardises numeric features using train-split means and standard deviations.
- Uses `BCEWithLogitsLoss(pos_weight=...)` for class imbalance.
- Caps background ratio to reduce overwhelming pseudo-absence dominance.
- Uses validation early stopping.
- Reports ROC-AUC, PR-AUC, F1 at 0.5, Brier/log loss, confusion matrix, and top-k hit rates.

## GPU

The script uses CUDA automatically if PyTorch detects it:

```bash
python pipelines/train_deep_model.py --species mahi_mahi southern_bluefin_tuna yellowtail_kingfish
```

Training progress is printed to the terminal and also written per species:

```bash
data/processed/deep_models/{species_id}/training.log
```

Follow progress in another terminal:

```bash
Get-Content data/processed/deep_models/mahi_mahi/training.log -Wait
```

Typical log lines include epoch number, train loss, validation ROC-AUC,
validation PR-AUC, top 10% hit rate, best epoch, and early-stopping wait.

Force CPU:

```bash
python pipelines/train_deep_model.py --cpu --species mahi_mahi
```

Install optional dependencies:

```bash
python -m pip install -r pipelines/requirements-deep-learning.txt
```

## Future CNN Extension

To add a CNN model correctly, the pipeline should first export local
environmental patches for each sample, for example:

- SST patch around the grid cell
- SST gradient/front patch
- current speed/direction patch
- depth/slope/shelf-distance patch
- chlorophyll patch when available

Then a small CNN or CNN+MLP hybrid can consume both spatial patches and tabular
metadata. This should be a separate script and should still not overwrite the
scikit-learn production artifacts.
