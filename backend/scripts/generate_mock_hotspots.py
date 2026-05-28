import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.services.hotspot_service import all_hotspots


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "app" / "data" / "mock_hotspot_zones.geojson"
    out.write_text(json.dumps(all_hotspots(), indent=2))
    print(f"Wrote {out}")
