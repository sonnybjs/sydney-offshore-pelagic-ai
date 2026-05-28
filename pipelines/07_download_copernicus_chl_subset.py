from pipeline_lib import cfg, ensure_dirs, write_json


def main() -> None:
    ensure_dirs()
    note = {
        "status": "skipped_missing_copernicus_setup",
        "product": "OCEANCOLOUR_GLO_BGC_L3_MY_009_103",
        "variables": ["CHL", "CHL_gradient_optional"],
        "bbox": cfg.TRAIN_BBOX,
        "reason": "Copernicus Marine Ocean Colour subset download requires a selected access method and may need credentials. Pipeline records missing CHL flags.",
    }
    write_json(cfg.DATA / "interim" / "env_raw_index" / "copernicus_chl_status.json", note)
    print(note)


if __name__ == "__main__":
    main()
