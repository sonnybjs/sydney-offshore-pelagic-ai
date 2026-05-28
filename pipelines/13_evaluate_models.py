from pipeline_lib import cfg, ensure_dirs, write_json


def main() -> None:
    import json

    ensure_dirs()
    summary = {}
    for path in (cfg.DATA / "processed" / "metrics").glob("*_metrics.json"):
        if path.name == "training_summary.json":
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        summary[path.stem.replace("_metrics", "")] = {
            "status": payload.get("status"),
            "presence": payload.get("presence"),
            "background": payload.get("background"),
            "best_model": payload.get("best_model"),
            "confidence": payload.get("confidence"),
            "metrics": payload.get("metrics"),
        }
    write_json(cfg.DATA / "processed" / "metrics" / "evaluation_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
