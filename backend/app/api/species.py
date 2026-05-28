from fastapi import APIRouter

from app.scoring.species_profiles import load_species_profiles

router = APIRouter()


@router.get("/species")
def species() -> list[dict]:
    return load_species_profiles()

