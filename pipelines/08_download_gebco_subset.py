from __future__ import annotations

from pathlib import Path
from urllib.request import Request, urlopen

from pipeline_lib import cfg, ensure_dirs, file_size_mb, write_json


OUT = cfg.DATA / "raw" / "bathymetry" / "gebco" / "gebco_nsw_subset.nc"
STATUS = cfg.DATA / "interim" / "env_raw_index" / "gebco_auto_download_status.json"
MAX_BYTES = 1_000_000_000


def candidate_urls() -> list[str]:
    bbox = cfg.TRAIN_BBOX
    # The 2026 GEBCO app is JavaScript-driven and its private API may change.
    # This candidate list is intentionally conservative: it only targets known
    # public subset-style endpoints and never the global NetCDF ZIP.
    return [
        (
            "https://download.gebco.net/api/download?"
            f"north={bbox['north_lat']}&south={bbox['south_lat']}&"
            f"east={bbox['east_lon']}&west={bbox['west_lon']}&format=netcdf&grid=gebco"
        ),
        (
            "https://download.gebco.net/api/v1/download?"
            f"north={bbox['north_lat']}&south={bbox['south_lat']}&"
            f"east={bbox['east_lon']}&west={bbox['west_lon']}&format=netcdf&grid=gebco"
        ),
    ]


def try_download(url: str) -> dict:
    request = Request(url, headers={"User-Agent": "Sydney-Offshore-Pelagic-AI-Map/0.2 audit"})
    with urlopen(request, timeout=60) as response:
        content_type = response.headers.get("content-type", "")
        length = int(response.headers.get("content-length") or 0)
        if length and length > MAX_BYTES:
            return {"status": "skipped_too_large", "url": url, "content_length": length}
        first = response.read(512)
        if b"<!DOCTYPE html" in first[:80] or b"<html" in first[:120] or "text/html" in content_type:
            return {"status": "not_netcdf_response", "url": url, "content_type": content_type}
        OUT.parent.mkdir(parents=True, exist_ok=True)
        with OUT.open("wb") as handle:
            handle.write(first)
            total = len(first)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_BYTES:
                    handle.close()
                    OUT.unlink(missing_ok=True)
                    return {"status": "aborted_too_large", "url": url, "bytes": total}
                handle.write(chunk)
    return {"status": "downloaded", "url": url, "file": str(OUT.relative_to(cfg.ROOT)), "size_mb": file_size_mb(OUT)}


def main() -> None:
    ensure_dirs()
    print("GEBCO automatic subset download attempt")
    print({"bbox": cfg.TRAIN_BBOX, "output": str(OUT.relative_to(cfg.ROOT)), "max_bytes": MAX_BYTES})
    attempts = []
    if OUT.exists():
        summary = {"status": "already_exists", "file": str(OUT.relative_to(cfg.ROOT)), "size_mb": file_size_mb(OUT)}
        write_json(STATUS, summary)
        print(summary)
        return
    for url in candidate_urls():
        try:
            result = try_download(url)
        except Exception as exc:
            result = {"status": "failed", "url": url, "error": f"{type(exc).__name__}: {exc}"}
        attempts.append(result)
        print(result)
        if result.get("status") == "downloaded":
            break
    summary = {
        "status": "downloaded" if OUT.exists() else "not_available_via_known_public_api",
        "attempts": attempts,
        "message": "GEBCO supports user-defined-area downloads and OPeNDAP, but the current app API is JavaScript-driven and may change. This script never downloads the global grid.",
    }
    write_json(STATUS, summary)


if __name__ == "__main__":
    main()
