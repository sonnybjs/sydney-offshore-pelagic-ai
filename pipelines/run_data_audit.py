from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    "00_confirm_data_plan.py",
    "01_download_occurrence_obis.py",
    "03_clean_occurrence.py",
    "04_build_unique_date_list.py",
    "05_test_mur_sst_subset.py",
    "08_prepare_gebco_bathymetry.py",
    "09_create_placeholder_structure_files.py",
    "99_generate_data_audit_report.py",
]


def main() -> int:
    failures = []
    for step in STEPS:
        print(f"\n=== Running pipelines/{step} ===")
        result = subprocess.run([sys.executable, str(ROOT / "pipelines" / step)], cwd=ROOT)
        if result.returncode != 0:
            failures.append({"step": step, "returncode": result.returncode})
            print(f"Step failed but audit runner will continue where safe: {step}")
    if failures:
        print({"status": "completed_with_failures", "failures": failures})
        return 1
    print({"status": "completed", "report": "docs/DATA_AUDIT_REPORT.md"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
