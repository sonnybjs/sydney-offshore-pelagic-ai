import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.ocean_mock_service import mock_fronts


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "app" / "data" / "mock_sst_fronts.geojson"
    out.write_text(json.dumps(mock_fronts(), indent=2))
    print(f"Wrote {out}")
