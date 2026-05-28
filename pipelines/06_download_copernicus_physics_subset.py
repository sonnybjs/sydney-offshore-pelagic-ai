from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from pipeline_lib import cfg, ensure_dirs, file_size_mb, write_json


HISTORICAL_DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
FORECAST_CURRENT_DATASET_ID = "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m"
VARIABLES = ["uo", "vo", "zos"]


def date_list(limit: int = 20) -> list[str]:
    path = cfg.DATA / "interim" / "date_lists" / "unique_training_dates.csv"
    if not path.exists():
        return []
    import pandas as pd

    df = pd.read_csv(path)
    if "date" not in df.columns:
        return []
    return sorted(df["date"].dropna().astype(str).unique().tolist())[:limit]


def copernicus_command_name() -> str | None:
    path_command = shutil.which("copernicusmarine")
    if path_command:
        return path_command
    venv_command = Path(sys.executable).parent / "copernicusmarine"
    if venv_command.exists():
        return str(venv_command)
    return None


def has_copernicus_credentials_file() -> bool:
    return (Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials").exists()


def command_for_date(date_text: str, out_dir: Path, executable: str = "copernicusmarine") -> list[str]:
    bbox = cfg.TRAIN_BBOX
    return [
        executable,
        "subset",
        "--dataset-id",
        HISTORICAL_DATASET_ID,
        "--variable",
        "uo",
        "--variable",
        "vo",
        "--variable",
        "zos",
        "--start-datetime",
        f"{date_text}T00:00:00",
        "--end-datetime",
        f"{date_text}T23:59:59",
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
        f"physics_{date_text}.nc",
        "--overwrite",
    ]


def main() -> None:
    ensure_dirs()
    out_dir = cfg.DATA / "raw" / "ocean" / "copernicus_physics"
    out_dir.mkdir(parents=True, exist_ok=True)
    dates = date_list()
    estimated_cells_per_date = round(((cfg.TRAIN_BBOX["north_lat"] - cfg.TRAIN_BBOX["south_lat"]) / 0.083) * ((cfg.TRAIN_BBOX["east_lon"] - cfg.TRAIN_BBOX["west_lon"]) / 0.083))
    estimated_mb_per_date = round(estimated_cells_per_date * len(VARIABLES) * 4 / (1024 * 1024), 2)
    cli = copernicus_command_name()
    has_cli = cli is not None
    has_env = bool(
        (os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME") and os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"))
        or (os.environ.get("COPERNICUSMARINE_USERNAME") and os.environ.get("COPERNICUSMARINE_PASSWORD"))
    )
    has_credentials_file = has_copernicus_credentials_file()
    note = {
        "status": "setup_check_only",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "products": ["GLOBAL_MULTIYEAR_PHY_001_030", "GLOBAL_ANALYSISFORECAST_PHY_001_024"],
        "historical_dataset_id": HISTORICAL_DATASET_ID,
        "forecast_current_dataset_id": FORECAST_CURRENT_DATASET_ID,
        "variables": VARIABLES,
        "bbox": cfg.TRAIN_BBOX,
        "surface_layer_only": True,
        "unique_dates_available_for_first_batch": dates,
        "estimated_cells_per_date": estimated_cells_per_date,
        "estimated_raw_mb_per_date_uncompressed": estimated_mb_per_date,
        "copernicusmarine_cli_found": has_cli,
        "copernicus_env_found": has_env,
        "copernicus_credentials_file_found": has_credentials_file,
        "downloaded_files": [],
        "reason": "Current data is not downloaded unless the Copernicus Marine toolbox and account environment are configured. This prevents accidental global/full-depth downloads.",
        "example_command": " ".join(command_for_date(dates[0], out_dir, cli or "copernicusmarine")) if dates else None,
    }
    if has_cli and (has_env or has_credentials_file) and dates:
        # Keep the first run intentionally tiny. Full training download should be expanded only
        # after this smoke test succeeds and the file size is reviewed.
        date_text = dates[0]
        command = command_for_date(date_text, out_dir, cli or "copernicusmarine")
        try:
            completed = subprocess.run(command, check=False, text=True, capture_output=True, timeout=600)
            out_file = out_dir / f"physics_{date_text}.nc"
            note.update(
                {
                    "status": "smoke_test_completed" if completed.returncode == 0 and out_file.exists() else "smoke_test_failed",
                    "returncode": completed.returncode,
                    "stdout_tail": completed.stdout[-2000:],
                    "stderr_tail": completed.stderr[-2000:],
                    "downloaded_files": [
                        {"path": str(out_file.relative_to(cfg.ROOT)), "size_mb": file_size_mb(out_file)}
                    ]
                    if out_file.exists()
                    else [],
                }
            )
        except Exception as exc:
            note.update({"status": "smoke_test_error", "error": f"{type(exc).__name__}: {exc}"})
    else:
        note["status"] = "skipped_missing_copernicus_setup"
    write_json(cfg.DATA / "interim" / "env_raw_index" / "copernicus_physics_status.json", note)
    print(note)


if __name__ == "__main__":
    main()
