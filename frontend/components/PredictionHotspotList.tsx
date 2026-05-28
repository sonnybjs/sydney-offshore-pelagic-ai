import type { FeatureCollection, PredictionProperties } from "../lib/types";

export function PredictionHotspotList({
  geojson,
  selectedIndex,
  onSelect
}: {
  geojson: FeatureCollection<PredictionProperties> | null;
  selectedIndex: number | null;
  onSelect: (index: number) => void;
}) {
  const rows = (geojson?.features || [])
    .map((feature, index) => ({ feature, index }))
    .sort((a, b) => b.feature.properties.score - a.feature.properties.score)
    .slice(0, 30);
  return (
    <section className="panel">
      <h2>Recommended Spots</h2>
      <div className="predictionList">
        {rows.length === 0 && <p>No recommended hotspot candidates available for this species/mode.</p>}
        {rows.map(({ feature, index }, rank) => {
          const [lon, lat] = feature.geometry.coordinates as number[];
          const radius = (feature.properties as any).recommendation_radius_m;
          return (
            <button key={`${feature.properties.species_id}-${index}`} className={selectedIndex === index ? "predictionListItem selected" : "predictionListItem"} onClick={() => onSelect(index)}>
              <span>#{feature.properties.spot_rank || rank + 1} {feature.properties.rating}</span>
              <strong>{feature.properties.score.toFixed(2)} / 100</strong>
              <small>{lat.toFixed(3)}, {lon.toFixed(3)}</small>
              {radius && <small>{radius} m candidate radius</small>}
              {feature.properties.coast_priority_band && <small>{feature.properties.coast_priority_band}</small>}
              {feature.properties.nearest_poi?.name && <small>Near {feature.properties.nearest_poi.name}</small>}
            </button>
          );
        })}
      </div>
    </section>
  );
}
