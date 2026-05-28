from __future__ import annotations

import pandas as pd

from model_audit_lib import BACKGROUND_AUDIT, TARGET_SPECIES, TRAINING_AUDIT, ensure_audit_dirs, load_training, min_depth_for, offshore_mask
from pipeline_lib import save_dataframe, write_json


STRATEGIES = [
    "random_ocean_background",
    "offshore_constrained_background",
    "target_group_background",
    "environment_stratified_background",
    "spatial_buffered_background",
]
RATIOS = [3, 5, 10]


def sample_ratio(presence: pd.DataFrame, background: pd.DataFrame, ratio: int, seed: int) -> pd.DataFrame:
    n = min(len(background), len(presence) * ratio)
    if n <= 0:
        return background.head(0).copy()
    return background.sample(n=n, random_state=seed, replace=len(background) < n)


def other_species_presence(species_id: str) -> pd.DataFrame:
    rows = []
    for other in TARGET_SPECIES:
        if other == species_id:
            continue
        df = load_training(other)
        if not df.empty and "label" in df.columns:
            rows.append(df[df["label"].astype(int) == 1].copy())
    if not rows:
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True, sort=False)
    out["label"] = 0
    out["sample_type"] = "background"
    out["background_strategy"] = "target_group_background"
    out["source"] = "other_target_species_presence_as_effort_proxy"
    return out


def make_strategy(species_id: str, data: pd.DataFrame, strategy: str) -> pd.DataFrame:
    presence = data[data["label"].astype(int) == 1].copy()
    background = data[data["label"].astype(int) == 0].copy()
    if strategy == "random_ocean_background":
        out = background
    elif strategy == "offshore_constrained_background":
        out = background[offshore_mask(background, species_id, "training")].copy()
    elif strategy == "target_group_background":
        effort = other_species_presence(species_id)
        out = effort[offshore_mask(effort, species_id, "training")].copy() if not effort.empty else background[offshore_mask(background, species_id, "training")].copy()
    elif strategy == "environment_stratified_background":
        if "depth_m" in background.columns and "distance_to_shelf_break" in background.columns:
            b = background.copy()
            b["depth_bin_tmp"] = pd.cut(pd.to_numeric(b["depth_m"], errors="coerce"), [-1, 50, 100, 200, 500, 1000, 5000], labels=False)
            b["shelf_bin_tmp"] = pd.cut(pd.to_numeric(b["distance_to_shelf_break"], errors="coerce"), [-1, 5, 20, 50, 100, 200, 10000], labels=False)
            parts = []
            target_per_bin = max(1, len(presence) // max(1, b[["depth_bin_tmp", "shelf_bin_tmp"]].drop_duplicates().shape[0]))
            for _, group in b.groupby(["depth_bin_tmp", "shelf_bin_tmp"], dropna=False):
                parts.append(group.sample(n=min(len(group), target_per_bin), random_state=42))
            out = pd.concat(parts, ignore_index=True, sort=False) if parts else b.head(0)
            out = out.drop(columns=[c for c in ["depth_bin_tmp", "shelf_bin_tmp"] if c in out.columns])
        else:
            out = background
    elif strategy == "spatial_buffered_background":
        out = background.copy()
        if {"grid_lat", "grid_lon"}.issubset(out.columns) and {"grid_lat", "grid_lon"}.issubset(presence.columns):
            presence_cells = set(zip(presence["date"].astype(str), presence["grid_lat"].round(2), presence["grid_lon"].round(2)))
            keep = [
                (str(row.date), round(float(row.grid_lat), 2), round(float(row.grid_lon), 2)) not in presence_cells
                for row in out.itertuples()
            ]
            out = out[keep].copy()
    else:
        out = background
    out = out.copy()
    out["label"] = 0
    out["sample_type"] = "background"
    out["background_strategy"] = strategy
    return out


def build_species(species_id: str) -> dict:
    data = load_training(species_id)
    if data.empty or "label" not in data.columns:
        return {"species_id": species_id, "status": "skipped_missing_training"}
    data = data.copy()
    data["label"] = data["label"].astype(int)
    presence = data[data["label"] == 1].copy()
    if presence.empty:
        return {"species_id": species_id, "status": "skipped_no_presence"}
    outputs = []
    for strategy in STRATEGIES:
        background = make_strategy(species_id, data, strategy)
        save_dataframe(background, BACKGROUND_AUDIT / f"{species_id}_{strategy}_background.csv", BACKGROUND_AUDIT / f"{species_id}_{strategy}_background.parquet")
        for ratio in RATIOS:
            sampled = sample_ratio(presence, background, ratio, seed=100 + ratio)
            combined = pd.concat([presence, sampled], ignore_index=True, sort=False)
            combined["audit_background_strategy"] = strategy
            combined["audit_background_ratio"] = ratio
            out = TRAINING_AUDIT / f"{species_id}_{strategy}_ratio{ratio}_training_samples.csv"
            save_dataframe(combined, out, out.with_suffix(".parquet"))
            outputs.append({"strategy": strategy, "ratio": ratio, "presence": int(len(presence)), "background": int(len(sampled)), "samples": int(len(combined))})
    return {"species_id": species_id, "status": "written", "outputs": outputs}


def main() -> None:
    ensure_audit_dirs()
    summary = {species_id: build_species(species_id) for species_id in TARGET_SPECIES}
    write_json(TRAINING_AUDIT / "background_strategy_summary.json", summary)
    print(summary)


if __name__ == "__main__":
    main()
