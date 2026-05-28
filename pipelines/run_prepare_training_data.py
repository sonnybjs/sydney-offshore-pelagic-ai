from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    "09_build_daily_feature_grid.py",
    "10_match_presence_to_features.py",
    "11_generate_background_samples.py",
    "12_build_training_samples.py",
    "13_validate_training_dataset.py",
]


def main() -> int:
    failures = []
    for step in STEPS:
        print(f"\n=== Running pipelines/{step} ===")
        result = subprocess.run([sys.executable, str(ROOT / "pipelines" / step)], cwd=ROOT)
        if result.returncode != 0:
            failures.append({"step": step, "returncode": result.returncode})
            print(f"Step failed: {step}")
            break
    if failures:
        print({"status": "failed", "failures": failures})
        return 1
    print(
        {
            "status": "completed",
            "report": "data/processed/reports/TRAINING_DATASET_REPORT.md",
            "summary": "data/processed/reports/training_dataset_summary.json",
            "provenance": "data/processed/reports/DATA_PROVENANCE_LOG.csv",
            "note": "No model training was performed.",
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
