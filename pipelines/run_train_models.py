from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"


STEPS = [
    "13_validate_training_dataset.py",
    "14_train_models.py",
    "15_evaluate_models.py",
    "16_tune_and_select_models.py",
    "17_predict_sydney_heatmap.py",
    "18_export_model_artifacts.py",
]


def main() -> None:
    failures = []
    for step in STEPS:
        print(f"\n=== Running pipelines/{step} ===")
        result = subprocess.run([sys.executable, str(PIPELINES / step)], cwd=ROOT)
        if result.returncode != 0:
            failures.append({"step": step, "returncode": result.returncode})
            print({"status": "failed", "failures": failures})
            sys.exit(result.returncode)
    print(
        {
            "status": "completed",
            "summary": "data/processed/reports/MODEL_TRAINING_SUMMARY.md",
            "summary_json": "data/processed/reports/model_training_summary.json",
            "note": "No exact fish-location or true catch-probability claim is made.",
        }
    )


if __name__ == "__main__":
    main()
