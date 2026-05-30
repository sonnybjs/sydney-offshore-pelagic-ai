"use client";

import { useMemo, useState } from "react";
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
  const [query, setQuery] = useState("");

  const rows = useMemo(() => {
    const all = (geojson?.features || [])
      .map((feature, index) => ({ feature, index }))
      .sort((a, b) => b.feature.properties.score - a.feature.properties.score)
      .slice(0, 30);
    const q = query.trim().toLowerCase();
    if (!q) return all;
    return all.filter(({ feature }) => {
      const p = feature.properties;
      return (
        p.rating?.toLowerCase().includes(q) ||
        p.coast_priority_band?.toLowerCase().includes(q) ||
        p.nearest_poi?.name?.toLowerCase().includes(q) ||
        p.common_name?.toLowerCase().includes(q)
      );
    });
  }, [geojson, query]);

  return (
    <section className="panel">
      <div className="panelHeading">
        <h2>Recommended Spots</h2>
        <span className="panelBadge">{rows.length}</span>
      </div>
      <div className="searchWrap">
        <span className="searchIcon">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" />
            <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </span>
        <input
          type="search"
          value={query}
          placeholder="Search spots, rating, zone…"
          onChange={(e) => setQuery(e.target.value)}
        />
        {query && (
          <button className="searchClear" onClick={() => setQuery("")} aria-label="Clear">&times;</button>
        )}
      </div>
      <div className="predictionList">
        {rows.length === 0 && query && <p>No spots match &ldquo;{query}&rdquo;.</p>}
        {rows.length === 0 && !query && <p>No recommended hotspot candidates available for this species/mode.</p>}
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
