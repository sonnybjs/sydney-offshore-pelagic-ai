from __future__ import annotations

import math
from pathlib import Path

from pipeline_lib import cfg, ensure_dirs, file_size_mb, format_bbox, save_dataframe, write_json


LOCAL_GEBCO = cfg.DATA / "raw" / "bathymetry" / "gebco" / "gebco_nsw_subset.nc"
INSTRUCTIONS = cfg.ROOT / "docs" / "GEBCO_DOWNLOAD_INSTRUCTIONS.md"


def write_instructions() -> None:
    text = f"""# GEBCO Subset Download Instructions

Do not download the global GEBCO grid for this project audit.

Download only the NSW / East Coast corridor subset:

- Source: GEBCO gridded bathymetry download app
- Product: latest GEBCO grid available, preferably GEBCO 2024 or newer
- Format: NetCDF
- BBox: {format_bbox(cfg.TRAIN_BBOX)}
- Save path: `data/raw/bathymetry/gebco/gebco_nsw_subset.nc`

Required bounds:

- south_lat = {cfg.TRAIN_BBOX['south_lat']}
- north_lat = {cfg.TRAIN_BBOX['north_lat']}
- west_lon = {cfg.TRAIN_BBOX['west_lon']}
- east_lon = {cfg.TRAIN_BBOX['east_lon']}

After placing the file, rerun:

```bash
python pipelines/08_prepare_gebco_bathymetry.py
```

The audit script will crop to TRAIN_BBOX, downsample to 0.05 degrees, and derive `depth_m`, `slope`, and `ocean_mask`.
"""
    INSTRUCTIONS.parent.mkdir(parents=True, exist_ok=True)
    INSTRUCTIONS.write_text(text, encoding="utf-8")


def find_local_gebco() -> Path | None:
    if LOCAL_GEBCO.exists():
        return LOCAL_GEBCO
    candidates = sorted((cfg.DATA / "raw" / "bathymetry" / "gebco").glob("gebco_*_n-27.0_s-39.0_w148.5_e158.5.nc"))
    candidates = [path for path in candidates if "_tid_" not in path.name]
    return candidates[0] if candidates else None


def read_local_gebco(local_file: Path) -> dict:
    import numpy as np
    import pandas as pd
    import xarray as xr

    ds = xr.open_dataset(local_file)
    lat_name = next((name for name in ["lat", "latitude", "y"] if name in ds.coords or name in ds.variables), None)
    lon_name = next((name for name in ["lon", "longitude", "x"] if name in ds.coords or name in ds.variables), None)
    var_name = next((name for name in ["elevation", "z", "Band1"] if name in ds.variables), None)
    if not (lat_name and lon_name and var_name):
        raise ValueError(f"Could not identify GEBCO lat/lon/elevation variables. Variables: {list(ds.variables)}")
    bbox = cfg.TRAIN_BBOX
    subset = ds[var_name].sel({lat_name: slice(bbox["south_lat"], bbox["north_lat"]), lon_name: slice(bbox["west_lon"], bbox["east_lon"])})
    target_lats = np.arange(bbox["south_lat"], bbox["north_lat"] + 1e-9, cfg.TRAIN_GRID_RESOLUTION_DEG)
    target_lons = np.arange(bbox["west_lon"], bbox["east_lon"] + 1e-9, cfg.TRAIN_GRID_RESOLUTION_DEG)
    interp = subset.interp({lat_name: target_lats, lon_name: target_lons}, method="nearest")
    values = interp.values
    lat_values = interp[lat_name].values
    lon_values = interp[lon_name].values
    gy, gx = np.gradient(values.astype(float))
    rows = []
    for i, lat in enumerate(lat_values):
      for j, lon in enumerate(lon_values):
        elevation = float(values[i, j])
        depth = max(0.0, -elevation)
        slope = float(math.hypot(gx[i, j], gy[i, j]))
        rows.append(
            {
                "lat": round(float(lat), 4),
                "lon": round(float(lon), 4),
                "depth_m": round(depth, 3),
                "slope": round(slope, 5),
                "ocean_mask": bool(elevation < 0),
            }
        )
    df = pd.DataFrame(rows)
    outputs = save_dataframe(
        df,
        cfg.DATA / "interim" / "feature_grid" / "bathymetry" / "bathymetry_features_0p05.csv",
        cfg.DATA / "interim" / "feature_grid" / "bathymetry" / "bathymetry_features_0p05.parquet",
    )
    return {
        "status": "processed_local_subset",
        "local_file": str(local_file.relative_to(cfg.ROOT)),
        "local_file_size_mb": file_size_mb(local_file),
        "cell_count": int(len(df)),
        "outputs": outputs,
        "derived": ["depth_m", "slope", "ocean_mask"],
    }


def main() -> None:
    ensure_dirs()
    write_instructions()
    local_file = find_local_gebco()
    if not local_file:
        summary = {
            "status": "local_subset_missing",
            "expected_path": str(LOCAL_GEBCO.relative_to(cfg.ROOT)),
            "message": "GEBCO subset file not found. Please download only the NSW/East Coast subset for TRAIN_BBOX and place it at data/raw/bathymetry/gebco/gebco_nsw_subset.nc",
            "instructions": str(INSTRUCTIONS.relative_to(cfg.ROOT)),
            "download_rule": "No global GEBCO download performed by this audit.",
        }
    else:
        try:
            summary = read_local_gebco(local_file)
        except Exception as exc:
            summary = {
                "status": "local_subset_read_failed",
                "expected_path": str(LOCAL_GEBCO.relative_to(cfg.ROOT)),
                "error": f"{type(exc).__name__}: {exc}",
                "instructions": str(INSTRUCTIONS.relative_to(cfg.ROOT)),
            }
    write_json(cfg.DATA / "interim" / "env_raw_index" / "gebco_status.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
