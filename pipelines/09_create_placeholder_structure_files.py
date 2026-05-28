from pipeline_lib import cfg, ensure_dirs, write_json


def feature(point_id: str, name: str, lat: float, lon: float, poi_type: str, notes: str) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "id": point_id,
            "name": name,
            "latitude": lat,
            "longitude": lon,
            "poi_type": poi_type,
            "source": "manual_demo_placeholder",
            "source_date": "audit_placeholder",
            "demo_only": True,
            "verified": False,
            "notes": notes,
        },
    }


def main() -> None:
    ensure_dirs()
    note = "Approximate demo-only point. Do not use as verified fishing mark."
    fad_features = [
        feature("fad_demo_north", "FAD-style demo point north", -33.15, 152.1, "fad_demo", note),
        feature("fad_demo_central", "FAD-style demo point central", -34.05, 152.15, "fad_demo", note),
        feature("fad_demo_south", "FAD-style demo point south", -34.75, 151.95, "fad_demo", note),
    ]
    poi_features = [
        feature("browns_mountain_demo", "Browns Mountain approximate demo point", -34.05, 151.8, "offshore_bank", note),
        feature("sydney_shelf_edge_demo", "Sydney shelf edge demo point", -33.95, 152.1, "shelf_break", note),
        feature("botany_offshore_demo", "Botany offshore demo point", -34.1, 151.55, "current_edge", note),
        feature("port_hacking_offshore_demo", "Port Hacking offshore demo point", -34.2, 151.45, "current_edge", note),
    ]
    fad_path = cfg.DATA / "raw" / "structure" / "fad" / "fad_points_demo.geojson"
    poi_path = cfg.DATA / "raw" / "structure" / "poi" / "offshore_poi_demo.geojson"
    write_json(fad_path, {"type": "FeatureCollection", "features": fad_features})
    write_json(poi_path, {"type": "FeatureCollection", "features": poi_features})
    summary = {
        "status": "written",
        "fad_points": len(fad_features),
        "poi_points": len(poi_features),
        "files": [str(fad_path.relative_to(cfg.ROOT)), str(poi_path.relative_to(cfg.ROOT))],
        "demo_only": True,
        "verified": False,
    }
    write_json(cfg.DATA / "interim" / "env_raw_index" / "structure_placeholder_status.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
