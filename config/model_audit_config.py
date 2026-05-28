TARGET_AUDIT_SPECIES = ["yellowfin_tuna", "mahi_mahi", "striped_marlin"]

AUDIT_WARNING = "Model under audit: nearshore saturation detected. Do not use as real prediction."

MIN_DEPTH_DISPLAY_BY_SPECIES = {
    "yellowfin_tuna": 50.0,
    "mahi_mahi": 30.0,
    "striped_marlin": 100.0,
}

MIN_DEPTH_TRAINING_BY_SPECIES = {
    "yellowfin_tuna": 50.0,
    "mahi_mahi": 30.0,
    "striped_marlin": 100.0,
}

OFFSHORE_DISPLAY_MASK_ENABLED = True

BACKGROUND_STRATEGIES = [
    "random_ocean_background",
    "offshore_constrained_background",
    "target_group_background",
    "environment_stratified_background",
    "spatial_buffered_background",
]

BACKGROUND_RATIOS = [3, 5, 10]

SATURATION_PERCENT_GE_90_LIMIT = 20.0
CLIPPING_PERCENT_EQ_100_LIMIT = 5.0
