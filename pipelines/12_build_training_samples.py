from __future__ import annotations

from pipeline_lib import append_provenance, cfg, ensure_dirs, read_table, save_dataframe, write_json
from training_prep_lib import TARGET_SPECIES


def assign_splits(df):
    import pandas as pd
    from sklearn.model_selection import train_test_split

    data = df.copy()
    data["split"] = "train"
    data.loc[(data["date"] >= "2021-01-01") & (data["date"] <= "2022-12-31"), "split"] = "validation"
    data.loc[data["date"] >= "2023-01-01", "split"] = "test"
    counts = data.groupby(["split", "label"]).size().unstack(fill_value=0)
    if {"train", "validation", "test"}.issubset(set(data["split"])) and (counts.min(axis=1) > 0).all():
        data["split_strategy"] = "time_split"
        return data
    if data["label"].nunique() < 2 or len(data) < 10:
        data["split"] = "train"
        data["split_strategy"] = "insufficient_for_split"
        return data
    if data["label"].value_counts().min() < 2:
        data["split"] = "train"
        data["split_strategy"] = "insufficient_for_stratified_split"
        return data
    train, holdout = train_test_split(data, test_size=0.3, stratify=data["label"], random_state=42)
    if holdout["label"].nunique() == 2 and len(holdout) >= 6 and holdout["label"].value_counts().min() >= 2:
        validation, test = train_test_split(holdout, test_size=0.5, stratify=holdout["label"], random_state=42)
    else:
        validation, test = holdout, holdout.iloc[0:0]
    train = train.copy(); train["split"] = "train"
    validation = validation.copy(); validation["split"] = "validation"
    test = test.copy(); test["split"] = "test"
    out = pd.concat([train, validation, test], ignore_index=True, sort=False)
    out["split_strategy"] = "stratified_random_low_data"
    return out


def build_species(species_id: str) -> dict:
    import pandas as pd

    presence_path = cfg.DATA / "interim" / "matched_presence" / f"{species_id}_presence.csv"
    background_path = cfg.DATA / "interim" / "background_samples" / f"{species_id}_background.csv"
    if not presence_path.exists() or not background_path.exists():
        return {"status": "missing_presence_or_background", "samples": 0}
    presence = read_table(presence_path)
    background = read_table(background_path)
    if presence.empty or background.empty:
        empty = pd.DataFrame(
            columns=[
                "species_id",
                "date",
                "year",
                "month",
                "day_of_year",
                "grid_lat",
                "grid_lon",
                "grid_id",
                "label",
                "sample_type",
            ]
        )
        outputs = save_dataframe(
            empty,
            cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.csv",
            cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.parquet",
        )
        return {
            "status": "empty_presence_or_background",
            "presence": int(len(presence)),
            "background": int(len(background)),
            "samples": 0,
            "outputs": outputs,
            "note": "Training samples were not created because required date-aligned presence/background data is unavailable.",
        }
    data = pd.concat([presence, background], ignore_index=True, sort=False)
    for col, value in {
        "occurrence_lat": float("nan"),
        "occurrence_lon": float("nan"),
        "match_distance_km": float("nan"),
        "source": "background",
        "source_quality": "background",
        "occurrence_id": "",
        "dataset_name": "",
    }.items():
        if col not in data.columns:
            data[col] = value
    data = assign_splits(data)
    outputs = save_dataframe(
        data,
        cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.csv",
        cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.parquet",
    )
    append_provenance(
        {
            "dataset_name": f"{species_id}_training_samples",
            "source_name": "Presence/background training dataset",
            "source_url_or_access_method": "Matched presence + same-date background samples",
            "spatial_bbox": cfg.TRAIN_BBOX,
            "time_range": f"{data['date'].min()} to {data['date'].max()}",
            "variables": ",".join(data.columns),
            "raw_file_path": f"{presence_path.relative_to(cfg.ROOT)}; {background_path.relative_to(cfg.ROOT)}",
            "processed_file_path": outputs.get("csv", ""),
            "estimated_size_mb": "<1000",
            "actual_size_mb": outputs.get("csv_size_mb", ""),
            "license_or_terms_note": "Derived table; occurrence licenses retained per row where available",
            "used_for_training": True,
            "notes": "Prepared only; no model training performed.",
        }
    )
    return {"status": "written", "presence": int(len(presence)), "background": int(len(background)), "samples": int(len(data)), "outputs": outputs}


def main() -> None:
    import pandas as pd

    ensure_dirs()
    summary = {}
    combined = []
    for species_id in TARGET_SPECIES:
        summary[species_id] = build_species(species_id)
        print(species_id, summary[species_id])
        out_path = cfg.DATA / "processed" / "training" / f"{species_id}_training_samples.csv"
        if out_path.exists():
            frame = read_table(out_path)
            if not frame.empty:
                combined.append(frame)
    if combined:
        all_df = pd.concat(combined, ignore_index=True, sort=False)
        summary["all_species"] = save_dataframe(
            all_df,
            cfg.DATA / "processed" / "training" / "all_species_training_samples.csv",
            cfg.DATA / "processed" / "training" / "all_species_training_samples.parquet",
        )
    write_json(cfg.DATA / "processed" / "reports" / "training_samples_build_summary.json", summary)


if __name__ == "__main__":
    main()
