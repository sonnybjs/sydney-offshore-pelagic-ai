from datetime import datetime, timezone
from math import cos, radians, sin
from typing import Dict, List

from app.core.config import BOUNDING_BOX, REGION_NAME


def sst_at(latitude: float, longitude: float) -> float:
    offshore = (longitude - BOUNDING_BOX["west_longitude"]) / (
        BOUNDING_BOX["east_longitude"] - BOUNDING_BOX["west_longitude"]
    )
    north = (latitude - BOUNDING_BOX["south_latitude"]) / (
        BOUNDING_BOX["north_latitude"] - BOUNDING_BOX["south_latitude"]
    )
    front = 1.2 if longitude > (151.15 + (latitude + 36.5) * 0.42) else -0.4
    eddy = 0.7 * sin((latitude + 34.0) * 3.0) * cos((longitude - 152.0) * 2.4)
    return round(17.0 + offshore * 6.8 + north * 1.3 + front + eddy, 1)


def gradient_at(latitude: float, longitude: float) -> float:
    front_line = 151.15 + (latitude + 36.5) * 0.42
    distance = abs(longitude - front_line)
    return round(max(0.1, 1.9 - distance * 3.1), 2)


def sst_category(sst_c: float) -> str:
    if sst_c < 18:
        return "cool"
    if sst_c < 21:
        return "moderate"
    if sst_c < 24:
        return "warm"
    return "very_warm"


def latest_ocean_summary() -> Dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data_source": "mock",
        "region_name": REGION_NAME,
        "bounding_box": BOUNDING_BOX,
        "sst_min_c": 16.8,
        "sst_max_c": 26.4,
        "dominant_current_direction": "south to south-east",
        "current_strength_label": "moderate offshore EAC-style flow",
        "chlorophyll_status": "mock chlorophyll edge near the shelf/front boundary",
        "sea_level_anomaly_status": "synthetic weak eddy signal east of Sydney",
        "cloud_warning": "No real satellite cloud mask is used in v0.1.",
        "freshness_note": "Synthetic demo data generated locally; not an observed ocean product.",
        "confidence": "Low - v0.1 uses synthetic ocean data.",
    }


def mock_sst_grid() -> Dict:
    features: List[Dict] = []
    latitudes = [-36.1, -35.5, -34.9, -34.3, -33.7, -33.1, -32.5]
    longitudes = [150.9, 151.4, 151.9, 152.4, 152.9, 153.4, 153.9]
    for lat in latitudes:
        for lon in longitudes:
            sst = sst_at(lat, lon)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "sst_c": sst,
                        "sst_category": sst_category(sst),
                        "gradient_strength": gradient_at(lat, lon),
                        "notes": "Synthetic SST point for v0.1 habitat scoring demo.",
                        "demo_only": True,
                    },
                }
            )
    return {"type": "FeatureCollection", "features": features}


def mock_current_vectors() -> Dict:
    features: List[Dict] = []
    for lat in [-35.8, -35.0, -34.2, -33.4, -32.6]:
        for lon in [151.3, 152.1, 152.9, 153.7]:
            eddy = abs(lat + 34.0) < 0.6 and abs(lon - 152.5) < 0.6
            direction = 135 if not eddy else 95
            speed = 0.45 + max(0, lon - 151.0) * 0.12 + (0.18 if eddy else 0)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "direction_degrees": direction,
                        "speed_m_s": round(speed, 2),
                        "direction_label": "south-east" if not eddy else "eastward eddy edge",
                        "notes": "Synthetic current vector, broadly EAC-like offshore flow.",
                        "demo_only": True,
                    },
                }
            )
    return {"type": "FeatureCollection", "features": features}


def mock_fronts() -> Dict:
    lines = [
        [[151.05, -36.3], [151.55, -35.3], [152.0, -34.3], [152.45, -33.3], [152.85, -32.3]],
        [[151.55, -35.8], [152.05, -34.9], [152.55, -34.0], [153.15, -33.1]],
    ]
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": line},
                "properties": {
                    "front_strength": "moderate" if index == 0 else "weak eddy edge",
                    "sst_change_c": 1.8 if index == 0 else 0.9,
                    "notes": "Synthetic SST front/edge for v0.1.",
                    "demo_only": True,
                },
            }
            for index, line in enumerate(lines)
        ],
    }

