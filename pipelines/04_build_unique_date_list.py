from pipeline_lib import cfg, ensure_dirs, save_dataframe, write_json


def main() -> None:
    import pandas as pd

    ensure_dirs()
    selected = []
    per_species = {}
    before_sampling = 0
    for species_id in cfg.SPECIES_CONFIG:
        path = cfg.DATA / "interim" / "occurrence_clean" / f"{species_id}_clean.csv"
        if not path.exists():
            continue
        try:
            df = pd.read_csv(path)
        except pd.errors.EmptyDataError:
            per_species[species_id] = 0
            continue
        if df.empty:
            per_species[species_id] = 0
            continue
        first = df[(df["date"] >= cfg.START_DATE_FIRST_RUN) & (df["date"] <= cfg.END_DATE_FIRST_RUN)]
        use = first
        dates = sorted(use["date"].unique().tolist())
        per_species[species_id] = len(dates)
        before_sampling += len(dates)
        for d in dates:
            selected.append({"species_id": species_id, "date": d, "year": int(d[:4]), "month": int(d[5:7])})
    dates_df = pd.DataFrame(selected, columns=["species_id", "date", "year", "month"]).drop_duplicates()
    if len(dates_df) > cfg.MAX_UNIQUE_TRAIN_DATES_FIRST_RUN:
        dates_df = (
            dates_df.groupby(["species_id", "year", "month"], group_keys=False)
            .apply(lambda x: x.sample(min(len(x), max(1, cfg.MAX_UNIQUE_TRAIN_DATES_FIRST_RUN // 180)), random_state=42))
            .head(cfg.MAX_UNIQUE_TRAIN_DATES_FIRST_RUN)
            .reset_index(drop=True)
        )
    outputs = save_dataframe(dates_df, cfg.DATA / "interim" / "date_lists" / "unique_training_dates.csv")
    summary = {
        "total_unique_dates_before_sampling": int(before_sampling),
        "total_rows_after_sampling": int(len(dates_df)),
        "date_min": None if dates_df.empty else str(dates_df["date"].min()),
        "date_max": None if dates_df.empty else str(dates_df["date"].max()),
        "per_species_candidate_dates": per_species,
        "dates_per_year": {} if dates_df.empty else {str(k): int(v) for k, v in dates_df.groupby("year").size().to_dict().items()},
        "outputs": outputs,
    }
    write_json(cfg.DATA / "interim" / "date_lists" / "unique_training_dates_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
