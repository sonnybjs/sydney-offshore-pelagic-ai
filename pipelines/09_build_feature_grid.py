from datetime import datetime
import random

from pipeline_lib import cfg, ensure_dirs, grid_points, haversine_km, synthetic_sst, depth_proxy, try_write_parquet, write_json


BROWNS = (-34.05, 151.8)


def load_fads():
    import pandas as pd

    path = cfg.DATA / "processed" / "nsw_dpi" / "fads.csv"
    if not path.exists():
        return []
    fads = pd.read_csv(path)
    if fads.empty:
        return []
    return [(float(row.latitude), float(row.longitude)) for row in fads.itertuples()]


def nearest_fad_distance(lat: float, lon: float, fads: list[tuple[float, float]]) -> float | None:
    if not fads:
        return None
    return float(min(haversine_km(lat, lon, fad_lat, fad_lon) for fad_lat, fad_lon in fads))


def build_features(date_text: str, bbox: dict) -> object:
    import pandas as pd

    d = datetime.strptime(date_text, "%Y-%m-%d").date()
    fads = load_fads()
    rows = []
    for point in grid_points(bbox, cfg.TRAIN_GRID_RESOLUTION_DEG):
        rows.append(feature_row(date_text, point["lat"], point["lon"], d, fads))
    return pd.DataFrame(rows)


def feature_row(date_text: str, lat: float, lon: float, d, fads: list[tuple[float, float]]) -> dict:
    import math

    sst = synthetic_sst(lat, lon, d)
    gradient = max(0, 1.4 - abs(lon - (151.2 + (lat + 36.5) * 0.35)) * 2.2)
    depth = depth_proxy(lat, lon)
    return {
        "date": date_text,
        "lat": round(lat, 4),
        "lon": round(lon, 4),
        "sst_c": sst,
        "sst_gradient": round(gradient, 4),
        "sst_front_strength": round(gradient, 4),
        "sst_3d_change": 0.0,
        "sst_7d_change": 0.0,
        "uo": float("nan"),
        "vo": float("nan"),
        "current_speed": float("nan"),
        "current_direction_degrees": float("nan"),
        "current_edge_score": float("nan"),
        "zos": float("nan"),
        "sla_gradient": float("nan"),
        "eddy_score": float("nan"),
        "chl": float("nan"),
        "chl_log": float("nan"),
        "chl_gradient": float("nan"),
        "chl_edge_score": float("nan"),
        "chl_missing_flag": True,
        "chl_days_offset": float("nan"),
        "depth_m": depth,
        "slope": round(min(80, depth / 80), 4),
        "distance_to_200m_contour": abs(depth - 200) / 25,
        "distance_to_500m_contour": abs(depth - 500) / 25,
        "distance_to_1000m_contour": abs(depth - 1000) / 25,
        "distance_to_shelf_break": abs(depth - 200) / 25,
        "distance_to_nearest_fad_km": nearest_fad_distance(lat, lon, fads),
        "distance_to_browns_mountain_km": haversine_km(lat, lon, BROWNS[0], BROWNS[1]),
        "month": d.month,
        "day_of_year": d.timetuple().tm_yday,
        "month_sin": math.sin(2 * math.pi * d.month / 12),
        "month_cos": math.cos(2 * math.pi * d.month / 12),
        "data_availability_sst": True,
        "data_availability_physics": False,
        "data_availability_chl": False,
        "data_availability_bathymetry": True,
    }


def nearest_grid(value: float) -> float:
    return round(round(value / cfg.TRAIN_GRID_RESOLUTION_DEG) * cfg.TRAIN_GRID_RESOLUTION_DEG, 4)


def build_training_features_for_date(date_text: str, occurrences, random_count: int = 1200):
    import pandas as pd

    d = datetime.strptime(date_text, "%Y-%m-%d").date()
    fads = load_fads()
    cells = {
        (nearest_grid(float(row.decimalLatitude)), nearest_grid(float(row.decimalLongitude)))
        for row in occurrences.itertuples()
        if row.date == date_text
    }
    random.seed(hash(date_text) & 0xFFFF)
    while len(cells) < random_count:
        lat = round(random.uniform(cfg.TRAIN_BBOX["south_lat"], cfg.TRAIN_BBOX["north_lat"]), 4)
        lon = round(random.uniform(max(150.0, cfg.TRAIN_BBOX["west_lon"]), cfg.TRAIN_BBOX["east_lon"]), 4)
        cells.add((nearest_grid(lat), nearest_grid(lon)))
    return pd.DataFrame([feature_row(date_text, lat, lon, d, fads) for lat, lon in sorted(cells)])


def main() -> None:
    import pandas as pd

    ensure_dirs()
    occurrence_frames = []
    for species_id in cfg.SPECIES_CONFIG:
        path = cfg.DATA / "interim" / "occurrence_clean" / f"{species_id}_clean.parquet"
        if path.exists():
            occurrence_frames.append(pd.read_parquet(path))
    occurrences = pd.concat(occurrence_frames, ignore_index=True) if occurrence_frames else pd.DataFrame()
    dates = sorted(occurrences["date"].drop_duplicates().tolist()) if "date" in occurrences.columns else []
    if len(dates) > cfg.MAX_UNIQUE_TRAIN_DATES_FIRST_RUN:
        dates = dates[: cfg.MAX_UNIQUE_TRAIN_DATES_FIRST_RUN]
    if not dates:
        dates = [datetime.utcnow().date().isoformat()]
    outputs = []
    out_dir = cfg.DATA / "interim" / "feature_grid" / "daily_features"
    for old in out_dir.glob("features_*.parquet"):
        old.unlink()
    for date_text in dates:
        df = build_training_features_for_date(date_text, occurrences)
        out = try_write_parquet(df, cfg.DATA / "interim" / "feature_grid" / "daily_features" / f"features_{date_text}.parquet")
        outputs.append(str(out.relative_to(cfg.ROOT)))
        print({"date": date_text, "cells": len(df), "output": outputs[-1]})
    write_json(cfg.DATA / "interim" / "feature_grid" / "daily_features_summary.json", {"outputs": outputs, "note": "First run builds presence cells plus sampled background candidate cells per occurrence date."})


if __name__ == "__main__":
    main()
