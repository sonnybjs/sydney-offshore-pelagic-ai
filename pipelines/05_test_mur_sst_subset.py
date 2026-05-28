from __future__ import annotations

import math
from pathlib import Path

from pipeline_lib import cfg, ensure_dirs, file_size_mb, save_dataframe, write_json


def erddap_csv_url() -> str:
    bbox = cfg.PREDICT_BBOX
    # CoastWatch ERDDAP exposes MUR-like gridded SST products in many deployments.
    # Dataset IDs can change, so the script records remote errors instead of pretending data exists.
    base = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/jplMURSST41.csvp"
    date = f"{cfg.MUR_AUDIT_DATE}T09:00:00Z"
    return (
        f"{base}?analysed_sst"
        f"[({date})]"
        f"[({bbox['south_lat']}):0.05:({bbox['north_lat']})]"
        f"[({bbox['west_lon']}):0.05:({bbox['east_lon']})]"
    )


def compute_gradient(rows):
    by_cell = {(round(row["lat"], 4), round(row["lon"], 4)): row["sst_c"] for row in rows}
    for row in rows:
        lat = round(row["lat"], 4)
        lon = round(row["lon"], 4)
        east = by_cell.get((lat, round(lon + cfg.PREDICT_GRID_RESOLUTION_DEG, 4)))
        north = by_cell.get((round(lat + cfg.PREDICT_GRID_RESOLUTION_DEG, 4), lon))
        dx = abs(east - row["sst_c"]) if east is not None else 0.0
        dy = abs(north - row["sst_c"]) if north is not None else 0.0
        row["sst_gradient"] = round(math.hypot(dx, dy), 5)
    return rows


def try_remote_subset() -> tuple[list[dict], str]:
    import pandas as pd

    url = erddap_csv_url()
    df = pd.read_csv(url)
    lower = {col.lower(): col for col in df.columns}
    lat_col = lower.get("latitude") or lower.get("lat")
    lon_col = lower.get("longitude") or lower.get("lon")
    sst_col = lower.get("analysed_sst") or lower.get("analysed_sst (kelvin)") or lower.get("analysed_sst (degree_c)")
    if not (lat_col and lon_col and sst_col):
        raise ValueError(f"Unexpected MUR CSV columns: {list(df.columns)}")
    rows = []
    for _, row in df.iterrows():
        raw = float(row[sst_col])
        sst_c = raw - 273.15 if raw > 100 else raw
        rows.append({"date": cfg.MUR_AUDIT_DATE, "lat": float(row[lat_col]), "lon": float(row[lon_col]), "sst_c": round(sst_c, 4)})
    return compute_gradient(rows), url


def main() -> None:
    ensure_dirs()
    out_dir = cfg.DATA / "interim" / "feature_grid" / "sst"
    out_csv = out_dir / f"sst_test_{cfg.MUR_AUDIT_DATE}.csv"
    out_parquet = out_dir / f"sst_test_{cfg.MUR_AUDIT_DATE}.parquet"
    summary = {
        "dataset": "NASA MUR SST v4.1 smoke test",
        "date": cfg.MUR_AUDIT_DATE,
        "bbox": cfg.PREDICT_BBOX,
        "variable": "analysed_sst",
        "download_rule": "one date and PREDICT_BBOX only; no global file; no full history",
        "status": "not_run",
    }
    try:
        import pandas as pd

        rows, url = try_remote_subset()
        df = pd.DataFrame(rows)
        outputs = save_dataframe(df, out_csv, out_parquet)
        missing_pct = float(df["sst_c"].isna().mean() * 100) if len(df) else 100.0
        summary.update(
            {
                "status": "success",
                "remote_url": url,
                "cell_count": int(len(df)),
                "min_sst_c": None if df.empty else float(df["sst_c"].min()),
                "max_sst_c": None if df.empty else float(df["sst_c"].max()),
                "mean_sst_c": None if df.empty else float(df["sst_c"].mean()),
                "missing_percentage": round(missing_pct, 4),
                "gradient_computed": "sst_gradient" in df.columns,
                "outputs": outputs,
                "output_file_size_mb": file_size_mb(out_csv),
            }
        )
    except Exception as exc:
        summary.update(
            {
                "status": "failed_remote_access",
                "error": f"{type(exc).__name__}: {exc}",
                "fallback": "No synthetic SST is written by this audit step. Check DATA_AUDIT_REPORT.md for setup notes.",
                "attempted_url": erddap_csv_url(),
            }
        )
    write_json(cfg.DATA / "interim" / "env_raw_index" / "mur_sst_smoke_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
