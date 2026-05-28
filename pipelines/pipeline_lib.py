import csv
import importlib.util
import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]


def load_config():
    path = Path(__file__).with_name("00_config.py")
    spec = importlib.util.spec_from_file_location("pipeline_config", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


cfg = load_config()


def ensure_dirs() -> None:
    dirs = [
        "data/raw/occurrence/obis",
        "data/raw/occurrence/gbif",
        "data/raw/occurrence/ala",
        "data/raw/occurrence/nsw_dpi",
        "data/raw/ocean/mur_sst",
        "data/raw/ocean/copernicus_physics",
        "data/raw/ocean/copernicus_chl",
        "data/raw/bathymetry/gebco",
        "data/raw/structure/fad",
        "data/raw/structure/poi",
        "data/interim/occurrence_clean",
        "data/interim/date_lists",
        "data/interim/env_raw_index",
        "data/interim/feature_grid/sst",
        "data/interim/feature_grid/bathymetry",
        "data/interim/feature_grid/physics",
        "data/interim/feature_grid/chl",
        "data/interim/feature_grid/daily_features",
        "data/interim/matched_presence",
        "data/interim/background_samples",
        "data/interim/training_samples",
        "data/processed/training",
        "data/processed/models",
        "data/processed/metrics",
        "data/processed/predictions",
        "data/processed/reports",
        "data/cache/downloads",
    ]
    for item in dirs:
        (ROOT / item).mkdir(parents=True, exist_ok=True)


def bbox_to_wkt(bbox: dict[str, float]) -> str:
    w, e = bbox["west_lon"], bbox["east_lon"]
    s, n = bbox["south_lat"], bbox["north_lat"]
    return f"POLYGON(({w} {s}, {e} {s}, {e} {n}, {w} {n}, {w} {s}))"


def in_bbox(lat: float, lon: float, bbox: dict[str, float]) -> bool:
    return bbox["south_lat"] <= lat <= bbox["north_lat"] and bbox["west_lon"] <= lon <= bbox["east_lon"]


def request_json(url: str, params: dict[str, Any] | None = None, timeout: int = 60) -> dict:
    full_url = url if not params else f"{url}?{urlencode(params)}"
    request = Request(full_url, headers={"User-Agent": "Sydney-Offshore-Pelagic-AI-Map/0.2 local training pipeline"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def write_rows_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not fields:
        seen = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.append(key)
        fields = seen
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def file_size_mb(path: Path) -> float:
    if not path.exists():
        return 0.0
    return round(path.stat().st_size / (1024 * 1024), 4)


def format_bbox(bbox: dict[str, float]) -> str:
    return (
        f"S {bbox['south_lat']}, N {bbox['north_lat']}, "
        f"W {bbox['west_lon']}, E {bbox['east_lon']}"
    )


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(item).replace("\n", "<br>") for item in row) + " |")
    return "\n".join(out)


def save_dataframe(df, csv_path: Path, parquet_path: Path | None = None) -> dict[str, Any]:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    result: dict[str, Any] = {"csv": str(csv_path.relative_to(ROOT)), "csv_size_mb": file_size_mb(csv_path)}
    if parquet_path is not None:
        try:
            parquet_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(parquet_path, index=False)
            result["parquet"] = str(parquet_path.relative_to(ROOT))
            result["parquet_size_mb"] = file_size_mb(parquet_path)
        except Exception as exc:
            result["parquet_warning"] = f"Parquet not written: {type(exc).__name__}: {exc}"
    return result


PROVENANCE_FIELDS = [
    "dataset_name",
    "source_name",
    "source_url_or_access_method",
    "download_date",
    "spatial_bbox",
    "time_range",
    "variables",
    "raw_file_path",
    "processed_file_path",
    "estimated_size_mb",
    "actual_size_mb",
    "license_or_terms_note",
    "used_for_training",
    "notes",
]


def append_provenance(row: dict[str, Any]) -> None:
    import csv
    from datetime import datetime, timezone

    path = ROOT / "data" / "processed" / "reports" / "DATA_PROVENANCE_LOG.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {field: row.get(field, "") for field in PROVENANCE_FIELDS}
    if not payload["download_date"]:
        payload["download_date"] = datetime.now(timezone.utc).isoformat()
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=PROVENANCE_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerow(payload)


def read_table(path: Path):
    import pandas as pd

    if path.with_suffix(".parquet").exists():
        return pd.read_parquet(path.with_suffix(".parquet"))
    if path.exists():
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()
    return pd.DataFrame()


def nearest_grid_value(value: float, resolution: float | None = None) -> float:
    res = resolution or cfg.TRAIN_GRID_RESOLUTION_DEG
    return round(round(value / res) * res, 4)


def read_rows_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt, size in (("%Y-%m-%d", 10), ("%Y-%m", 7), ("%Y", 4)):
        try:
            parsed = datetime.strptime(text[:size], fmt).date()
            return parsed
        except ValueError:
            continue
    return None


def date_range(start: date, end: date, step_days: int = 1) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=step_days)


def grid_points(bbox: dict[str, float], resolution: float) -> list[dict[str, float]]:
    points = []
    lat = bbox["south_lat"]
    while lat <= bbox["north_lat"] + 1e-9:
        lon = bbox["west_lon"]
        while lon <= bbox["east_lon"] + 1e-9:
            points.append({"lat": round(lat, 4), "lon": round(lon, 4)})
            lon += resolution
        lat += resolution
    return points


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def synthetic_sst(lat: float, lon: float, d: date) -> float:
    north = (lat - cfg.TRAIN_BBOX["south_lat"]) / (cfg.TRAIN_BBOX["north_lat"] - cfg.TRAIN_BBOX["south_lat"])
    offshore = (lon - cfg.TRAIN_BBOX["west_lon"]) / (cfg.TRAIN_BBOX["east_lon"] - cfg.TRAIN_BBOX["west_lon"])
    seasonal = math.sin((d.timetuple().tm_yday - 20) / 365 * 2 * math.pi) * 1.8
    front = 0.9 if lon > 151.2 + (lat + 36.5) * 0.35 else -0.4
    return round(17.5 + north * 3.0 + offshore * 4.0 + seasonal + front, 3)


def depth_proxy(lat: float, lon: float) -> float:
    shelf_break_lon = 151.4 + (lat + 36.5) * 0.08
    offshore = max(0.0, lon - shelf_break_lon)
    return round(60 + offshore * 850 + max(0, lon - 152.3) * 950, 2)


def rating(score: float) -> str:
    if score < 30:
        return "Low"
    if score < 55:
        return "Possible"
    if score < 75:
        return "Good"
    return "Prime"


def try_write_parquet(df, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
        return path
    except Exception:
        csv_path = path.with_suffix(".csv")
        df.to_csv(csv_path, index=False)
        return csv_path


def random_background_cells(points: list[dict[str, float]], n: int, forbidden: set[tuple[float, float]]) -> list[dict[str, float]]:
    candidates = [p for p in points if (round(p["lat"], 4), round(p["lon"], 4)) not in forbidden and p["lon"] > 150.0]
    if len(candidates) <= n:
        return candidates
    return random.sample(candidates, n)
