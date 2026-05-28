from fastapi import APIRouter

from app.services.ocean_mock_service import latest_ocean_summary

router = APIRouter()


@router.get("/ocean/mock/latest")
def latest_mock_ocean() -> dict:
    return latest_ocean_summary()

