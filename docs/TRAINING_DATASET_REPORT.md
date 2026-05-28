# Training Dataset Report

This report validates training-ready presence/background samples. No model training is performed.

Occurrence labels are presence-only public records. Background samples are pseudo-absence / available ocean environment, not true absence. Outputs should support relative habitat suitability / hotspot scoring, not exact fish locations or true catch probability.

Dynamic features must be aligned to occurrence dates. SST is required for v1. Bathymetry and structure are static. Physics and chlorophyll are optional and remain NaN when unavailable.

## Species Summary

| Species | Status | Total | Presence | Background | Dates | Date Range |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| yellowfin_tuna | rule_based_only_insufficient_occurrence | 44 | 4 | 40 | 4 | 2010-06-20 to 2025-09-21 |
| mahi_mahi | trainable_low_confidence | 3179 | 289 | 2890 | 227 | 2005-03-01 to 2025-01-03 |
| striped_marlin | rule_based_only_insufficient_occurrence | 11 | 1 | 10 | 1 | 2004-03-06 to 2004-03-06 |
| southern_bluefin_tuna | trainable_low_confidence | 1826 | 166 | 1660 | 145 | 2010-11-07 to 2015-10-01 |
| yellowtail_kingfish | trainable_low_confidence | 2156 | 196 | 1960 | 187 | 2015-01-22 to 2025-12-22 |

## Missing Data Notes

- If a species has no training samples, the required date-aligned SST feature grid was unavailable for its occurrence dates.
- Optional physics/chlorophyll missingness does not block v1 samples.
- If GEBCO is missing, bathymetry features remain unavailable and confidence should be lower.

## Recommended Model Training Sequence

1. First train only species with status `trainable_sst_bathy_only` or `trainable_low_confidence`.
2. Keep rule-based scoring for species marked `rule_based_only_insufficient_occurrence`.
3. Add verified MUR SST subsets before expanding model training.