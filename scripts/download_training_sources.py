import csv
import json
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"

SOURCES = {
    "nsw_dpi_fads": {
        "url": "https://www.dpi.nsw.gov.au/fishing/recreational/resources/fish-aggregating-devices",
        "description": "NSW DPI Fish Aggregating Devices public page; useful for future FAD proximity features.",
    },
    "nasa_mur_cmr": {
        "url": "https://cmr.earthdata.nasa.gov/search/collections.json?short_name=MUR-JPL-L4-GLOB-v4.1",
        "description": "NASA Earthdata CMR metadata for MUR SST. Granule downloads may require Earthdata workflow.",
    },
    "gebco_downloads": {
        "url": "https://download.gebco.net/downloads",
        "description": "GEBCO gridded bathymetry download entrypoint; full grids are large.",
    },
    "aodn_portal": {
        "url": "https://portal.aodn.org.au/",
        "description": "AODN portal entrypoint for IMOS/AODN ocean data discovery.",
    },
}

NSW_DPI_FAD_FALLBACK_ROWS = [
    ("Tweed Heads", "28° 09.730'", "153° 41.000'", "64"),
    ("Byron Bay", "28° 36.723'", "153° 42.758'", "70"),
    ("Ballina", "28° 54.430'", "153° 41.189'", "70"),
    ("Evans Head", "29° 06.400'", "153° 36.200'", "50"),
    ("Yamba", "29° 37.268'", "153° 29.153'", "70"),
    ("Wooli", "29° 52.703'", "153° 26.117'", "65"),
    ("Coffs Harbour", "30° 14.858'", "153° 21.605'", "85"),
    ("Nambucca", "30° 39.622'", "153° 08.934'", "60"),
    ("South West Rocks", "30° 50.534'", "153° 11.803'", "104"),
    ("Hat Head", "31° 00.636'", "153° 07.795'", "85"),
    ("Port Macquarie", "31° 26.439'", "153° 04.342'", "90"),
    ("Laurieton", "31° 39.601'", "152° 56.235'", "65"),
    ("Crowdy Head", "31° 47.000'", "152° 55.200'", "79"),
    ("Forster", "32° 13.211'", "152° 40.680'", "80"),
    ("Trial Bay bait collection marker buoy", "30° 52.760'", "153° 03.110'", "10"),
]


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tr":
            self.current_row = []
        if tag in {"td", "th"} and self.current_row is not None:
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            text = " ".join(data.split())
            if text:
                self.current_cell.append(text)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self.current_cell is not None and self.current_row is not None:
            self.current_row.append(" ".join(self.current_cell).strip())
            self.current_cell = None
        if tag == "tr" and self.current_row is not None:
            if any(self.current_row):
                self.rows.append(self.current_row)
            self.current_row = None


def fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "Sydney-Offshore-Pelagic-AI-Map/0.1 local research demo"})
    with urlopen(request, timeout=45) as response:
        return response.read()


def dms_to_decimal(value: str, hemisphere: str) -> float:
    match = re.search(r"(\d{1,3})\D+(\d{1,2}(?:\.\d+)?)", value)
    if not match:
        raise ValueError(f"Could not parse coordinate: {value}")
    degrees = float(match.group(1))
    minutes = float(match.group(2))
    decimal = degrees + minutes / 60.0
    return -decimal if hemisphere.upper() in {"S", "W"} else decimal


def parse_fads(html: str) -> list[dict]:
    parser = TableParser()
    parser.feed(html)
    fads: list[dict] = []
    for row in parser.rows:
        if len(row) >= 5 and re.search(r"\d{1,2}\D+\d{1,2}(?:\.\d+)?", row[1]) and re.search(r"\d{2,3}\D+\d{1,2}(?:\.\d+)?", row[2]):
            name = re.sub(r"^\(\d+[A-Z]?\)\s*", "", row[0]).strip()
            depth = row[4]
            fads.append(
                {
                    "id": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:80],
                    "name": name,
                    "latitude": round(dms_to_decimal(row[1], "S"), 6),
                    "longitude": round(dms_to_decimal(row[2], "E"), 6),
                    "source": "NSW DPI Fish Aggregating Devices public page",
                    "source_url": SOURCES["nsw_dpi_fads"]["url"],
                    "downloaded_at": datetime.now(timezone.utc).isoformat(),
                    "demo_use_note": f"Parsed from downloaded official NSW DPI HTML; depth_m={depth}. Verify current status with NSW DPI/FishSmart before operational use.",
                }
            )
            continue
        row_text = " | ".join(row)
        lat_match = re.search(r"(\d{1,2}\D+\d{1,2}(?:\.\d+)?)\s*[\"']?\s*S", row_text, re.I)
        lon_match = re.search(r"(\d{2,3}\D+\d{1,2}(?:\.\d+)?)\s*[\"']?\s*E", row_text, re.I)
        if not lat_match or not lon_match:
            continue
        name = next((cell for cell in row if re.search(r"FAD|Sydney|Wollongong|Port|Bay|Shoalhaven|Newcastle|Kiama", cell, re.I)), row[0])
        fads.append(
            {
                "id": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:80],
                "name": name,
                "latitude": round(dms_to_decimal(lat_match.group(1), "S"), 6),
                "longitude": round(dms_to_decimal(lon_match.group(1), "E"), 6),
                "source": "NSW DPI Fish Aggregating Devices public page",
                "source_url": SOURCES["nsw_dpi_fads"]["url"],
                "downloaded_at": datetime.now(timezone.utc).isoformat(),
                "demo_use_note": "Official public FAD table parsed for future feature engineering; verify current status with NSW DPI before operational use.",
            }
        )
    seen: set[tuple[float, float]] = set()
    unique = []
    for fad in fads:
        key = (fad["latitude"], fad["longitude"])
        if key not in seen:
            unique.append(fad)
            seen.add(key)
    return unique


def fallback_fads() -> list[dict]:
    downloaded_at = datetime.now(timezone.utc).isoformat()
    return [
        {
            "id": re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:80],
            "name": name,
            "latitude": round(dms_to_decimal(lat, "S"), 6),
            "longitude": round(dms_to_decimal(lon, "E"), 6),
            "source": "NSW DPI Fish Aggregating Devices public page",
            "source_url": SOURCES["nsw_dpi_fads"]["url"],
            "downloaded_at": downloaded_at,
            "demo_use_note": f"Fallback from official page text after command-line fetch was blocked; depth_m={depth}. Verify current status with NSW DPI/FishSmart before operational use.",
        }
        for name, lat, lon, depth in NSW_DPI_FAD_FALLBACK_ROWS
    ]


def write_fads(fads: list[dict]) -> None:
    processed_dir = PROCESSED / "nsw_dpi"
    processed_dir.mkdir(parents=True, exist_ok=True)
    csv_path = processed_dir / "fads.csv"
    geojson_path = processed_dir / "fads.geojson"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fads[0].keys()))
        writer.writeheader()
        writer.writerows(fads)
    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [fad["longitude"], fad["latitude"]]},
                "properties": {key: value for key, value in fad.items() if key not in {"latitude", "longitude"}},
            }
            for fad in fads
        ],
    }
    geojson_path.write_text(json.dumps(geojson, indent=2), encoding="utf-8")


def main() -> dict:
    RAW.mkdir(parents=True, exist_ok=True)
    (RAW / "source_metadata").mkdir(parents=True, exist_ok=True)
    manifest = {
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "sources": SOURCES,
        "outputs": [],
    }

    for key, source in SOURCES.items():
        try:
            body = fetch(source["url"])
            fetch_status = "downloaded"
        except (HTTPError, URLError, TimeoutError) as exc:
            fetch_status = f"failed: {type(exc).__name__}: {exc}"
            body = b""
        suffix = ".json" if key == "nasa_mur_cmr" else ".html"
        out = RAW / "source_metadata" / f"{key}{suffix}"
        out.write_bytes(body)
        manifest["outputs"].append(str(out.relative_to(ROOT)))
        manifest[f"{key}_status"] = fetch_status
        if key == "nsw_dpi_fads":
            fads = parse_fads(body.decode("utf-8", errors="ignore")) if body else fallback_fads()
            if not fads:
                fads = fallback_fads()
                manifest["nsw_dpi_fads_parse_note"] = "Downloaded body did not expose parseable coordinate rows; used official-page fallback rows."
            write_fads(fads)
            manifest["nsw_dpi_fad_count"] = len(fads)
            manifest["outputs"].extend(["data/processed/nsw_dpi/fads.csv", "data/processed/nsw_dpi/fads.geojson"])

    manifest_path = RAW / "source_metadata" / "download_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
