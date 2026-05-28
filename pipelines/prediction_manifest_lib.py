from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pipeline_lib import cfg, write_json


DEMO_SPECIES = ["yellowfin_tuna", "mahi_mahi", "striped_marlin"]


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def metadata_for(species_id: str) -> dict[str, Any]:
    return read_json(cfg.DATA / "processed" / "models" / species_id / "model_metadata.json", {}) or {}


def prediction_files_for(species_id: str, mode: str | None = None) -> list[Path]:
    suffix = f"_{species_id}_sydney_heatmap.geojson" if mode != "current" else f"_{species_id}_current_sydney_heatmap.geojson"
    paths = sorted((cfg.DATA / "processed" / "predictions").glob(f"*{suffix}"))
    if mode == "demo":
        paths = [path for path in paths if "_current_" not in path.name]
    return paths


def date_from_name(path: Path) -> str | None:
    match = re.match(r"(\d{4}-\d{2}-\d{2})_", path.name)
    return match.group(1) if match else None


def source_dates_from_geojson(path: Path) -> dict[str, Any]:
    payload = read_json(path, {"features": []})
    props = payload.get("features", [{}])[0].get("properties", {}) if payload.get("features") else {}
    return {
        "sst": props.get("sst_source_date") or props.get("date"),
        "physics": props.get("physics_source_date"),
        "chl": props.get("chl_source_date"),
        "bathymetry": "static",
    }


def species_entry(species_id: str, mode: str, path: Path | None, target_date: str | None = None) -> dict[str, Any]:
    meta = metadata_for(species_id)
    if not path:
        return {
            "available": False,
            "species_id": species_id,
            "common_name": meta.get("common_name") or cfg.SPECIES_CONFIG.get(species_id, {}).get("common_name", species_id),
            "reason": meta.get("reason") or "No trained model prediction file is available for this species.",
            "model_confidence": meta.get("confidence_level") or "Unavailable",
            "notes": "Unavailable species is shown clearly in the UI; no fallback fish-location claim is made.",
        }
    date = date_from_name(path)
    return {
        "available": True,
        "mode": mode,
        "species_id": species_id,
        "common_name": meta.get("common_name") or cfg.SPECIES_CONFIG.get(species_id, {}).get("common_name", species_id),
        "prediction_date": date,
        "target_date": target_date or date,
        "file_path": str(path.relative_to(cfg.ROOT)),
        "model_type": meta.get("model_type"),
        "model_confidence": meta.get("confidence_level", "Low"),
        "feature_set_name": meta.get("feature_set_name"),
        "data_source_dates": source_dates_from_geojson(path),
        "available_layers": ["habitat_heatmap", "hotspot_points", "poi_markers", "sst_front_proxy"],
        "notes": "Relative habitat suitability from a presence/background model; not exact fish location or guaranteed catch.",
    }


def build_demo_manifest() -> dict[str, Any]:
    species_entries = {}
    preferred_demo_date = (read_json(cfg.DATA / "processed" / "predictions" / "real_model_prediction_summary.json", {}) or {}).get("date")
    dates_by_species = {}
    for species_id in DEMO_SPECIES:
        paths = prediction_files_for(species_id, mode="demo")
        dates_by_species[species_id] = {date_from_name(path): path for path in paths if date_from_name(path)}
    common_dates = set.intersection(*(set(v.keys()) for v in dates_by_species.values())) if dates_by_species else set()
    demo_date = preferred_demo_date if preferred_demo_date in common_dates else max(common_dates) if common_dates else None
    for species_id in DEMO_SPECIES:
        path = dates_by_species[species_id].get(demo_date) if demo_date else None
        if not path and dates_by_species[species_id]:
            latest_date = preferred_demo_date if preferred_demo_date in dates_by_species[species_id] else max(dates_by_species[species_id])
            path = dates_by_species[species_id][latest_date]
        species_entries[species_id] = species_entry(species_id, "demo", path)
    return {
        "mode": "demo",
        "date": demo_date,
        "species": species_entries,
        "notes": "Demo mode uses the most recent historical trained-model prediction files available per species.",
    }


def load_existing_manifest() -> dict[str, Any]:
    return read_json(cfg.DATA / "processed" / "predictions" / "prediction_manifest.json", {"demo": {}, "current": {}}) or {"demo": {}, "current": {}}


def write_manifest(manifest: dict[str, Any]) -> None:
    write_json(cfg.DATA / "processed" / "predictions" / "prediction_manifest.json", manifest)
