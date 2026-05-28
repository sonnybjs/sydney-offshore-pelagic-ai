# Backend

FastAPI service for the Sydney Offshore Pelagic AI Map v0.1 demo.

## Run

```bash
cd sydney-offshore-pelagic-ai/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## Test

```bash
cd sydney-offshore-pelagic-ai/backend
source .venv/bin/activate
pytest
```

All v0.1 ocean layers, POIs and hotspots are synthetic demo data.
