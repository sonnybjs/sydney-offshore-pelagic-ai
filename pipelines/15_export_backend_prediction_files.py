from pipeline_lib import cfg, ensure_dirs, write_json


def main() -> None:
    import shutil

    ensure_dirs()
    backend_dir = cfg.ROOT / "backend" / "app" / "data" / "real_predictions"
    backend_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in (cfg.DATA / "processed" / "predictions").glob("*_sydney_heatmap.geojson"):
        dest = backend_dir / src.name
        shutil.copy2(src, dest)
        copied.append(str(dest.relative_to(cfg.ROOT)))
    write_json(backend_dir / "export_summary.json", {"copied": copied})
    print({"copied": copied})


if __name__ == "__main__":
    main()
