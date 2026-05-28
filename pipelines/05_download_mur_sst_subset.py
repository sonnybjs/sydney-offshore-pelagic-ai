from datetime import datetime

from pipeline_lib import cfg, ensure_dirs, grid_points, synthetic_sst, try_write_parquet, write_json


def build_sst_features(date_text: str, bbox: dict, output_dir) -> dict:
    import pandas as pd

    d = datetime.strptime(date_text, "%Y-%m-%d").date()
    points = grid_points(bbox, cfg.TRAIN_GRID_RESOLUTION_DEG)
    rows = []
    for point in points:
        sst = synthetic_sst(point["lat"], point["lon"], d)
        sst_3 = synthetic_sst(point["lat"], point["lon"], d.replace(day=max(1, d.day - 3)))
        sst_7 = synthetic_sst(point["lat"], point["lon"], d.replace(day=max(1, d.day - 7)))
        rows.append(
            {
                "date": date_text,
                "lat": point["lat"],
                "lon": point["lon"],
                "sst_c": sst,
                "sst_gradient": round(abs(point["lon"] - (151.2 + (point["lat"] + 36.5) * 0.35)) * -0.25 + 1.4, 4),
                "sst_front_strength": round(max(0, 1.4 - abs(point["lon"] - (151.2 + (point["lat"] + 36.5) * 0.35)) * 2.2), 4),
                "sst_3d_change": round(sst - sst_3, 4),
                "sst_7d_change": round(sst - sst_7, 4),
                "sst_source": "synthetic_fallback_pending_remote_mur_subset",
            }
        )
    df = pd.DataFrame(rows)
    out = try_write_parquet(df, output_dir / f"sst_features_{date_text}.parquet")
    return {
        "date": date_text,
        "bbox": bbox,
        "cell_count": int(len(df)),
        "min_sst": float(df["sst_c"].min()),
        "max_sst": float(df["sst_c"].max()),
        "missing_percentage": 0.0,
        "output": str(out.relative_to(cfg.ROOT)),
        "note": "Remote MUR subset hook is scaffolded; this first run stores controlled synthetic SST-compatible features so the ML pipeline can run.",
    }


def main() -> None:
    ensure_dirs()
    print({"bbox": cfg.PREDICT_BBOX, "variables": ["analysed_sst"], "estimated_size": "<5 MB for one 0.05 degree processed feature grid"})
    out_dir = cfg.DATA / "interim" / "feature_grid" / "sst"
    date_text = datetime.utcnow().date().isoformat()
    summary = build_sst_features(date_text, cfg.PREDICT_BBOX, out_dir)
    write_json(cfg.DATA / "interim" / "env_raw_index" / "mur_sst_smoke_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
