from __future__ import annotations

import math
from datetime import date, datetime

from pipeline_lib import append_provenance, cfg, ensure_dirs, save_dataframe, write_json


SYNODIC_MONTH_DAYS = 29.530588853
REFERENCE_NEW_MOON = date(2000, 1, 6)


def lunar_features(date_text: str) -> dict:
    d = datetime.strptime(date_text, "%Y-%m-%d").date()
    days = (d - REFERENCE_NEW_MOON).days
    age = days % SYNODIC_MONTH_DAYS
    phase = age / SYNODIC_MONTH_DAYS
    illumination = 0.5 * (1 - math.cos(2 * math.pi * phase))
    if phase < 0.03 or phase > 0.97:
        label = "new_moon"
    elif phase < 0.25:
        label = "waxing_crescent"
    elif phase < 0.28:
        label = "first_quarter"
    elif phase < 0.47:
        label = "waxing_gibbous"
    elif phase < 0.53:
        label = "full_moon"
    elif phase < 0.72:
        label = "waning_gibbous"
    elif phase < 0.78:
        label = "last_quarter"
    else:
        label = "waning_crescent"
    return {
        "date": date_text,
        "moon_age_days": round(age, 4),
        "moon_phase_fraction": round(phase, 6),
        "moon_illumination": round(illumination, 6),
        "moon_phase_sin": round(math.sin(2 * math.pi * phase), 8),
        "moon_phase_cos": round(math.cos(2 * math.pi * phase), 8),
        "moon_phase_label": label,
        "moon_source": "local_astronomical_approximation",
    }


def main() -> None:
    import pandas as pd

    ensure_dirs()
    out_dir = cfg.DATA / "interim" / "feature_grid" / "lunar"
    date_path = cfg.DATA / "interim" / "date_lists" / "unique_training_dates.csv"
    if not date_path.exists():
        raise FileNotFoundError("Missing unique_training_dates.csv")
    dates = sorted(pd.read_csv(date_path)["date"].dropna().astype(str).unique().tolist())
    df = pd.DataFrame([lunar_features(item) for item in dates])
    outputs = save_dataframe(
        df,
        out_dir / "lunar_features_by_date.csv",
        out_dir / "lunar_features_by_date.parquet",
    )
    summary = {"status": "written", "date_count": len(df), "outputs": outputs}
    write_json(cfg.DATA / "interim" / "env_raw_index" / "lunar_features_status.json", summary)
    append_provenance(
        {
            "dataset_name": "lunar_features",
            "source_name": "Local lunar phase approximation",
            "source_url_or_access_method": "Astronomical formula using synodic month; no external download",
            "spatial_bbox": "not spatial",
            "time_range": f"{min(dates)} to {max(dates)}" if dates else "",
            "variables": "moon_age_days, moon_phase_fraction, moon_illumination, moon_phase_sin, moon_phase_cos",
            "processed_file_path": outputs.get("csv", ""),
            "estimated_size_mb": "<1",
            "actual_size_mb": outputs.get("csv_size_mb", ""),
            "license_or_terms_note": "Generated local derived feature",
            "used_for_training": True,
            "notes": "Approximate lunar phase feature aligned by occurrence date.",
        }
    )
    print(summary)


if __name__ == "__main__":
    main()
