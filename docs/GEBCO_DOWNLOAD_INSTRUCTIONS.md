# GEBCO Subset Download Instructions

Do not download the global GEBCO grid for this project audit.

Download only the NSW / East Coast corridor subset:

- Source: GEBCO gridded bathymetry download app
- Product: latest GEBCO grid available, preferably GEBCO 2024 or newer
- Format: NetCDF
- BBox: S -39.0, N -27.0, W 148.5, E 158.5
- Save path: `data/raw/bathymetry/gebco/gebco_nsw_subset.nc`

Required bounds:

- south_lat = -39.0
- north_lat = -27.0
- west_lon = 148.5
- east_lon = 158.5

After placing the file, rerun:

```bash
python pipelines/08_prepare_gebco_bathymetry.py
```

The audit script will crop to TRAIN_BBOX, downsample to 0.05 degrees, and derive `depth_m`, `slope`, and `ocean_mask`.
