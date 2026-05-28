from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import xarray as xr

from pipeline_lib import cfg, ensure_dirs, file_size_mb, save_dataframe, write_json
from training_prep_lib import load_all_best_occurrences


def target_dates() -> set[str]:
    occurrences = load_all_best_occurrences()
    if not occurrences.empty and "date" in occurrences.columns:
        return set(occurrences["date"].dropna().astype(str).unique().tolist())
    path = cfg.DATA / "interim" / "date_lists" / "unique_training_dates.csv"
    if not path.exists():
        return set()
    df = pd.read_csv(path)
    if "date" not in df.columns:
        return set()
    return set(df["date"].dropna().astype(str).unique().tolist())


def output_path(date_text: str) -> Path:
    return cfg.DATA / "interim" / "feature_grid" / "physics" / f"physics_features_{date_text}.csv"


def raw_files() -> list[Path]:
    return sorted((cfg.DATA / "raw" / "ocean" / "copernicus_physics").glob("physics_*.nc"))


def normalize_dataset(ds: xr.Dataset) -> xr.Dataset:
    if "depth" in ds["uo"].dims:
        ds["uo"] = ds["uo"].isel(depth=0)
    if "depth" in ds["vo"].dims:
        ds["vo"] = ds["vo"].isel(depth=0)
    return ds


def grid_round(values: pd.Series, resolution: float) -> pd.Series:
    return (np.round(values.astype(float) / resolution) * resolution).round(4)


def current_direction_degrees(uo: pd.Series, vo: pd.Series) -> pd.Series:
    # Direction the water is moving toward, degrees clockwise from north.
    return (np.degrees(np.arctan2(uo.astype(float), vo.astype(float))) + 360) % 360


def derive_features(frame: pd.DataFrame, date_text: str) -> pd.DataFrame:
    frame = frame.rename(columns={"latitude": "lat", "longitude": "lon"})
    frame["date"] = date_text
    frame["lat"] = grid_round(frame["lat"], cfg.TRAIN_GRID_RESOLUTION_DEG)
    frame["lon"] = grid_round(frame["lon"], cfg.TRAIN_GRID_RESOLUTION_DEG)
    frame["uo"] = pd.to_numeric(frame["uo"], errors="coerce")
    frame["vo"] = pd.to_numeric(frame["vo"], errors="coerce")
    frame["zos"] = pd.to_numeric(frame["zos"], errors="coerce")
    frame["current_speed"] = np.sqrt(frame["uo"] ** 2 + frame["vo"] ** 2)
    frame["current_direction_degrees"] = current_direction_degrees(frame["uo"], frame["vo"])

    grouped = frame.groupby(["date", "lat", "lon"], as_index=False).agg(
        {
            "uo": "mean",
            "vo": "mean",
            "zos": "mean",
            "current_speed": "mean",
            "current_direction_degrees": "mean",
        }
    )
    grouped = grouped.sort_values(["lat", "lon"]).reset_index(drop=True)
    grouped["current_edge_score"] = 0.0
    grouped["sla_gradient"] = 0.0
    grouped["eddy_score"] = 0.0

    # Approximate gradients on the regular grid. This stays lightweight and
    # avoids geospatial dependencies.
    pivot_speed = grouped.pivot(index="lat", columns="lon", values="current_speed")
    pivot_zos = grouped.pivot(index="lat", columns="lon", values="zos")
    if pivot_speed.shape[0] > 2 and pivot_speed.shape[1] > 2:
        gy, gx = np.gradient(pivot_speed.to_numpy(dtype=float))
        current_grad = np.sqrt(gx**2 + gy**2)
        grad_df = pd.DataFrame(current_grad, index=pivot_speed.index, columns=pivot_speed.columns).stack().reset_index(name="current_edge_score")
        grouped = grouped.drop(columns=["current_edge_score"]).merge(grad_df, on=["lat", "lon"], how="left")
    if pivot_zos.shape[0] > 2 and pivot_zos.shape[1] > 2:
        gy, gx = np.gradient(pivot_zos.to_numpy(dtype=float))
        sla_grad = np.sqrt(gx**2 + gy**2)
        sla_df = pd.DataFrame(sla_grad, index=pivot_zos.index, columns=pivot_zos.columns).stack().reset_index(name="sla_gradient")
        grouped = grouped.drop(columns=["sla_gradient"]).merge(sla_df, on=["lat", "lon"], how="left")
    grouped["eddy_score"] = grouped[["current_edge_score", "sla_gradient"]].fillna(0).sum(axis=1)
    grouped["physics_missing_flag"] = False
    grouped["physics_source_date"] = date_text
    grouped["physics_date_offset_days"] = 0
    grouped["has_physics"] = True
    return grouped


def process_file(path: Path, wanted_dates: set[str]) -> dict:
    ds = normalize_dataset(xr.open_dataset(path))
    outputs = []
    for time_value in ds["time"].values:
        date_text = pd.to_datetime(time_value).date().isoformat()
        if wanted_dates and date_text not in wanted_dates:
            continue
        selected = ds.sel(time=time_value)
        df = selected[["uo", "vo", "zos"]].to_dataframe().reset_index()
        features = derive_features(df, date_text)
        out = output_path(date_text)
        saved = save_dataframe(features, out, out.with_suffix(".parquet"))
        outputs.append(
            {
                "date": date_text,
                "cells": int(len(features)),
                "current_speed_min": float(features["current_speed"].min(skipna=True)),
                "current_speed_max": float(features["current_speed"].max(skipna=True)),
                "outputs": saved,
            }
        )
    return {"raw_file": str(path.relative_to(cfg.ROOT)), "raw_size_mb": file_size_mb(path), "dates": outputs}


def main() -> None:
    ensure_dirs()
    files = raw_files()
    wanted_dates = target_dates()
    summary = {"status": "completed" if files else "no_raw_physics_files", "raw_files": len(files), "items": []}
    for path in files:
        try:
            summary["items"].append(process_file(path, wanted_dates))
        except Exception as exc:
            summary["items"].append({"raw_file": str(path), "status": "failed", "error": f"{type(exc).__name__}: {exc}"})
    write_json(cfg.DATA / "interim" / "feature_grid" / "physics" / "physics_feature_processing_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
