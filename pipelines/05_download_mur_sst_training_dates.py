from __future__ import annotations

import math
import os
from datetime import datetime
from urllib.parse import quote

from pipeline_lib import append_provenance, cfg, ensure_dirs, file_size_mb, save_dataframe, write_json


ERDDAP_DATASET = "jplMURSST41"
ERDDAP_BASE = f"https://coastwatch.pfeg.noaa.gov/erddap/griddap/{ERDDAP_DATASET}.csvp"


def estimate_download_plan(date_count: int) -> dict:
    bbox = cfg.TRAIN_BBOX
    lat_cells = int(round((bbox["north_lat"] - bbox["south_lat"]) / cfg.TRAIN_GRID_RESOLUTION_DEG)) + 1
    lon_cells = int(round((bbox["east_lon"] - bbox["west_lon"]) / cfg.TRAIN_GRID_RESOLUTION_DEG)) + 1
    cells_per_date = lat_cells * lon_cells
    total_cells = cells_per_date * date_count
    # CSV/parquet sizes vary; this estimate is intentionally conservative.
    estimated_mb = round(total_cells * 90 / (1024 * 1024), 2)
    return {
        "title": "DATA DOWNLOAD CONFIRMATION - MUR SST TRAINING DATES",
        "dataset": "NASA/JPL MUR SST v4.1 via NOAA CoastWatch ERDDAP mirror",
        "purpose": "Date-aligned SST features for presence/background habitat suitability training",
        "spatial_scope": cfg.TRAIN_BBOX,
        "time_scope": "unique occurrence dates only",
        "variables": ["analysed_sst"],
        "download_now": "yes",
        "resolution": "0.05 degree output using ERDDAP stride from 0.01 degree source",
        "date_count": date_count,
        "cells_per_date": cells_per_date,
        "estimated_total_cells": total_cells,
        "estimated_processed_size_mb": estimated_mb,
        "safety_rule": "No Western Australia, no full Australia, no global files, no dates outside unique occurrence-date list",
        "under_10gb": estimated_mb < cfg.RAW_DOWNLOAD_SIZE_LIMIT_GB * 1024,
    }


def erddap_url(date_text: str, bbox: dict | None = None) -> str:
    bbox = bbox or cfg.TRAIN_BBOX
    time = quote(f"{date_text}T09:00:00Z", safe="")
    return (
        f"{ERDDAP_BASE}?analysed_sst"
        f"[({time})]"
        f"[({bbox['south_lat']}):5:({bbox['north_lat']})]"
        f"[({bbox['west_lon']}):5:({bbox['east_lon']})]"
    )


def compute_gradient(df):
    import numpy as np
    import pandas as pd

    pivot = df.pivot(index="lat", columns="lon", values="sst_c").sort_index().sort_index(axis=1)
    values = pivot.values.astype(float)
    gy, gx = np.gradient(values)
    grad = np.hypot(gx, gy)
    gradient = pd.DataFrame(grad, index=pivot.index, columns=pivot.columns).stack().reset_index()
    gradient.columns = ["lat", "lon", "sst_gradient"]
    out = df.merge(gradient, on=["lat", "lon"], how="left")
    out["sst_front_strength"] = out["sst_gradient"].clip(lower=0)
    return out


def download_one_date(date_text: str, overwrite: bool = False) -> dict:
    import pandas as pd

    out_dir = cfg.DATA / "interim" / "feature_grid" / "sst"
    out_csv = out_dir / f"sst_features_{date_text}.csv"
    out_parquet = out_dir / f"sst_features_{date_text}.parquet"
    if not overwrite and (out_parquet.exists() or out_csv.exists()):
        return {
            "date": date_text,
            "status": "already_exists",
            "csv": str(out_csv.relative_to(cfg.ROOT)) if out_csv.exists() else "",
            "parquet": str(out_parquet.relative_to(cfg.ROOT)) if out_parquet.exists() else "",
            "size_mb": file_size_mb(out_parquet if out_parquet.exists() else out_csv),
        }
    url = erddap_url(date_text)
    raw = pd.read_csv(url)
    lower = {col.lower(): col for col in raw.columns}
    lat_col = next(col for key, col in lower.items() if key.startswith("latitude"))
    lon_col = next(col for key, col in lower.items() if key.startswith("longitude"))
    sst_col = next(col for key, col in lower.items() if key.startswith("analysed_sst"))
    df = raw[[lat_col, lon_col, sst_col]].copy()
    df.columns = ["lat", "lon", "sst_c"]
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce").round(4)
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce").round(4)
    df["sst_c"] = pd.to_numeric(df["sst_c"], errors="coerce")
    df = df.dropna(subset=["lat", "lon"])
    df["date"] = date_text
    df = compute_gradient(df)
    df["sst_3d_change"] = math.nan
    df["sst_7d_change"] = math.nan
    df["sst_source"] = "NASA/JPL MUR SST v4.1 via NOAA CoastWatch ERDDAP jplMURSST41"
    df["sst_source_url"] = url
    df["sst_source_date"] = date_text
    df["sst_date_offset_days"] = 0
    df = df[
        [
            "date",
            "lat",
            "lon",
            "sst_c",
            "sst_gradient",
            "sst_front_strength",
            "sst_3d_change",
            "sst_7d_change",
            "sst_source",
            "sst_source_url",
            "sst_source_date",
            "sst_date_offset_days",
        ]
    ]
    parquet_only = os.environ.get("MUR_PARQUET_ONLY", "0") == "1"
    if parquet_only:
        out_parquet.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_parquet, index=False)
        outputs = {"parquet": str(out_parquet.relative_to(cfg.ROOT)), "parquet_size_mb": file_size_mb(out_parquet)}
    else:
        outputs = save_dataframe(df, out_csv, out_parquet)
    return {
        "date": date_text,
        "status": "downloaded",
        "cell_count": int(len(df)),
        "min_sst_c": None if df.empty else float(df["sst_c"].min()),
        "max_sst_c": None if df.empty else float(df["sst_c"].max()),
        "mean_sst_c": None if df.empty else float(df["sst_c"].mean()),
        "missing_pct": round(float(df["sst_c"].isna().mean() * 100), 4) if len(df) else 100.0,
        "outputs": outputs,
    }


def main() -> None:
    import pandas as pd
    import sys

    ensure_dirs()
    date_list_path = cfg.DATA / "interim" / "date_lists" / "unique_training_dates.csv"
    if not date_list_path.exists():
        raise FileNotFoundError("Missing unique date list. Run pipelines/04_build_unique_date_list.py first.")
    date_source = os.environ.get("MUR_DATE_SOURCE", "sampled_unique_dates")
    if date_source == "all_clean_occurrence_dates":
        sys.path.append(str(cfg.ROOT / "pipelines"))
        from training_prep_lib import load_all_best_occurrences

        occurrence = load_all_best_occurrences()
        dates = sorted(occurrence["date"].dropna().astype(str).unique().tolist())
    else:
        dates = sorted(pd.read_csv(date_list_path)["date"].dropna().astype(str).unique().tolist())
    max_dates_env = os.environ.get("MUR_MAX_DATES")
    if max_dates_env:
        dates = dates[: int(max_dates_env)]
    plan = estimate_download_plan(len(dates))
    print(plan)
    if not plan["under_10gb"]:
        raise RuntimeError("Estimated MUR SST download exceeds 10 GB. Stop and ask for approval.")

    summary = {
        "dataset": plan["dataset"],
        "source": ERDDAP_BASE,
        "bbox": cfg.TRAIN_BBOX,
        "date_count": len(dates),
        "started_at": datetime.utcnow().isoformat() + "Z",
        "items": [],
    }
    downloaded = 0
    failed = 0
    skipped = 0
    for idx, date_text in enumerate(dates, start=1):
        try:
            item = download_one_date(date_text)
        except Exception as exc:
            item = {"date": date_text, "status": "failed", "error": f"{type(exc).__name__}: {exc}", "attempted_url": erddap_url(date_text)}
        if item["status"] == "downloaded":
            downloaded += 1
        elif item["status"] == "already_exists":
            skipped += 1
        else:
            failed += 1
        summary["items"].append(item)
        print(f"[{idx}/{len(dates)}] {date_text}: {item['status']}")
    summary.update({"downloaded": downloaded, "already_exists": skipped, "failed": failed, "finished_at": datetime.utcnow().isoformat() + "Z"})
    write_json(cfg.DATA / "interim" / "env_raw_index" / "mur_sst_training_download_summary.json", summary)
    append_provenance(
        {
            "dataset_name": "mur_sst_training_date_subsets",
            "source_name": "NASA/JPL MUR SST v4.1 via NOAA CoastWatch ERDDAP",
            "source_url_or_access_method": ERDDAP_BASE,
            "spatial_bbox": cfg.TRAIN_BBOX,
            "time_range": f"{min(dates)} to {max(dates)}" if dates else "",
            "variables": "analysed_sst, derived sst_gradient, sst_front_strength",
            "raw_file_path": ERDDAP_BASE,
            "processed_file_path": "data/interim/feature_grid/sst/sst_features_YYYY-MM-DD.parquet",
            "estimated_size_mb": plan["estimated_processed_size_mb"],
            "actual_size_mb": "",
            "license_or_terms_note": "Public NASA/JPL MUR SST mirrored by NOAA CoastWatch ERDDAP; verify terms before redistribution.",
            "used_for_training": True,
            "notes": "Date-aligned SST subsets only; no global/full-Australia download.",
        }
    )
    print(summary)


if __name__ == "__main__":
    main()
