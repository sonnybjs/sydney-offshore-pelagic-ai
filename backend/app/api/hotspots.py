from fastapi import APIRouter, HTTPException, Query

from app.services.hotspot_service import all_hotspots, hotspots_for_species

router = APIRouter()


@router.get("/hotspots")
def hotspots(
    species_id: str | None = None,
    mode: str = "today",
    min_score: float | None = Query(default=None, ge=0, le=100),
) -> dict:
    return all_hotspots(species_id=species_id, min_score=min_score)


@router.get("/hotspots/{species_id}")
def hotspots_by_species(species_id: str, min_score: float | None = Query(default=None, ge=0, le=100)) -> dict:
    try:
        return hotspots_for_species(species_id, min_score=min_score)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

