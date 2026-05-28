from __future__ import annotations

import time
from urllib.parse import urlencode

from pipeline_lib import append_provenance, cfg, ensure_dirs, save_dataframe, write_json


API = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_CELL_RESOLUTION_DEG = 0.5
HOURLY_VARIABLES = [
    "surface_pressure",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "precipitation",
]


def weather_cell(value: float) -> float:
    return round(round(float(value) / WEATHER_CELL_RESOLUTION_DEG) * WEATHER_CELL_RESOLUTION_DEG, 4)


def build_cell_date_plan():
    import sys

    sys.path.append(str(cfg.ROOT / "pipelines"))
    from training_prep_lib import load_all_best_occurrences

    occ = load_all_best_occurrences()
    if occ.empty:
        return []
    occ = occ.copy()
    occ["weather_lat"] = occ["decimalLatitude"].astype(float).apply(weather_cell)
    occ["weather_lon"] = occ["decimalLongitude"].astype(float).apply(weather_cell)
    plan = []
    for (lat, lon), group in occ.groupby(["weather_lat", "weather_lon"]):
        dates = sorted(group["date"].dropna().astype(str).unique().tolist())
        plan.append({"weather_lat": float(lat), "weather_lon": float(lon), "dates": dates, "start_date": min(dates), "end_date": max(dates)})
    return sorted(plan, key=lambda item: (item["weather_lat"], item["weather_lon"]))


def request_cell(cell: dict) -> dict:
    import requests

    params = {
        "latitude": cell["weather_lat"],
        "longitude": cell["weather_lon"],
        "start_date": cell["start_date"],
        "end_date": cell["end_date"],
        "hourly": ",".join(HOURLY_VARIABLES),
        "timezone": "UTC",
    }
    url = f"{API}?{urlencode(params)}"
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    payload = response.json()
    if "hourly" not in payload:
        raise ValueError(f"Open-Meteo response has no hourly data: {payload}")
    return {"url": url, "payload": payload}


def aggregate_payload(cell: dict, payload: dict):
    import pandas as pd

    hourly = payload["hourly"]
    df = pd.DataFrame(hourly)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df["date"] = df["time"].dt.date.astype(str)
    keep_dates = set(cell["dates"])
    df = df[df["date"].isin(keep_dates)]
    if df.empty:
        return df
    agg = df.groupby("date").agg(
        surface_pressure_hpa_mean=("surface_pressure", "mean"),
        surface_pressure_hpa_min=("surface_pressure", "min"),
        surface_pressure_hpa_max=("surface_pressure", "max"),
        pressure_msl_hpa_mean=("pressure_msl", "mean"),
        wind_speed_10m_kmh_mean=("wind_speed_10m", "mean"),
        wind_speed_10m_kmh_max=("wind_speed_10m", "max"),
        precipitation_mm_sum=("precipitation", "sum"),
    ).reset_index()
    # Circular mean for wind direction.
    import numpy as np

    wind = df.dropna(subset=["wind_direction_10m"]).copy()
    if not wind.empty:
        wind["sin_dir"] = np.sin(np.deg2rad(wind["wind_direction_10m"]))
        wind["cos_dir"] = np.cos(np.deg2rad(wind["wind_direction_10m"]))
        wind_dir = wind.groupby("date").agg(sin_mean=("sin_dir", "mean"), cos_mean=("cos_dir", "mean")).reset_index()
        wind_dir["wind_direction_10m_deg_circular_mean"] = (np.rad2deg(np.arctan2(wind_dir["sin_mean"], wind_dir["cos_mean"])) + 360) % 360
        agg = agg.merge(wind_dir[["date", "wind_direction_10m_deg_circular_mean"]], on="date", how="left")
    else:
        agg["wind_direction_10m_deg_circular_mean"] = float("nan")
    agg["weather_lat"] = cell["weather_lat"]
    agg["weather_lon"] = cell["weather_lon"]
    agg["weather_source"] = "Open-Meteo Historical Weather API"
    agg["weather_source_url"] = payload.get("_source_url", "")
    return agg


def main() -> None:
    import pandas as pd

    ensure_dirs()
    out_dir = cfg.DATA / "interim" / "feature_grid" / "weather"
    plan = build_cell_date_plan()
    estimated = {
        "title": "SUPPLEMENTARY DATA DOWNLOAD CHECK",
        "dataset": "Open-Meteo historical weather",
        "bbox": cfg.TRAIN_BBOX,
        "variables": HOURLY_VARIABLES,
        "weather_cell_resolution_deg": WEATHER_CELL_RESOLUTION_DEG,
        "cell_count": len(plan),
        "estimated_size": "<100 MB processed for first run",
        "under_10gb": True,
        "notes": "Queries are limited to East Coast occurrence-date weather cells; no global/full-Australia download.",
    }
    print(estimated)
    rows = []
    items = []
    for idx, cell in enumerate(plan, start=1):
        try:
            result = request_cell(cell)
            result["payload"]["_source_url"] = result["url"]
            frame = aggregate_payload(cell, result["payload"])
            rows.append(frame)
            item = {"status": "downloaded", "weather_lat": cell["weather_lat"], "weather_lon": cell["weather_lon"], "dates": len(cell["dates"])}
        except Exception as exc:
            item = {"status": "failed", "weather_lat": cell["weather_lat"], "weather_lon": cell["weather_lon"], "error": f"{type(exc).__name__}: {exc}"}
        items.append(item)
        print(f"[{idx}/{len(plan)}] {item}")
        time.sleep(0.2)
    df = pd.concat([frame for frame in rows if frame is not None and not frame.empty], ignore_index=True, sort=False) if rows else pd.DataFrame()
    outputs = save_dataframe(
        df,
        out_dir / "open_meteo_weather_features.csv",
        out_dir / "open_meteo_weather_features.parquet",
    )
    summary = {
        "status": "completed",
        "plan": estimated,
        "rows": int(len(df)),
        "downloaded_cells": sum(1 for item in items if item["status"] == "downloaded"),
        "failed_cells": sum(1 for item in items if item["status"] == "failed"),
        "outputs": outputs,
        "items": items,
    }
    write_json(cfg.DATA / "interim" / "env_raw_index" / "open_meteo_weather_status.json", summary)
    append_provenance(
        {
            "dataset_name": "open_meteo_historical_weather_features",
            "source_name": "Open-Meteo Historical Weather API",
            "source_url_or_access_method": API,
            "spatial_bbox": cfg.TRAIN_BBOX,
            "time_range": "occurrence dates, grouped by 0.5 degree weather cells",
            "variables": ",".join(HOURLY_VARIABLES),
            "raw_file_path": API,
            "processed_file_path": outputs.get("csv", ""),
            "estimated_size_mb": "<100",
            "actual_size_mb": outputs.get("csv_size_mb", ""),
            "license_or_terms_note": "Open-Meteo API; provide attribution and verify terms before redistribution.",
            "used_for_training": True,
            "notes": "Daily aggregates aligned to occurrence dates and approximate weather cells.",
        }
    )
    print(summary)


if __name__ == "__main__":
    main()
