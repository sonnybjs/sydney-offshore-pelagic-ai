import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.ocean_mock_service import mock_current_vectors


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "app" / "data" / "mock_current_vectors.geojson"
    out.write_text(json.dumps(mock_current_vectors(), indent=2))
    print(f"Wrote {out}")
