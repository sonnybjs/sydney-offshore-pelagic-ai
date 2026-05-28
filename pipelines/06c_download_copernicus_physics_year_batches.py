from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
import importlib.util
from pathlib import Path

import pandas as pd

from pipeline_lib import cfg, ensure_dirs, file_size_mb, write_json
from training_prep_lib import load_all_best_occurrences


def load_download_module():
    path = Path(__file__).with_name("06_download_copernicus_physics_subset.py")
    spec = importlib.util.spec_from_file_location("copernicus_physics_download", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


download_mod = load_download_module()

DATASET_ID = download_mod.HISTORICAL_DATASET_ID
VARIABLES = download_mod.VARIABLES


def unique_dates() -> list[str]:
    occurrences = load_all_best_occurrences()
    if not occurrences.empty and "date" in occurrences.columns:
        return sorted(occurrences["date"].dropna().astype(str).unique().tolist())
    path = cfg.DATA / "interim" / "date_lists" / "unique_training_dates.csv"
    if not path.exists():
        return []
    df = pd.read_csv(path)
    if "date" not in df.columns:
        return []
    return sorted(df["date"].dropna().astype(str).unique().tolist())


def year_batches(dates: list[str]) -> list[dict]:
    grouped: dict[str, list[str]] = defaultdict(list)
    for date_text in dates:
        grouped[date_text[:4]].append(date_text)
    batches = []
    for year, values in sorted(grouped.items()):
        start = min(values)
        end = max(values)
        days = (pd.to_datetime(end).date() - pd.to_datetime(start).date()).days + 1
        batches.append({"year": year, "start": start, "end": end, "unique_dates": len(values), "span_days": days})
    return batches


def estimate_size_mb(batches: list[dict]) -> float:
    # Conservative estimate based on the successful smoke test plus margin.
    smoke_file = cfg.DATA / "raw" / "ocean" / "copernicus_physics" / "physics_2015-01-23.nc"
    per_day_mb = max(file_size_mb(smoke_file), 0.2)
    return round(sum(batch["span_days"] for batch in batches) * per_day_mb * 1.5, 2)


def command_for_batch(batch: dict, out_dir: Path, executable: str) -> list[str]:
    bbox = cfg.TRAIN_BBOX
    return [
        executable,
        "subset",
        "--dataset-id",
        DATASET_ID,
        "--variable",
        "uo",
        "--variable",
        "vo",
        "--variable",
        "zos",
        "--start-datetime",
        f"{batch['start']}T00:00:00",
        "--end-datetime",
        f"{batch['end']}T23:59:59",
        "--minimum-longitude",
        str(bbox["west_lon"]),
        "--maximum-longitude",
        str(bbox["east_lon"]),
        "--minimum-latitude",
        str(bbox["south_lat"]),
        "--maximum-latitude",
        str(bbox["north_lat"]),
        "--minimum-depth",
        "0",
        "--maximum-depth",
        "1",
        "--output-directory",
        str(out_dir),
        "--output-filename",
        f"physics_{batch['year']}.nc",
        "--overwrite",
    ]


def main() -> None:
    ensure_dirs()
    out_dir = cfg.DATA / "raw" / "ocean" / "copernicus_physics"
    out_dir.mkdir(parents=True, exist_ok=True)
    dates = unique_dates()
    batches = year_batches(dates)
    estimated_mb = estimate_size_mb(batches)
    confirmation = {
        "title": "COPERNICUS PHYSICS YEAR-BATCH DOWNLOAD CHECK",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset_id": DATASET_ID,
        "variables": VARIABLES,
        "bbox": cfg.TRAIN_BBOX,
        "surface_layer_only": True,
        "date_source": "data/interim/date_lists/unique_training_dates.csv",
        "unique_dates": len(dates),
        "batches": batches,
        "estimated_raw_cache_mb": estimated_mb,
        "limit_mb": cfg.RAW_DOWNLOAD_SIZE_LIMIT_GB * 1024,
        "will_download": estimated_mb <= cfg.RAW_DOWNLOAD_SIZE_LIMIT_GB * 1024,
        "scope_note": "East Coast TRAIN_BBOX only. No WA, no full Australia, no global files, no full-depth layers.",
    }
    write_json(cfg.DATA / "interim" / "env_raw_index" / "copernicus_physics_year_batch_plan.json", confirmation)
    print(json.dumps(confirmation, indent=2))
    if not confirmation["will_download"]:
        print({"status": "stopped_size_limit_exceeded"})
        return
    executable = download_mod.copernicus_command_name()
    has_login = download_mod.has_copernicus_credentials_file()
    if not executable or not has_login:
        print({"status": "stopped_missing_copernicus_login", "cli": bool(executable), "credentials_file": has_login})
        return
    outputs = []
    for batch in batches:
        out_file = out_dir / f"physics_{batch['year']}.nc"
        if out_file.exists() and file_size_mb(out_file) > 0:
            outputs.append({"year": batch["year"], "status": "exists", "path": str(out_file.relative_to(cfg.ROOT)), "size_mb": file_size_mb(out_file)})
            continue
        command = command_for_batch(batch, out_dir, executable)
        completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=3600)
        outputs.append(
            {
                "year": batch["year"],
                "status": "downloaded" if completed.returncode == 0 and out_file.exists() else "failed",
                "returncode": completed.returncode,
                "path": str(out_file.relative_to(cfg.ROOT)) if out_file.exists() else "",
                "size_mb": file_size_mb(out_file),
                "stdout_tail": completed.stdout[-1000:],
                "stderr_tail": completed.stderr[-1000:],
            }
        )
        write_json(cfg.DATA / "interim" / "env_raw_index" / "copernicus_physics_year_batch_status.json", {"plan": confirmation, "outputs": outputs})
    summary = {"status": "completed", "plan": confirmation, "outputs": outputs}
    write_json(cfg.DATA / "interim" / "env_raw_index" / "copernicus_physics_year_batch_status.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
