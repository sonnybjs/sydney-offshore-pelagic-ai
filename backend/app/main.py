from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health, hotspots, layers, ocean, pois, prediction_files, predictions, species
from app.core.config import PROJECT_NAME, VERSION

app = FastAPI(title=PROJECT_NAME, version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(species.router, prefix="/api")
app.include_router(ocean.router, prefix="/api")
app.include_router(layers.router, prefix="/api")
app.include_router(pois.router, prefix="/api")
app.include_router(hotspots.router, prefix="/api")
app.include_router(predictions.router, prefix="/api")
app.include_router(prediction_files.router, prefix="/api")
