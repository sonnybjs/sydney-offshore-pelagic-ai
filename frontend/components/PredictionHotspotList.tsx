"use client";

import { useMemo, useState } from "react";
import type { FeatureCollection, PredictionProperties } from "../lib/types";

const cn = (...args: (string | boolean | undefined)[]) => args.filter(Boolean).join(" ");

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M10.5 10.5L14 14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    </svg>
  );
}

export function PredictionHotspotList({ geojson, selectedIndex, onSelect }: {
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
    <section className="bg-[var(--panel-glass)] border border-[var(--line)] rounded-panel p-4 shadow-panel">
      <div className="flex items-center justify-between gap-2.5 mb-3">
        <h2 className="m-0 text-[15px] uppercase text-[var(--heading)] font-bold tracking-[0] whitespace-nowrap">Recommended Spots</h2>
        <span className="text-[11px] text-[var(--muted)] border border-[var(--line)] rounded-full px-2 py-0.5 font-mono">{rows.length}</span>
      </div>
      <div className="search-wrap relative flex items-center mb-2.5">
        <span className="absolute left-2.5 text-[var(--muted)] flex pointer-events-none"><SearchIcon /></span>
        <input
          type="search" value={query} placeholder="Search spots, rating, zone…"
          className="w-full py-[9px] pl-[30px] pr-7 border border-[var(--line)] rounded-btn bg-[var(--btn-bg)] text-[var(--text)] text-[13px] outline-none appearance-none placeholder:text-[var(--muted)] focus:border-[var(--accent)]"
          onChange={(e) => setQuery(e.target.value)}
        />
        {query && (
          <button className="absolute right-1.5 border-0 bg-transparent text-[var(--muted)] text-[18px] leading-none cursor-pointer px-1.5 py-0.5 rounded-[5px] hover:text-[var(--text)]" onClick={() => setQuery("")} aria-label="Clear">&times;</button>
        )}
      </div>
      <div className="spot-list grid gap-[9px] max-h-[46vh] overflow-auto pr-1">
        {rows.length === 0 && query && <p className="text-[var(--muted)] text-[13px] mx-0.5 my-1">No spots match &ldquo;{query}&rdquo;.</p>}
        {rows.length === 0 && !query && <p className="text-[var(--muted)] text-[13px] mx-0.5 my-1">No recommended hotspot candidates available.</p>}
        {rows.map(({ feature, index }, rank) => {
          const [lon, lat] = feature.geometry.coordinates as number[];
          const radius = (feature.properties as any).recommendation_radius_m;
          return (
            <button key={`${feature.properties.species_id}-${index}`}
              className={cn(
                "grid [grid-template-columns:1fr_auto] gap-y-1 gap-x-2.5 w-full px-[11px] py-2.5 border rounded-btn cursor-pointer text-left",
                selectedIndex === index ? "border-[var(--accent)] bg-[var(--card-selected)]" : "border-[rgba(103,212,255,0.2)] bg-[var(--btn-bg)]"
              )}
              onClick={() => onSelect(index)}>
              <span className="text-[var(--muted)] text-xs">#{feature.properties.spot_rank || rank + 1} {feature.properties.rating}</span>
              <strong className="[grid-row:span_2] self-center font-mono text-[var(--text)]">{feature.properties.score.toFixed(2)} / 100</strong>
              <small className="text-[var(--muted)] text-xs font-mono">{lat.toFixed(3)}, {lon.toFixed(3)}</small>
              {radius && <small className="text-[var(--muted)] text-xs col-span-2">{radius} m radius</small>}
              {feature.properties.coast_priority_band && <small className="text-[var(--muted)] text-xs col-span-2">{feature.properties.coast_priority_band}</small>}
              {feature.properties.nearest_poi?.name && <small className="text-[var(--muted)] text-xs col-span-2">Near {feature.properties.nearest_poi.name}</small>}
            </button>
          );
        })}
      </div>
    </section>
  );
}
