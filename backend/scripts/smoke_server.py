import threading
import time
from pathlib import Path
import sys

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.main import app


def main() -> None:
    config = uvicorn.Config(app, host="127.0.0.1", port=8011, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 8
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            health = httpx.get("http://127.0.0.1:8011/api/health", timeout=1)
            health.raise_for_status()
            for path in ["/api/species", "/api/ocean/mock/latest", "/api/hotspots"]:
                response = httpx.get(f"http://127.0.0.1:8011{path}", timeout=2)
                response.raise_for_status()
            print(health.json())
            break
        except Exception as exc:
            last_error = exc
            time.sleep(0.25)
    else:
        raise RuntimeError(f"Uvicorn smoke test failed: {last_error}")
    server.should_exit = True
    thread.join(timeout=3)


if __name__ == "__main__":
    main()
