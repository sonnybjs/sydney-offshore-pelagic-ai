from math import asin, cos, radians, sin, sqrt


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def range_score(value: float, preferred: list[float], extended: list[float]) -> float:
    low, high = preferred
    ext_low, ext_high = extended
    if low <= value <= high:
        return 100.0
    if value < low:
        if value <= ext_low:
            return 0.0
        return 100.0 * (value - ext_low) / (low - ext_low)
    if value >= ext_high:
        return 0.0
    return 100.0 * (ext_high - value) / (ext_high - high)


def rating_for(score: float) -> str:
    if score < 30:
        return "Low"
    if score < 55:
        return "Possible"
    if score < 75:
        return "Good"
    return "Prime"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * radius * asin(sqrt(a))

