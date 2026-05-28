from fastapi import APIRouter

from app.services.poi_service import get_pois

router = APIRouter()


@router.get("/pois")
def pois() -> list[dict]:
    return get_pois()

