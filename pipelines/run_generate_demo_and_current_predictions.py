from __future__ import annotations

import subprocess
import sys

from pipeline_lib import cfg, ensure_dirs, write_json
from prediction_manifest_lib import build_demo_manifest, load_existing_manifest, write_manifest


def main() -> None:
    ensure_dirs()
    manifest = load_existing_manifest()
    manifest["demo"] = build_demo_manifest()
    write_manifest(manifest)
    print({"demo_manifest": manifest["demo"]})
    result = subprocess.run([sys.executable, str(cfg.ROOT / "pipelines" / "19_predict_current_tomorrow.py")], cwd=cfg.ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    final_manifest = load_existing_manifest()
    write_json(
        cfg.DATA / "processed" / "predictions" / "prediction_generation_summary.json",
        {
            "status": "completed",
            "manifest": "data/processed/predictions/prediction_manifest.json",
            "demo_species": list(final_manifest.get("demo", {}).get("species", {}).keys()),
            "current_species": list(final_manifest.get("current", {}).get("species", {}).keys()),
        },
    )
    print({"status": "completed", "manifest": "data/processed/predictions/prediction_manifest.json"})


if __name__ == "__main__":
    main()
