import json
from functools import lru_cache
from importlib import resources


@lru_cache
def get_pois_geojson() -> dict:
    text = resources.files("app.data").joinpath("offshore_pois_seed.geojson").read_text()
    return json.loads(text)


def get_pois() -> list[dict]:
    pois = []
    for feature in get_pois_geojson()["features"]:
        lon, lat = feature["geometry"]["coordinates"]
        props = feature["properties"]
        pois.append({**props, "longitude": lon, "latitude": lat})
    return pois

