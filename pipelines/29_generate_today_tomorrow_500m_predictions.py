from __future__ import annotations

import gzip
import importlib.util
import json
import math
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen, urlretrieve

import numpy as np
import pandas as pd

from pipeline_lib import cfg, ensure_dirs, grid_points, nearest_grid_value, write_json
from training_prep_lib import grid_id, load_bathymetry, load_structure_points, nearest_structure, seasonality


SPECIES = ["mahi_mahi", "southern_bluefin_tuna", "yellowtail_kingfish"]
IMOS_CATALOG = "https://thredds.aodn.org.au/thredds/catalog/IMOS/OceanCurrent/GSLA/NRT/{year}/catalog.html"
IMOS_FILESERVER = "https://thredds.aodn.org.au/thredds/fileServer/IMOS/OceanCurrent/GSLA/NRT/{year}/{name}"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


legacy = load_module("legacy_500m_current", cfg.ROOT / "pipelines" / "27_generate_500m_prediction_heatmaps.py")
deep = load_module("deep_500m_current", cfg.ROOT / "pipelines" / "28_generate_500m_deep_prediction_heatmaps.py")
current_fetch = load_module("current_fetch", cfg.ROOT / "pipelines" / "19_predict_current_tomorrow.py")


def today_sydney() -> str:
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Australia/Sydney")).date().isoformat()
    except Exception:
        return datetime.now().date().isoformat()


def target_dates() -> list[str]:
    today = datetime.strptime(today_sydney(), "%Y-%m-%d").date()
    return [today.isoformat(), (today + timedelta(days=1)).isoformat()]


def latest_local_sst(target_date: str) -> tuple[str, pd.DataFrame, dict]:
    base = cfg.DATA / "interim" / "feature_grid" / "sst"
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    candidates: list[tuple[str, Path]] = []
    for path in sorted(list(base.glob("sst_features_*.parquet")) + list(base.glob("sst_features_*.csv"))):
        date_text = path.stem.replace("sst_features_", "")
        try:
            date_value = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue
        if date_value <= target:
            candidates.append((date_text, path))
    if not candidates:
        raise RuntimeError("No local SST feature files are available for current fallback.")
    date_text, path = sorted(candidates, key=lambda item: item[0])[-1]
    frame = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path)
    frame = frame.copy()
    frame["lat"] = pd.to_numeric(frame["lat"], errors="coerce").round(4)
    frame["lon"] = pd.to_numeric(frame["lon"], errors="coerce").round(4)
    frame["sst_c"] = pd.to_numeric(frame["sst_c"], errors="coerce")
    frame = frame.dropna(subset=["lat", "lon", "sst_c"])
    return date_text, frame, {
        "source": str(path.relative_to(cfg.ROOT)),
        "method": "local_latest_sst_fallback",
        "note": "Remote current SST was unavailable or skipped; using latest local SST feature file.",
    }


def load_sst_for_target(target_date: str) -> tuple[str, pd.DataFrame, dict]:
    attempts: list[dict] = []
    try:
        source_date, frame, remote_attempts = current_fetch.latest_available_sst(target_date)
        attempts = remote_attempts
        frame = frame.copy()
        frame["sst_source"] = "remote_mur_erddap_subset"
        return source_date, frame, {"method": "remote_mur_erddap_subset", "attempts": attempts}
    except Exception as exc:
        attempts.append({"status": "remote_failed", "error": f"{type(exc).__name__}: {exc}"})
    source_date, frame, info = latest_local_sst(target_date)
    info["attempts"] = attempts
    return source_date, frame, info


def latest_imos_oceancurrent(target_date: str) -> tuple[str | None, Path | None, dict]:
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    raw_dir = cfg.DATA / "raw" / "ocean" / "imos_oceancurrent"
    raw_dir.mkdir(parents=True, exist_ok=True)
    attempts: list[dict] = []
    for year in [target.year, target.year - 1]:
        catalog_url = IMOS_CATALOG.format(year=year)
        try:
            html = urlopen(catalog_url, timeout=30).read().decode("utf-8")
        except Exception as exc:
            attempts.append({"year": year, "status": "catalog_failed", "error": f"{type(exc).__name__}: {exc}"})
            continue
        names = sorted(set(re.findall(r"IMOS_OceanCurrent_HV_(\d{8})T\d{6}Z_GSLA_FV02_NRT\.nc", html)))
        dated = []
        for date_token in names:
            date_value = datetime.strptime(date_token, "%Y%m%d").date()
            if date_value <= target:
                filename = f"IMOS_OceanCurrent_HV_{date_token}T000000Z_GSLA_FV02_NRT.nc"
                # Older files in early 2026 used 180000Z; keep the exact name from catalog if present.
                match = re.search(rf"(IMOS_OceanCurrent_HV_{date_token}T\d{{6}}Z_GSLA_FV02_NRT\.nc)", html)
                if match:
                    filename = match.group(1)
                dated.append((date_value.isoformat(), filename))
        if not dated:
            attempts.append({"year": year, "status": "no_files_before_target"})
            continue
        source_date, filename = dated[-1]
        local_path = raw_dir / filename
        if not local_path.exists():
            url = IMOS_FILESERVER.format(year=year, name=filename)
            urlretrieve(url, local_path)
        return source_date, local_path, {
            "method": "imos_oceancurrent_gsla_nrt",
            "source_url": IMOS_FILESERVER.format(year=year, name=filename),
            "local_file": str(local_path.relative_to(cfg.ROOT)),
            "attempts": attempts,
        }
    return None, None, {"method": "imos_oceancurrent_gsla_nrt", "status": "unavailable", "attempts": attempts}


def attach_imos_currents(frame: pd.DataFrame, target_date: str) -> tuple[pd.DataFrame, dict]:
    source_date, local_path, info = latest_imos_oceancurrent(target_date)
    if not local_path or not local_path.exists():
        return frame, info
    try:
        import xarray as xr

        ds = xr.open_dataset(local_path)
        bbox = cfg.PREDICT_BBOX
        ds = ds.sel(
            LATITUDE=slice(bbox["south_lat"] - 0.5, bbox["north_lat"] + 0.5),
            LONGITUDE=slice(bbox["west_lon"] - 0.5, bbox["east_lon"] + 0.5),
        )
        speed_grid = np.hypot(ds["UCUR"].isel(TIME=0).values.astype(float), ds["VCUR"].isel(TIME=0).values.astype(float))
        gy, gx = np.gradient(speed_grid)
        edge = xr.DataArray(np.hypot(gx, gy), coords=ds["UCUR"].isel(TIME=0).coords, dims=ds["UCUR"].isel(TIME=0).dims)
        points_lat = xr.DataArray(frame["lat"].astype(float).to_numpy(), dims="points")
        points_lon = xr.DataArray(frame["lon"].astype(float).to_numpy(), dims="points")
        u = ds["UCUR"].isel(TIME=0).interp(LATITUDE=points_lat, LONGITUDE=points_lon).to_numpy()
        v = ds["VCUR"].isel(TIME=0).interp(LATITUDE=points_lat, LONGITUDE=points_lon).to_numpy()
        gsl = ds["GSL"].isel(TIME=0).interp(LATITUDE=points_lat, LONGITUDE=points_lon).to_numpy()
        gsla = ds["GSLA"].isel(TIME=0).interp(LATITUDE=points_lat, LONGITUDE=points_lon).to_numpy()
        current_edge = edge.interp(LATITUDE=points_lat, LONGITUDE=points_lon).to_numpy()
        out = frame.copy()
        out["uo"] = u
        out["vo"] = v
        out["current_speed"] = np.hypot(u, v)
        out["current_direction_degrees"] = (np.degrees(np.arctan2(u, v)) + 360) % 360
        out["current_edge_score"] = current_edge
        out["zos"] = gsl
        out["sla_gradient"] = current_edge
        out["eddy_score"] = pd.Series(gsla).rank(pct=True).to_numpy() * 100.0
        out["physics_missing_flag"] = pd.isna(out["current_speed"])
        out["physics_source_date"] = source_date
        out["physics_date_offset_days"] = (
            datetime.strptime(target_date, "%Y-%m-%d").date()
            - datetime.strptime(source_date, "%Y-%m-%d").date()
        ).days
        out["has_physics"] = out["current_speed"].notna()
        info.update({"status": "loaded", "source_date": source_date, "variables": ["UCUR", "VCUR", "GSL", "GSLA"]})
        return out, info
    except Exception as exc:
        info.update({"status": "failed_to_process", "error": f"{type(exc).__name__}: {exc}"})
        return frame, info


def prepare_source_feature_grid(target_date: str) -> tuple[pd.DataFrame, dict]:
    source_date, sst, source_info = load_sst_for_target(target_date)
    frame = sst.copy()
    frame["date"] = target_date
    frame["grid_id"] = [grid_id(float(lat), float(lon)) for lat, lon in zip(frame["lat"], frame["lon"])]
    frame["sst_missing_flag"] = frame["sst_c"].isna()
    frame["sst_source_date"] = source_date
    frame["sst_date_offset_days"] = (
        datetime.strptime(target_date, "%Y-%m-%d").date()
        - datetime.strptime(source_date, "%Y-%m-%d").date()
    ).days

    for col in ["sst_gradient", "sst_front_strength", "sst_3d_change", "sst_7d_change"]:
        if col not in frame.columns:
            frame[col] = math.nan

    bathy = load_bathymetry()
    if not bathy.empty:
        bathy = bathy.copy()
        bathy["lat"] = pd.to_numeric(bathy["lat"], errors="coerce").round(4)
        bathy["lon"] = pd.to_numeric(bathy["lon"], errors="coerce").round(4)
        frame = frame.merge(bathy, on=["lat", "lon"], how="left")
        frame["has_bathymetry"] = frame.get("depth_m").notna()
    else:
        for col in ["depth_m", "slope", "ocean_mask", "distance_to_200m_contour", "distance_to_500m_contour", "distance_to_1000m_contour", "distance_to_shelf_break"]:
            frame[col] = math.nan
        frame["has_bathymetry"] = False

    structures = load_structure_points()
    structure_df = pd.DataFrame([nearest_structure(float(row.lat), float(row.lon), structures) for row in frame.itertuples()])
    frame = pd.concat([frame.reset_index(drop=True), structure_df.reset_index(drop=True)], axis=1)
    frame["has_structure"] = bool(structures)

    for col in ["uo", "vo", "current_speed", "current_direction_degrees", "current_edge_score", "zos", "sla_gradient", "eddy_score", "chl", "chl_log", "chl_gradient", "chl_edge_score", "o2", "dissolved_oxygen", "oxygen_saturation"]:
        if col not in frame.columns:
            frame[col] = math.nan
    frame["physics_missing_flag"] = True
    frame["physics_source_date"] = None
    frame["physics_date_offset_days"] = math.nan
    frame["has_physics"] = False
    frame, physics_info = attach_imos_currents(frame, target_date)
    frame["chl_missing_flag"] = True
    frame["chl_source_date"] = None
    frame["chl_date_offset_days"] = math.nan
    frame["has_chl"] = False
    frame["oxygen_missing_flag"] = True
    frame["has_oxygen"] = False
    frame["has_sst"] = frame["sst_c"].notna()
    for col in ["moon_age_days", "moon_phase_fraction", "moon_illumination", "moon_phase_sin", "moon_phase_cos"]:
        frame[col] = math.nan
    frame["moon_phase_label"] = "unavailable"
    frame["has_lunar"] = False
    frame["has_weather"] = False
    for key, value in seasonality(target_date).items():
        frame[key] = value
    frame["feature_set_name"] = "current_sst_bathy_structure"
    if "ocean_mask" in frame.columns and frame["ocean_mask"].notna().any():
        frame = frame[(frame["ocean_mask"].isna()) | (frame["ocean_mask"].astype(bool))].copy()
    return frame, source_info | {"sst_source_date": source_date, "physics": physics_info}


def write_daily_feature_grid(target_date: str, frame: pd.DataFrame) -> Path:
    out = cfg.DATA / "interim" / "feature_grid" / "daily_features" / f"features_{target_date}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(out, index=False)
    csv_path = out.with_suffix(".csv")
    frame.to_csv(csv_path, index=False)
    return out


def gzip_file(path: Path) -> Path:
    gz_path = path.with_suffix(path.suffix + ".gz")
    with path.open("rb") as src, gzip.open(gz_path, "wb", compresslevel=9) as dst:
        shutil.copyfileobj(src, dst)
    return gz_path


def ensure_gzip_for_outputs(results: list[dict]) -> None:
    for result in results:
        rel = result.get("top_geojson")
        if not rel:
            continue
        path = cfg.ROOT / rel
        if path.exists():
            gzip_file(path)


def add_current_metadata_to_geojson(path: Path, target_date: str, source_info: dict, model_source: str) -> None:
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    for feature in payload.get("features", []):
        props = feature.setdefault("properties", {})
        props["mode"] = "current"
        props["target_date"] = target_date
        props["prediction_date"] = target_date
        props["sst_source_date"] = props.get("sst_source_date") or source_info.get("sst_source_date")
        props["physics_source_date"] = props.get("physics_source_date")
        props["chl_source_date"] = props.get("chl_source_date")
        props["current_run_type"] = "today_or_tomorrow_current_inference"
        props["model_source"] = model_source
        props["limitations"] = (
            "Current inference uses latest available SST if target-date SST is unavailable; "
            "relative habitat suitability only, not exact fish location or guaranteed catch."
        )
    write_json(path, payload)
    gzip_file(path)


def predict_for_target(target_date: str, torch, device: str) -> dict:
    source_grid, source_info = prepare_source_feature_grid(target_date)
    source_path = write_daily_feature_grid(target_date, source_grid)
    date_text, high_grid = legacy.build_500m_grid(target_date)
    if high_grid.empty:
        return {"target_date": target_date, "status": "skipped_no_high_res_grid"}

    sl_results = []
    dl_results = []
    for species_id in SPECIES:
        print(f"current inference target={target_date} species={species_id} model=scikit_learn", flush=True)
        sl = legacy.predict_species(species_id, target_date, high_grid)
        sl_results.append(sl)
        if sl.get("top_geojson"):
            add_current_metadata_to_geojson(cfg.ROOT / sl["top_geojson"], target_date, source_info, "scikit_learn")

        print(f"current inference target={target_date} species={species_id} model=deep_learning device={device}", flush=True)
        dl = deep.predict_species(species_id, target_date, high_grid, torch, device)
        dl_results.append(dl)
        if dl.get("top_geojson"):
            add_current_metadata_to_geojson(cfg.ROOT / dl["top_geojson"], target_date, source_info, "deep_learning")

    ensure_gzip_for_outputs(sl_results)
    ensure_gzip_for_outputs(dl_results)
    return {
        "target_date": target_date,
        "status": "completed",
        "source_feature_grid": str(source_path.relative_to(cfg.ROOT)),
        "sst_source_date": source_info.get("sst_source_date"),
        "sst_access": source_info,
        "scikit_learn": sl_results,
        "deep_learning": dl_results,
    }


def update_manifest(results: list[dict]) -> None:
    manifest_path = cfg.DATA / "processed" / "predictions" / "prediction_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"demo": {"mode": "demo", "species": {}}, "current": {"mode": "current", "species": {}}}
    available_dates = [item["target_date"] for item in results if item.get("status") == "completed"]
    latest = available_dates[-1] if available_dates else None
    current_species = {}
    latest_completed = next((r for r in reversed(results) if r.get("status") == "completed"), {})
    latest_physics = ((latest_completed.get("sst_access") or {}).get("physics") or {}).get("source_date")
    for species_id in SPECIES:
        current_species[species_id] = {
            "available": bool(latest),
            "mode": "current",
            "species_id": species_id,
            "common_name": cfg.SPECIES_CONFIG[species_id]["common_name"],
            "prediction_date": latest,
            "target_date": latest,
            "available_dates": available_dates,
            "file_path": f"data/processed/predictions_500m/{latest}_{species_id}_500m_sydney_heatmap_top.geojson" if latest else "",
            "model_type": "current_inference",
            "model_confidence": "Low",
            "feature_set_name": "current_sst_bathy_structure",
            "data_source_dates": {
                "sst": next((r.get("sst_source_date") for r in reversed(results) if r.get("status") == "completed"), None),
                "physics": latest_physics,
                "chl": None,
                "bathymetry": "static",
            },
            "available_layers": ["habitat_heatmap", "hotspot_points", "poi_markers", "sst_front_proxy"],
            "audit_status": "current_inference_under_audit",
            "warning": "Current/tomorrow output uses latest available environmental data where target-day sources are unavailable.",
            "score_explanation": "Score is relative habitat suitability / hotspot score, not exact fish location or true catch probability.",
            "grid_resolution_m_estimate": 500,
            "source_resolution_note": "500m display grid resampled from source environmental features.",
            "notes": "Today/tomorrow inference is experimental and should be used as decision-support only.",
        }
    manifest["current"] = {
        "mode": "current",
        "target_date": latest,
        "available_dates": available_dates,
        "species": current_species,
        "notes": "Current mode includes today and tomorrow if generated; SST may use the latest available source date.",
    }
    write_json(manifest_path, manifest)


def main() -> None:
    ensure_dirs()
    torch = deep.import_torch()
    device = "cuda" if torch.cuda.is_available() else "cpu"
    results = []
    for target_date in target_dates():
        results.append(predict_for_target(target_date, torch, device))
    update_manifest(results)
    summary = {
        "status": "completed",
        "generated_dates": [item.get("target_date") for item in results],
        "species": SPECIES,
        "device": device,
        "outputs": results,
        "limitations": [
            "MUR SST can lag current/tomorrow target dates; latest available SST is used and labelled.",
            "Copernicus physics/chlorophyll are not available in this run, so current/chl fields remain missing.",
            "Relative habitat suitability only; not exact fish location or guaranteed catch.",
        ],
    }
    write_json(cfg.DATA / "processed" / "predictions" / "today_tomorrow_prediction_summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
