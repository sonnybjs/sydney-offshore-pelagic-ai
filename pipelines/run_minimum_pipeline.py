import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    "01_download_occurrence_obis.py",
    "02_download_occurrence_gbif.py",
    "03_clean_occurrence.py",
    "04_build_unique_date_list.py",
    "05_download_mur_sst_subset.py",
    "06_download_copernicus_physics_subset.py",
    "07_download_copernicus_chl_subset.py",
    "08_prepare_gebco_bathymetry.py",
    "09_build_feature_grid.py",
    "10_match_presence_to_features.py",
    "11_generate_background_samples.py",
    "12_train_presence_background_models.py",
    "13_evaluate_models.py",
    "14_predict_sydney_heatmap.py",
    "15_export_backend_prediction_files.py",
]


def main() -> None:
    for step in STEPS:
        print(f"\n=== {step} ===")
        subprocess.run([sys.executable, str(ROOT / "pipelines" / step)], check=True)


if __name__ == "__main__":
    main()
