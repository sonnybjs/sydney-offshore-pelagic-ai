# Sydney Data Scope

## Prediction BBOX

- south_lat: `-36.5`
- north_lat: `-32.0`
- west_lon: `150.5`
- east_lon: `154.5`

This covers Sydney offshore, Broken Bay offshore, Botany Bay offshore, Port Hacking offshore, Browns Mountain demo area, and the shelf/canyon area east of Sydney.

## Training BBOX

- south_lat: `-39.0`
- north_lat: `-27.0`
- west_lon: `148.5`
- east_lon: `158.5`

This covers NSW offshore plus southern Queensland/east coast context for East Australian Current influence. It intentionally excludes Western Australia and South Australia.

## Optional East-Only Extension

Only use if a species has too few occurrence records:

- south_lat: `-44.5`
- north_lat: `-25.0`
- west_lon: `145.0`
- east_lon: `160.5`

Still no Western Australia.

