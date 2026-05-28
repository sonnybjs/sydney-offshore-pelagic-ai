from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

TRAIN_BBOX = {"south_lat": -39.0, "north_lat": -27.0, "west_lon": 148.5, "east_lon": 158.5}
PREDICT_BBOX = {"south_lat": -36.5, "north_lat": -32.0, "west_lon": 150.5, "east_lon": 154.5}
OPTIONAL_EXTENDED_BBOX = {"south_lat": -44.5, "north_lat": -25.0, "west_lon": 145.0, "east_lon": 160.5}

SPECIES_CONFIG = {
    "yellowfin_tuna": {
        "species_id": "yellowfin_tuna",
        "scientific_name": "Thunnus albacares",
        "common_name": "Yellowfin Tuna",
        "first_run_start_date": "2015-01-01",
        "full_start_date": "2002-06-01",
        "priority": 1,
        "min_records_trainable": 300,
        "min_records_low_confidence": 100,
    },
    "mahi_mahi": {
        "species_id": "mahi_mahi",
        "scientific_name": "Coryphaena hippurus",
        "common_name": "Mahi Mahi / Dolphinfish",
        "first_run_start_date": "2015-01-01",
        "full_start_date": "2002-06-01",
        "priority": 2,
        "min_records_trainable": 300,
        "min_records_low_confidence": 100,
    },
    "striped_marlin": {
        "species_id": "striped_marlin",
        "scientific_name": "Kajikia audax",
        "common_name": "Striped Marlin",
        "first_run_start_date": "2015-01-01",
        "full_start_date": "2002-06-01",
        "priority": 3,
        "min_records_trainable": 300,
        "min_records_low_confidence": 100,
    },
    "southern_bluefin_tuna": {
        "species_id": "southern_bluefin_tuna",
        "scientific_name": "Thunnus maccoyii",
        "common_name": "Southern Bluefin Tuna",
        "first_run_start_date": "2015-01-01",
        "full_start_date": "2002-06-01",
        "priority": 4,
        "min_records_trainable": 300,
        "min_records_low_confidence": 100,
    },
    "yellowtail_kingfish": {
        "species_id": "yellowtail_kingfish",
        "scientific_name": "Seriola lalandi",
        "common_name": "Yellowtail Kingfish",
        "first_run_start_date": "2015-01-01",
        "full_start_date": "2002-06-01",
        "priority": 5,
        "min_records_trainable": 300,
        "min_records_low_confidence": 100,
    },
}

START_DATE_FULL = "2002-06-01"
START_DATE_FIRST_RUN = "2015-01-01"
END_DATE_FIRST_RUN = "2025-12-31"
MAX_UNIQUE_TRAIN_DATES_FIRST_RUN = 1000
TRAIN_GRID_RESOLUTION_DEG = 0.05
PREDICT_GRID_RESOLUTION_DEG = 0.05
HIGH_RES_PREDICT_GRID_RESOLUTION_DEG = 0.005
HIGH_RES_TRAIN_GRID_RESOLUTION_DEG = 0.005
REQUESTED_RECOMMENDATION_RADIUS_M = 500
RAW_DOWNLOAD_SIZE_LIMIT_GB = 10
PROCESSED_SIZE_LIMIT_GB = 5
MODEL_ARTIFACT_LIMIT_MB = 500
PREDICTION_OUTPUT_LIMIT_GB = 1
BACKGROUND_PER_PRESENCE_FIRST_RUN = 10

OBIS_API = "https://api.obis.org/v3/occurrence"
MUR_CMR_COLLECTION = "MUR-JPL-L4-GLOB-v4.1"
MUR_CMR_URL = "https://cmr.earthdata.nasa.gov/search/collections.json?short_name=MUR-JPL-L4-GLOB-v4.1"
MUR_AUDIT_DATE = "2024-02-15"
