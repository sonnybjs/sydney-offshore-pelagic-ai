import json
from functools import lru_cache
from importlib import resources


@lru_cache
def load_species_profiles() -> list[dict]:
    text = resources.files("app.data").joinpath("species_profiles.json").read_text()
    return json.loads(text)


def get_species_profile(species_id: str) -> dict:
    for profile in load_species_profiles():
        if profile["species_id"] == species_id:
            return profile
    raise KeyError(f"Unknown species_id: {species_id}")

