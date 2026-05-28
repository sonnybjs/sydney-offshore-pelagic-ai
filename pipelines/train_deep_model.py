from __future__ import annotations

"""
Independent PyTorch deep-learning SDM trainer.

This script intentionally does not overwrite the existing scikit-learn model
artifacts in data/processed/models/. It writes to data/processed/deep_models/.

References used for the design:
- Rew, Cho & Hwang (2021), bagging ensembles with DNNs for SDMs:
  https://doi.org/10.3390/rs13081495
- Botella et al. (2021), CNN SDMs using environmental neighbourhoods:
  https://doi.org/10.1111/2041-210X.13634
- Ryckewaert et al. (2024/2026), DeepMaxent for presence-only SDMs:
  https://arxiv.org/abs/2412.19217
- MALPOLON deep-SDM framework, PyTorch modularity:
  https://arxiv.org/abs/2409.18102

For this project v1, the available data are date-aligned tabular ocean features
at grid cells, not raster image patches. A regularised MLP is therefore the
right first deep baseline; CNN support should come later after building local
environmental patch tensors around each grid cell.
"""

import argparse
import json
import math
import random
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from modeling_lib import (
    FLAG_FEATURES,
    OPTIONAL_FEATURES,
    TARGET_SPECIES,
    clean_feature_columns,
    evaluate_scores,
    load_training_samples,
    split_dataset,
)
from pipeline_lib import ROOT, cfg, write_json


MIN_PRESENCE_LOW_CONFIDENCE = 100
DEFAULT_FEATURE_CANDIDATES = [
    "sst_c",
    "sst_gradient",
    "sst_front_strength",
    "sst_3d_change",
    "sst_7d_change",
    "depth_m",
    "slope",
    "distance_to_200m_contour",
    "distance_to_500m_contour",
    "distance_to_1000m_contour",
    "distance_to_shelf_break",
    "month_sin",
    "month_cos",
    "day_of_year_sin",
    "day_of_year_cos",
] + OPTIONAL_FEATURES + FLAG_FEATURES


@dataclass
class DeepTrainConfig:
    hidden_layers: tuple[int, ...] = (128, 64, 32)
    dropout: float = 0.20
    learning_rate: float = 1e-3
    weight_decay: float = 1e-4
    batch_size: int = 256
    max_epochs: int = 160
    patience: int = 20
    background_ratio_cap: int = 10
    random_seed: int = 42


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def import_torch():
    try:
        import torch
        from torch import nn
        from torch.utils.data import DataLoader, TensorDataset
    except Exception as exc:
        raise RuntimeError(
            "PyTorch is not installed. Install optional dependencies with: "
            "python -m pip install -r pipelines/requirements-deep-learning.txt"
        ) from exc
    return torch, nn, DataLoader, TensorDataset


class MLPBinaryClassifier:
    def __init__(self, input_dim: int, hidden_layers: tuple[int, ...], dropout: float):
        torch, nn, _, _ = import_torch()
        layers: list[Any] = []
        previous = input_dim
        for width in hidden_layers:
            layers.extend(
                [
                    nn.Linear(previous, width),
                    nn.BatchNorm1d(width),
                    nn.SiLU(),
                    nn.Dropout(dropout),
                ]
            )
            previous = width
        layers.append(nn.Linear(previous, 1))
        self.model = nn.Sequential(*layers)


class ProgressLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a", encoding="utf-8")

    def write(self, message: str) -> None:
        line = f"{datetime.now().isoformat(timespec='seconds')} | {message}"
        print(line, flush=True)
        self.handle.write(line + "\n")
        self.handle.flush()

    def close(self) -> None:
        self.handle.close()


def make_output_dirs(species_id: str) -> dict[str, Path]:
    root = cfg.DATA / "processed" / "deep_models" / species_id
    figures = cfg.DATA / "processed" / "figures" / species_id / "deep_learning"
    reports = cfg.DATA / "processed" / "reports"
    root.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    return {"root": root, "figures": figures, "reports": reports}


def selected_sklearn_summary(species_id: str) -> dict[str, Any]:
    path = cfg.DATA / "processed" / "metrics" / f"{species_id}_metrics.json"
    if not path.exists():
        return {"available": False, "reason": "metrics file missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"available": False, "reason": "metrics file unreadable"}
    return {
        "available": True,
        "selected_model": payload.get("selected_model"),
        "validation_metrics": payload.get("validation_metrics") or payload.get("validation"),
        "test_metrics": payload.get("test_metrics") or payload.get("test"),
        "confidence": payload.get("confidence_rating") or payload.get("confidence_level"),
    }


def balanced_background_cap(df: pd.DataFrame, ratio: int, seed: int) -> pd.DataFrame:
    positives = df[df["label"].astype(int) == 1]
    background = df[df["label"].astype(int) == 0]
    if positives.empty or background.empty:
        return df
    keep_background = min(len(background), len(positives) * ratio)
    sampled = background.sample(n=keep_background, random_state=seed) if keep_background < len(background) else background
    return pd.concat([positives, sampled], ignore_index=True, sort=False).sample(frac=1, random_state=seed)


def select_features(df: pd.DataFrame) -> list[str]:
    features = clean_feature_columns(df, DEFAULT_FEATURE_CANDIDATES, keep_flags=True)
    return [col for col in features if col not in {"grid_lat", "grid_lon", "lat", "lon"}]


def fit_preprocessor(train: pd.DataFrame, feature_cols: list[str]) -> dict[str, Any]:
    numeric = train[feature_cols].apply(pd.to_numeric, errors="coerce")
    medians = numeric.median(axis=0, skipna=True).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    filled = numeric.fillna(medians)
    means = filled.mean(axis=0)
    stds = filled.std(axis=0).replace(0, 1.0).fillna(1.0)
    return {
        "feature_columns": feature_cols,
        "medians": medians.to_dict(),
        "means": means.to_dict(),
        "stds": stds.to_dict(),
    }


def transform(df: pd.DataFrame, prep: dict[str, Any]) -> np.ndarray:
    cols = prep["feature_columns"]
    numeric = df[cols].apply(pd.to_numeric, errors="coerce")
    medians = pd.Series(prep["medians"])
    means = pd.Series(prep["means"])
    stds = pd.Series(prep["stds"])
    return ((numeric.fillna(medians) - means) / stds).replace([np.inf, -np.inf], 0).fillna(0).to_numpy(dtype=np.float32)


def predict_scores(torch, model, x: np.ndarray, device: str, batch_size: int) -> np.ndarray:
    model.eval()
    scores: list[np.ndarray] = []
    with torch.no_grad():
        for start in range(0, len(x), batch_size):
            batch = torch.tensor(x[start : start + batch_size], dtype=torch.float32, device=device)
            logits = model(batch).squeeze(1)
            scores.append(torch.sigmoid(logits).detach().cpu().numpy())
    return np.concatenate(scores) if scores else np.array([], dtype=float)


def make_plots(species_id: str, y_true: np.ndarray, scores: np.ndarray, out_dir: Path) -> None:
    try:
        import matplotlib.pyplot as plt
        from sklearn.metrics import PrecisionRecallDisplay, RocCurveDisplay
    except Exception:
        return
    if len(np.unique(y_true)) < 2:
        return
    RocCurveDisplay.from_predictions(y_true, scores)
    plt.title(f"{species_id} deep MLP ROC")
    plt.tight_layout()
    plt.savefig(out_dir / "roc_curve.png", dpi=140)
    plt.close()
    PrecisionRecallDisplay.from_predictions(y_true, scores)
    plt.title(f"{species_id} deep MLP precision-recall")
    plt.tight_layout()
    plt.savefig(out_dir / "precision_recall_curve.png", dpi=140)
    plt.close()
    plt.hist(scores[y_true == 0], bins=30, alpha=0.65, label="background")
    plt.hist(scores[y_true == 1], bins=30, alpha=0.65, label="presence")
    plt.legend()
    plt.title(f"{species_id} deep MLP score distribution")
    plt.tight_layout()
    plt.savefig(out_dir / "score_distribution.png", dpi=140)
    plt.close()


def markdown_report(species_id: str, payload: dict[str, Any]) -> str:
    validation = payload.get("validation_metrics") or {}
    test = payload.get("test_metrics") or {}
    sklearn_summary = payload.get("sklearn_comparison") or {}
    return f"""# Deep Learning SDM Report: {species_id}

This is an independent PyTorch MLP experiment. It does not replace the existing
Logistic Regression, Random Forest, or HistGradientBoostingClassifier artifacts.

## Model

- Architecture: regularised multilayer perceptron
- Hidden layers: {payload["config"]["hidden_layers"]}
- Dropout: {payload["config"]["dropout"]}
- Device: {payload["device"]}
- Feature set: tabular date-aligned oceanographic and static habitat features

The output is relative habitat suitability from presence/background labels. It is
not exact fish location, guaranteed fish presence, or true catch probability.

## Metrics

| Split | ROC-AUC | PR-AUC | F1 @ 0.5 | Top 10% hit rate |
|---|---:|---:|---:|---:|
| Validation | {validation.get("roc_auc")} | {validation.get("pr_auc")} | {validation.get("f1_threshold_0_5")} | {validation.get("top_10_hit_rate")} |
| Test | {test.get("roc_auc")} | {test.get("pr_auc")} | {test.get("f1_threshold_0_5")} | {test.get("top_10_hit_rate")} |

## Scikit-Learn Comparison

```json
{json.dumps(sklearn_summary, indent=2)}
```

## Notes

- Missing numeric values are imputed using train-split medians.
- Numeric features are standardised using train-split means and standard deviations.
- Class imbalance is handled with `BCEWithLogitsLoss(pos_weight=...)` and a capped background ratio.
- Future CNN models should use spatial environmental patches around each cell rather than this tabular feature table.

## References

- Rew et al. 2021, bagging ensembles with deep neural networks for SDM: https://doi.org/10.3390/rs13081495
- Botella et al. 2021, CNNs for environmental neighbourhood structure in SDM: https://doi.org/10.1111/2041-210X.13634
- Ryckewaert et al. DeepMaxent: https://arxiv.org/abs/2412.19217
- MALPOLON PyTorch deep-SDM framework: https://arxiv.org/abs/2409.18102
"""


def add_extra_metrics(metrics: dict[str, Any], y_true: np.ndarray, scores: np.ndarray) -> dict[str, Any]:
    from sklearn.metrics import f1_score, confusion_matrix

    out = dict(metrics)
    if len(y_true) and len(np.unique(y_true)) >= 2:
        labels = (scores >= 0.5).astype(int)
        out["f1_threshold_0_5"] = float(f1_score(y_true, labels))
        out["confusion_matrix_threshold_0_5"] = confusion_matrix(y_true, labels).tolist()
    else:
        out["f1_threshold_0_5"] = None
    return out


def train_species(species_id: str, config: DeepTrainConfig, force_cpu: bool = False) -> dict[str, Any]:
    torch, nn, DataLoader, TensorDataset = import_torch()
    random.seed(config.random_seed)
    np.random.seed(config.random_seed)
    torch.manual_seed(config.random_seed)

    out = make_output_dirs(species_id)
    logger = ProgressLogger(out["root"] / "training.log")
    logger.write(f"START species={species_id}")
    logger.write(f"Config={asdict(config)}")
    data = load_training_samples(species_id)
    if data.empty or "label" not in data.columns:
        result = {
            "species_id": species_id,
            "status": "not_trained",
            "reason": "training samples missing or label column unavailable",
            "timestamp": now_utc(),
        }
        write_json(out["root"] / "deep_model_metrics.json", result)
        logger.write(f"SKIP species={species_id} reason={result['reason']}")
        logger.close()
        return result

    data = data.copy()
    data["label"] = data["label"].astype(int)
    presence_count = int((data["label"] == 1).sum())
    background_count = int((data["label"] == 0).sum())
    if presence_count < MIN_PRESENCE_LOW_CONFIDENCE:
        result = {
            "species_id": species_id,
            "status": "not_trained",
            "reason": "fewer than 100 presence records; deep model would be unreliable",
            "presence_count": presence_count,
            "background_count": background_count,
            "timestamp": now_utc(),
        }
        write_json(out["root"] / "deep_model_metrics.json", result)
        logger.write(
            f"SKIP species={species_id} reason={result['reason']} "
            f"presence={presence_count} background={background_count}"
        )
        logger.close()
        return result

    feature_cols = select_features(data)
    if len(feature_cols) < 3:
        result = {
            "species_id": species_id,
            "status": "not_trained",
            "reason": "fewer than three usable numeric environmental features",
            "feature_count": len(feature_cols),
            "timestamp": now_utc(),
        }
        write_json(out["root"] / "deep_model_metrics.json", result)
        logger.write(f"SKIP species={species_id} reason={result['reason']} feature_count={len(feature_cols)}")
        logger.close()
        return result

    capped = balanced_background_cap(data, config.background_ratio_cap, config.random_seed)
    splits, split_strategy = split_dataset(capped)
    if splits.get("train", pd.DataFrame()).empty or splits.get("validation", pd.DataFrame()).empty:
        result = {
            "species_id": species_id,
            "status": "not_trained",
            "reason": "unable to create usable train/validation split",
            "split_strategy": split_strategy,
            "timestamp": now_utc(),
        }
        write_json(out["root"] / "deep_model_metrics.json", result)
        logger.write(f"SKIP species={species_id} reason={result['reason']} split_strategy={split_strategy}")
        logger.close()
        return result

    train = splits["train"].copy()
    validation = splits["validation"].copy()
    test = splits.get("test", pd.DataFrame()).copy()
    prep = fit_preprocessor(train, feature_cols)
    x_train = transform(train, prep)
    x_val = transform(validation, prep)
    x_test = transform(test, prep) if not test.empty else np.empty((0, len(feature_cols)), dtype=np.float32)
    y_train = train["label"].to_numpy(dtype=np.float32)
    y_val = validation["label"].to_numpy(dtype=np.int64)
    y_test = test["label"].to_numpy(dtype=np.int64) if not test.empty else np.array([], dtype=np.int64)
    logger.write(
        "DATA "
        f"samples={len(data)} capped_samples={len(capped)} presence={presence_count} background={background_count} "
        f"features={len(feature_cols)} split_strategy={split_strategy} "
        f"train={len(train)} validation={len(validation)} test={len(test)}"
    )

    device = "cuda" if torch.cuda.is_available() and not force_cpu else "cpu"
    cuda_name = torch.cuda.get_device_name(0) if device == "cuda" else "none"
    logger.write(f"DEVICE device={device} cuda_name={cuda_name} torch={torch.__version__}")
    wrapper = MLPBinaryClassifier(input_dim=x_train.shape[1], hidden_layers=config.hidden_layers, dropout=config.dropout)
    model = wrapper.model.to(device)
    positives = max(float(y_train.sum()), 1.0)
    negatives = max(float((y_train == 0).sum()), 1.0)
    pos_weight = torch.tensor([negatives / positives], dtype=torch.float32, device=device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    dataset = TensorDataset(torch.tensor(x_train, dtype=torch.float32), torch.tensor(y_train, dtype=torch.float32))
    loader = DataLoader(dataset, batch_size=config.batch_size, shuffle=True)

    best_state = None
    best_val_auc = -math.inf
    best_epoch = 0
    wait = 0
    history = []
    logger.write("TRAINING_LOOP begin")
    for epoch in range(1, config.max_epochs + 1):
        model.train()
        losses = []
        for xb, yb in loader:
            xb = xb.to(device)
            yb = yb.to(device)
            optimizer.zero_grad()
            logits = model(xb).squeeze(1)
            loss = criterion(logits, yb)
            loss.backward()
            optimizer.step()
            losses.append(float(loss.detach().cpu()))
        val_scores = predict_scores(torch, model, x_val, device, config.batch_size)
        val_metrics = evaluate_scores(y_val, val_scores)
        val_auc = val_metrics.get("roc_auc") or -math.inf
        history.append({"epoch": epoch, "train_loss": float(np.mean(losses)), "validation_roc_auc": val_metrics.get("roc_auc"), "validation_pr_auc": val_metrics.get("pr_auc")})
        if val_auc > best_val_auc:
            best_val_auc = val_auc
            best_epoch = epoch
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            wait = 0
        else:
            wait += 1
        if epoch == 1 or epoch % 5 == 0 or wait == 0 or wait >= config.patience:
            logger.write(
                "EPOCH "
                f"{epoch}/{config.max_epochs} "
                f"loss={float(np.mean(losses)):.5f} "
                f"val_roc_auc={val_metrics.get('roc_auc')} "
                f"val_pr_auc={val_metrics.get('pr_auc')} "
                f"top10={val_metrics.get('top_10_hit_rate')} "
                f"best_epoch={best_epoch} wait={wait}/{config.patience}"
            )
        if wait >= config.patience:
            logger.write(f"EARLY_STOP epoch={epoch} best_epoch={best_epoch} best_val_auc={best_val_auc}")
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    train_scores = predict_scores(torch, model, x_train, device, config.batch_size)
    val_scores = predict_scores(torch, model, x_val, device, config.batch_size)
    test_scores = predict_scores(torch, model, x_test, device, config.batch_size) if len(x_test) else np.array([])
    train_metrics = add_extra_metrics(evaluate_scores(y_train.astype(int), train_scores), y_train.astype(int), train_scores)
    val_metrics = add_extra_metrics(evaluate_scores(y_val, val_scores), y_val, val_scores)
    test_metrics = add_extra_metrics(evaluate_scores(y_test, test_scores), y_test, test_scores) if len(y_test) else {}
    make_plots(species_id, y_val, val_scores, out["figures"])

    artifact = {
        "model_state_dict": model.state_dict(),
        "preprocessor": prep,
        "feature_columns": feature_cols,
        "config": asdict(config),
        "species_id": species_id,
    }
    model_path = out["root"] / "best_deep_mlp.pt"
    torch.save(artifact, model_path)
    write_json(out["root"] / "preprocessor.json", prep)
    write_json(out["root"] / "feature_list.json", {"feature_columns": feature_cols})
    pd.DataFrame(history).to_csv(out["root"] / "training_history.csv", index=False)

    payload = {
        "species_id": species_id,
        "status": "trained",
        "timestamp": now_utc(),
        "model_type": "pytorch_mlp_binary_classifier",
        "model_path": str(model_path.relative_to(ROOT)),
        "device": device,
        "torch_version": torch.__version__,
        "config": asdict(config),
        "feature_columns": feature_cols,
        "feature_count": len(feature_cols),
        "split_strategy": split_strategy,
        "best_epoch": best_epoch,
        "presence_count": presence_count,
        "background_count": background_count,
        "train_sample_count": int(len(train)),
        "validation_sample_count": int(len(validation)),
        "test_sample_count": int(len(test)),
        "train_metrics": train_metrics,
        "validation_metrics": val_metrics,
        "test_metrics": test_metrics,
        "sklearn_comparison": selected_sklearn_summary(species_id),
        "limitations": [
            "Presence/background labels are not true absences or catch/no-catch effort data.",
            "Model estimates relative habitat suitability only.",
            "MLP uses tabular features; it does not yet learn spatial raster neighbourhoods like a CNN.",
        ],
    }
    write_json(out["root"] / "deep_model_metrics.json", payload)
    (out["root"] / "deep_model_report.md").write_text(markdown_report(species_id, payload), encoding="utf-8")
    logger.write(
        "DONE "
        f"species={species_id} best_epoch={best_epoch} "
        f"val_roc_auc={val_metrics.get('roc_auc')} val_pr_auc={val_metrics.get('pr_auc')} "
        f"test_roc_auc={test_metrics.get('roc_auc')} test_pr_auc={test_metrics.get('pr_auc')} "
        f"model_path={model_path}"
    )
    logger.close()
    return payload


def run(species: list[str], args) -> dict[str, Any]:
    config = DeepTrainConfig(
        hidden_layers=tuple(int(v) for v in args.hidden_layers.split(",") if v.strip()),
        dropout=args.dropout,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        batch_size=args.batch_size,
        max_epochs=args.max_epochs,
        patience=args.patience,
        background_ratio_cap=args.background_ratio_cap,
        random_seed=args.seed,
    )
    summary = {"timestamp": now_utc(), "species": {}, "notes": "Deep models are independent experimental artifacts; existing scikit-learn models are unchanged."}
    print(f"{datetime.now().isoformat(timespec='seconds')} | DEEP_TRAIN_START species={species}", flush=True)
    for species_id in species:
        summary["species"][species_id] = train_species(species_id, config, force_cpu=args.cpu)
    out_path = cfg.DATA / "processed" / "reports" / "deep_model_training_summary.json"
    write_json(out_path, summary)
    md = ["# Deep Model Training Summary", "", "Deep models are experimental sidecar artifacts and do not replace the current scikit-learn production/demo models.", ""]
    for species_id, result in summary["species"].items():
        md.append(f"## {species_id}")
        md.append("")
        md.append(f"- Status: {result.get('status')}")
        md.append(f"- Reason: {result.get('reason', 'n/a')}")
        md.append(f"- Model: {result.get('model_type', 'n/a')}")
        md.append(f"- Device: {result.get('device', 'n/a')}")
        md.append(f"- Validation ROC-AUC: {(result.get('validation_metrics') or {}).get('roc_auc')}")
        md.append(f"- Validation PR-AUC: {(result.get('validation_metrics') or {}).get('pr_auc')}")
        md.append("")
    (cfg.DATA / "processed" / "reports" / "DEEP_MODEL_TRAINING_SUMMARY.md").write_text("\n".join(md), encoding="utf-8")
    print(
        f"{datetime.now().isoformat(timespec='seconds')} | DEEP_TRAIN_DONE "
        f"summary={cfg.DATA / 'processed' / 'reports' / 'DEEP_MODEL_TRAINING_SUMMARY.md'}",
        flush=True,
    )
    return summary


def parse_args():
    parser = argparse.ArgumentParser(description="Train independent PyTorch MLP SDM models.")
    parser.add_argument("--species", nargs="*", default=TARGET_SPECIES, help="Species IDs to train. Defaults to all configured species.")
    parser.add_argument("--hidden-layers", default="128,64,32", help="Comma-separated MLP hidden layer sizes.")
    parser.add_argument("--dropout", type=float, default=0.20)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--max-epochs", type=int, default=160)
    parser.add_argument("--patience", type=int, default=20)
    parser.add_argument("--background-ratio-cap", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cpu", action="store_true", help="Force CPU even when CUDA is available.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    result = run(args.species, args)
    print(json.dumps(result, indent=2))
