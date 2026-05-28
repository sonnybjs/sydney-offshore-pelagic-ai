import json
from importlib import resources

from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get("/predictions/real/{species_id}")
def real_prediction(species_id: str, date: str | None = Query(default=None)) -> dict:
    data_root = resources.files("app.data")
    prediction_dir = data_root.joinpath("real_predictions")
    if not prediction_dir.is_dir():
        return {
            "status": "not_available",
            "message": "No precomputed real prediction files are available yet. Run pipelines/14_predict_sydney_heatmap.py and 15_export_backend_prediction_files.py.",
        }
    candidates = [item for item in prediction_dir.iterdir() if item.name.endswith(f"_{species_id}_sydney_heatmap.geojson")]
    if date:
        candidates = [item for item in candidates if item.name.startswith(f"{date}_")]
    if not candidates:
        return {
            "status": "not_available",
            "species_id": species_id,
            "date": date,
            "message": "No precomputed GeoJSON found for this species/date.",
        }
    selected = sorted(candidates, key=lambda item: item.name)[-1]
    try:
        return json.loads(selected.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"Prediction file is not valid JSON: {selected.name}") from exc
