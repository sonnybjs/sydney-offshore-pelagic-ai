from fastapi import APIRouter

from app.core.config import PROJECT_NAME, VERSION

router = APIRouter()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "project": PROJECT_NAME, "version": VERSION}

