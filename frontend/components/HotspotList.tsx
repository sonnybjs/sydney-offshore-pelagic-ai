import { HotspotCard } from "./HotspotCard";
import type { FeatureCollection, HotspotProperties } from "../lib/types";

export function HotspotList({ hotspots, selectedId, onSelect }: { hotspots: FeatureCollection<HotspotProperties>; selectedId?: string; onSelect: (id: string) => void }) {
  const sorted = [...hotspots.features].sort((a, b) => b.properties.score - a.properties.score);
  return (
    <section className="panel hotspotList">
      <h2>Top Habitat Scores</h2>
      <div className="cardsScroll">
        {sorted.slice(0, 8).map((feature) => (
          <HotspotCard key={feature.properties.id} hotspot={feature.properties} selected={feature.properties.id === selectedId} onSelect={() => onSelect(feature.properties.id)} />
        ))}
      </div>
    </section>
  );
}
