from fastapi import APIRouter

from app.services.layer_service import get_current_layer, get_front_layer, get_sst_layer

router = APIRouter()


@router.get("/layers/mock/sst")
def sst_layer() -> dict:
    return get_sst_layer()


@router.get("/layers/mock/currents")
def current_layer() -> dict:
    return get_current_layer()


@router.get("/layers/mock/fronts")
def front_layer() -> dict:
    return get_front_layer()

