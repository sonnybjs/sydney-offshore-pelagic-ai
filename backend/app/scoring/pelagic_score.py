from datetime import datetime, timezone
from typing import Any, Dict, List

from app.scoring.common import clamp, rating_for, range_score


STRATEGIES = {
    "yellowfin_tuna": "Focus on temperature breaks and current edges near shelf/canyon structure.",
    "southern_bluefin_tuna": "Look for cooler offshore water and strong frontal zones along the shelf edge.",
    "striped_marlin": "Work warm blue water near the shelf edge where bait may collect.",
    "blue_marlin": "Prioritise warmer deep offshore water and current edges on the oceanic side of the shelf.",
    "mahi_mahi": "Prioritise FAD-like structure and current lines in warm water.",
    "offshore_kingfish": "Focus on structure where current is pushing over reef, ridge, or seamount features.",
    "longtail_tuna": "Look for warm pushes and bait/current edges around shelf-transition water.",
}


def season_score(profile: Dict[str, Any], month: int | None = None) -> float:
    month = month or datetime.now(timezone.utc).month
    labels = {1:"Jan",2:"Feb",3:"Mar",4:"Apr",5:"May",6:"Jun",7:"Jul",8:"Aug",9:"Sep",10:"Oct",11:"Nov",12:"Dec"}
    label = profile.get("seasonality_by_month", {}).get(labels[month], "possible")
    return {"prime": 100, "good": 78, "possible": 52, "low": 25}.get(label, 50)


def structure_score(profile: Dict[str, Any], poi_type: str, depth_class: str) -> float:
    score = 35.0
    prefs = set(profile.get("structure_preference", []))
    depth_prefs = set(profile.get("depth_preference", []))
    if poi_type in prefs:
        score += 40
    if depth_class in depth_prefs:
        score += 25
    if poi_type in {"shelf_break", "canyon"} and any(x in prefs for x in {"shelf_break", "canyon"}):
        score += 10
    if poi_type == "fad_demo" and "fad_demo" in prefs:
        score += 25
    return clamp(score)


def score_pelagic_habitat(profile: Dict[str, Any], context: Dict[str, Any], month: int | None = None) -> Dict[str, Any]:
    sst = float(context["sst_c"])
    gradient = float(context.get("gradient_strength", 0))
    current_speed = float(context.get("current_speed_m_s", 0.4))
    poi_type = context.get("poi_type", "current_edge")
    depth_class = context.get("depth_class", "deep")
    data_confidence = context.get("data_confidence", "mock")

    sst_component = range_score(sst, profile["preferred_sst_range_c"], profile["extended_sst_range_c"])
    front_component = clamp(gradient * 48)
    current_component = clamp(35 + current_speed * 72)
    bathy_component = 85 if depth_class in profile.get("depth_preference", []) else 45
    structure_component = structure_score(profile, poi_type, depth_class)
    fad_component = 95 if poi_type == "fad_demo" and "fad_demo" in profile.get("structure_preference", []) else 40
    shelf_canyon_component = 90 if poi_type in {"shelf_break", "canyon"} else 45
    season_component = season_score(profile, month)
    chlorophyll_component = 68 if gradient >= 1.0 else 42
    eddy_component = 70 if context.get("eddy_signal", False) else 48

    weights = {
        "sst": 0.22,
        "front": 0.14,
        "current": 0.10,
        "bathy": 0.10,
        "structure": 0.13,
        "fad": 0.06,
        "shelf_canyon": 0.09,
        "season": 0.08,
        "chlorophyll": 0.04,
        "eddy": 0.04,
    }
    if profile["species_id"] == "mahi_mahi":
        weights.update({"fad": 0.18, "structure": 0.14, "shelf_canyon": 0.03, "bathy": 0.06})
    if profile["species_id"] == "offshore_kingfish":
        weights.update({"structure": 0.22, "current": 0.13, "fad": 0.02, "bathy": 0.13})
    if profile["species_id"] == "blue_marlin":
        weights.update({"sst": 0.25, "bathy": 0.14, "front": 0.10})

    components = {
        "SST suitability": sst_component,
        "SST front / gradient": front_component,
        "Current edge": current_component,
        "Bathymetry / depth class": bathy_component,
        "POI structure": structure_component,
        "FAD proximity": fad_component,
        "Shelf/canyon proximity": shelf_canyon_component,
        "Season/month": season_component,
        "Chlorophyll edge placeholder": chlorophyll_component,
        "SLA / eddy placeholder": eddy_component,
    }
    raw = (
        sst_component * weights["sst"]
        + front_component * weights["front"]
        + current_component * weights["current"]
        + bathy_component * weights["bathy"]
        + structure_component * weights["structure"]
        + fad_component * weights["fad"]
        + shelf_canyon_component * weights["shelf_canyon"]
        + season_component * weights["season"]
        + chlorophyll_component * weights["chlorophyll"]
        + eddy_component * weights["eddy"]
    )
    score = round(clamp(raw - (6 if data_confidence == "mock" else 0)), 1)
    strongest = sorted(components.items(), key=lambda item: item[1], reverse=True)[:4]
    weak = sorted(components.items(), key=lambda item: item[1])[:2]
    explanation: List[str] = [
        f"SST is {sst:.1f} C, giving a {sst_component:.0f}/100 species suitability component.",
        f"The synthetic front/gradient score is {front_component:.0f}/100.",
        f"Structure/depth context is {poi_type} in {depth_class} water.",
        "Confidence is limited because this v0.1 demo uses synthetic ocean data.",
    ]
    if weak[0][1] < 45:
        explanation.append(f"Limiting factor: {weak[0][0]} is weak in this demo scenario.")
    return {
        "score": score,
        "rating": rating_for(score),
        "confidence": "Low" if data_confidence == "mock" else "Medium",
        "components": components,
        "key_drivers": [name for name, _ in strongest],
        "explanation": explanation,
        "suggested_strategy": STRATEGIES.get(profile["species_id"], "Use the score as broad habitat decision support only."),
        "caution_notes": [
            "Demo coordinates are approximate and not verified fishing marks.",
            "This is not navigation, marine safety, legal, or catch guarantee advice.",
        ],
    }
