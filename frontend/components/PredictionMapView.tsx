import { useEffect, useMemo, useRef, useState } from "react";
import { scoreColor, scoreOpacity } from "../lib/scoreColors";
import type { FeatureCollection, LayerState, POI, PredictionProperties } from "../lib/types";
import { MapLegend } from "./MapLegend";

const bounds: [number, number, number, number] = [150.5, -36.5, 154.5, -32.0];
const initialCenter = { longitude: 152.5, latitude: -34.25 };
const tileSize = 256;

type Point = { x: number; y: number };
type Center = { longitude: number; latitude: number };

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function hexToRgb(hex: string) {
  const normalized = hex.replace("#", "");
  const value = Number.parseInt(normalized, 16);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255
  };
}

function rgba(hex: string, alpha: number) {
  const rgb = hexToRgb(hex);
  return `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, ${clamp(alpha, 0, 1)})`;
}

function lonLatToWorld(longitude: number, latitude: number, zoom: number): Point {
  const sin = Math.sin((clamp(latitude, -85.0511, 85.0511) * Math.PI) / 180);
  const scale = tileSize * 2 ** zoom;
  return { x: ((longitude + 180) / 360) * scale, y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale };
}

function worldToLonLat(point: Point, zoom: number): Center {
  const scale = tileSize * 2 ** zoom;
  const longitude = (point.x / scale) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * point.y) / scale;
  const latitude = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  return { longitude: clamp(longitude, 149.5, 155.5), latitude: clamp(latitude, -37.6, -31.0) };
}

function tileUrl(x: number, y: number, zoom: number) {
  const server = ["a", "b", "c"][Math.abs(x + y) % 3];
  return `https://${server}.tile.openstreetmap.org/${zoom}/${x}/${y}.png`;
}

function project(longitude: number, latitude: number, center: Center, zoom: number, size: Point) {
  const c = lonLatToWorld(center.longitude, center.latitude, zoom);
  const p = lonLatToWorld(longitude, latitude, zoom);
  return { x: p.x - c.x + size.x / 2, y: p.y - c.y + size.y / 2 };
}

function tiles(center: Center, zoom: number, size: Point) {
  if (!size.x || !size.y) return [];
  const centerWorld = lonLatToWorld(center.longitude, center.latitude, zoom);
  const startX = centerWorld.x - size.x / 2;
  const startY = centerWorld.y - size.y / 2;
  const minTileX = Math.floor(startX / tileSize) - 1;
  const maxTileX = Math.floor((startX + size.x) / tileSize) + 1;
  const minTileY = Math.floor(startY / tileSize) - 1;
  const maxTileY = Math.floor((startY + size.y) / tileSize) + 1;
  const count = 2 ** zoom;
  const out = [];
  for (let x = minTileX; x <= maxTileX; x += 1) {
    const wrappedX = ((x % count) + count) % count;
    for (let y = minTileY; y <= maxTileY; y += 1) {
      if (y >= 0 && y < count) out.push({ key: `${zoom}-${x}-${y}`, left: x * tileSize - startX, top: y * tileSize - startY, url: tileUrl(wrappedX, y, zoom) });
    }
  }
  return out;
}

export function PredictionMapView({
  geojson,
  spots,
  pois,
  layers,
  selectedIndex,
  selectedSpotIndex,
  onSelect,
  onSpotSelect
}: {
  geojson: FeatureCollection<PredictionProperties> | null;
  spots?: FeatureCollection<PredictionProperties> | null;
  pois: POI[];
  layers: LayerState;
  selectedIndex: number | null;
  selectedSpotIndex: number | null;
  onSelect: (index: number) => void;
  onSpotSelect: (index: number) => void;
}) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const dragRef = useRef<{ pointerId: number; start: Point; centerWorld: Point } | null>(null);
  const movedRef = useRef(false);
  const [center, setCenter] = useState(initialCenter);
  const [zoom, setZoom] = useState(8);
  const [size, setSize] = useState<Point>({ x: 0, y: 0 });
  const [selectedPoi, setSelectedPoi] = useState<POI | null>(null);
  const tileList = useMemo(() => tiles(center, zoom, size), [center, zoom, size]);
  const selected = selectedIndex == null ? null : geojson?.features[selectedIndex];
  const selectedSpot = selectedSpotIndex == null ? null : spots?.features[selectedSpotIndex];
  const activeModelSource = geojson?.features[0]?.properties.model_source === "deep_learning" || spots?.features[0]?.properties.model_source === "deep_learning" ? "Deep Learning" : "Scikit-learn";

  useEffect(() => {
    const update = () => {
      const rect = mapRef.current?.getBoundingClientRect();
      if (rect) setSize({ x: rect.width, y: rect.height });
    };
    update();
    const observer = new ResizeObserver(update);
    if (mapRef.current) observer.observe(mapRef.current);
    return () => observer.disconnect();
  }, []);

  const projectedCells = useMemo(() => {
    if (!geojson || !size.x || !size.y) return [];
    return geojson.features.map((feature, index) => {
      const [lon, lat] = feature.geometry.coordinates as number[];
      const p = project(lon, lat, center, zoom, size);
      return { feature, index, x: p.x, y: p.y, score: feature.properties.score };
    });
  }, [geojson, center, zoom, size]);

  useEffect(() => {
    if (!selectedSpot) return;
    const [lon, lat] = selectedSpot.geometry.coordinates as number[];
    setCenter({ longitude: lon, latitude: lat });
    setZoom((value) => Math.max(value, 13));
  }, [selectedSpot]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !size.x || !size.y) return;
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(size.x * ratio));
    canvas.height = Math.max(1, Math.floor(size.y * ratio));
    canvas.style.width = `${size.x}px`;
    canvas.style.height = `${size.y}px`;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, size.x, size.y);
    if (!layers.heatmap) return;
    const bucketSize = zoom >= 12 ? 7 : 12;
    const renderMargin = zoom >= 12 ? 180 : 140;
    const buckets = new Map<string, (typeof projectedCells)[number]>();
    projectedCells
      .filter((cell) => cell.score >= 30 && cell.x > -renderMargin && cell.y > -renderMargin && cell.x < size.x + renderMargin && cell.y < size.y + renderMargin)
      .forEach((cell) => {
        const key = `${Math.round(cell.x / bucketSize)}:${Math.round(cell.y / bucketSize)}`;
        const existing = buckets.get(key);
        if (!existing || cell.score > existing.score) buckets.set(key, cell);
      });
    const visibleCells = Array.from(buckets.values()).sort((a, b) => a.score - b.score);
    const scale = zoom >= 12 ? 0.26 : 0.3;
    const surface = document.createElement("canvas");
    surface.width = Math.max(1, Math.floor(size.x * scale));
    surface.height = Math.max(1, Math.floor(size.y * scale));
    const surfaceCtx = surface.getContext("2d");
    if (!surfaceCtx) return;
    surfaceCtx.scale(scale, scale);
    surfaceCtx.globalCompositeOperation = "source-over";
    const radius = zoom >= 12 ? 54 : 42;
    for (const cell of visibleCells) {
      const intensity = clamp(cell.score / 100, 0, 1);
      const color = scoreColor(cell.score);
      const alpha = scoreOpacity(cell.score);
      const gradient = surfaceCtx.createRadialGradient(cell.x, cell.y, 0, cell.x, cell.y, radius);
      gradient.addColorStop(0, rgba(color, 0.1 + alpha * 0.3 + intensity * 0.04));
      gradient.addColorStop(0.56, rgba(color, 0.06 + alpha * 0.12));
      gradient.addColorStop(1, rgba(color, 0));
      surfaceCtx.fillStyle = gradient;
      surfaceCtx.beginPath();
      surfaceCtx.arc(cell.x, cell.y, radius, 0, Math.PI * 2);
      surfaceCtx.fill();
    }
    ctx.save();
    ctx.globalAlpha = 0.92;
    ctx.imageSmoothingEnabled = true;
    ctx.filter = zoom >= 12 ? "blur(22px) saturate(1.12)" : "blur(18px) saturate(1.16)";
    ctx.drawImage(surface, 0, 0, size.x, size.y);
    ctx.restore();
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = "source-over";
  }, [projectedCells, layers.heatmap, size, zoom]);

  function zoomBy(delta: number) {
    setZoom((value) => clamp(value + delta, 6, 15));
  }

  function reset() {
    setCenter(initialCenter);
    setZoom(8);
  }

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    event.currentTarget.setPointerCapture(event.pointerId);
    movedRef.current = false;
    dragRef.current = { pointerId: event.pointerId, start: { x: event.clientX, y: event.clientY }, centerWorld: lonLatToWorld(center.longitude, center.latitude, zoom) };
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (Math.abs(event.clientX - drag.start.x) + Math.abs(event.clientY - drag.start.y) > 4) movedRef.current = true;
    setCenter(worldToLonLat({ x: drag.centerWorld.x - (event.clientX - drag.start.x), y: drag.centerWorld.y - (event.clientY - drag.start.y) }, zoom));
  }

  function onPointerUp(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (drag?.pointerId === event.pointerId && !movedRef.current && layers.heatmap) {
      const rect = mapRef.current?.getBoundingClientRect();
      if (rect) {
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        let best: { index: number; distance: number } | null = null;
        const clickRadius = zoom >= 12 ? 18 : 12;
        for (const cell of projectedCells) {
          const dx = cell.x - x;
          const dy = cell.y - y;
          const distance = Math.sqrt(dx * dx + dy * dy);
          if (distance <= clickRadius && (!best || distance < best.distance)) best = { index: cell.index, distance };
        }
        if (best) onSelect(best.index);
      }
    }
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  }

  return (
    <section className="mapPanel predictionMapPanel">
      <div className="mapToolbar">
        <div>
          <strong>Prediction Map</strong>
          <span>{activeModelSource} overlay · OpenStreetMap basemap</span>
        </div>
        <button className="mapResetButton" onPointerDown={(e) => e.stopPropagation()} onClick={reset}>Reset view</button>
      </div>
      <div ref={mapRef} className="realMapShell predictionMapShell" onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}>
        <div className="tileMap">
          {tileList.map((tile) => <img key={tile.key} alt="" className="mapTile" src={tile.url} style={{ left: tile.left, top: tile.top }} draggable={false} />)}
        </div>
        <canvas ref={canvasRef} className="predictionCanvas" />
        {selected && (() => {
          const [lon, lat] = selected.geometry.coordinates as number[];
          const p = project(lon, lat, center, zoom, size);
          return <span className="predictionCell selected" style={{ left: p.x, top: p.y, backgroundColor: scoreColor(selected.properties.score) }} />;
        })()}
        {layers.fronts && geojson?.features.filter((feature) => (feature.properties as any).sst_gradient > 0.08).slice(0, 160).map((feature, index) => {
          const [lon, lat] = feature.geometry.coordinates as number[];
          const p = project(lon, lat, center, zoom, size);
          return <span key={`front-${index}`} className="predictionFrontCell" style={{ left: p.x, top: p.y }} />;
        })}
        {layers.currents && projectedCells.filter((cell) => {
          const props = cell.feature.properties;
          return typeof props.current_speed === "number" && typeof props.current_direction_degrees === "number" && props.current_speed > 0.05;
        }).filter((_, index) => index % (zoom >= 12 ? 22 : 42) === 0).slice(0, 220).map((cell, index) => {
          const props = cell.feature.properties;
          const length = clamp((props.current_speed || 0) * 38, 5, 28);
          const direction = props.current_direction_degrees || 0;
          const phase = (((cell.x || 0) * 0.037 + Math.abs(cell.y || 0) * 0.021) % 2.5).toFixed(2);
          const dur = (1.6 + (1 - Math.min(1, (props.current_speed || 0) / 0.8)) * 1.2).toFixed(1);
          const travel = Math.round(length * 0.5);
          return <span key={`current-${index}`} className="currentArrow" style={{ left: cell.x, top: cell.y, width: length, "--cur-rot": `${direction}deg`, "--cur-dur": `${dur}s`, "--cur-travel": `${travel}px`, animationDelay: `${phase}s` } as React.CSSProperties} />;
        })}
        {layers.pois && spots?.features.map((feature, index) => {
          const poi = feature.properties.nearest_poi;
          if (!poi?.name) return null;
          const [lon, lat] = feature.geometry.coordinates as number[];
          const p = project(lon, lat, center, zoom, size);
          if (p.x < -40 || p.y < -40 || p.x > size.x + 40 || p.y > size.y + 40) return null;
          return <span key={`poi-context-${index}`} className="hotspotPoiContext" style={{ left: p.x + 16, top: p.y - 18 }}>{poi.name}</span>;
        })}
        {false && layers.pois && pois.slice(0, 32).map((poi) => {
          const p = project(poi.longitude, poi.latitude, center, zoom, size);
          if (p.x < -40 || p.y < -40 || p.x > size.x + 40 || p.y > size.y + 40) return null;
          return (
            <button
              key={poi.id}
              className={`fallbackPoi ${poi.poi_type}`}
              title={`${poi.name} demo only`}
              style={{ left: p.x, top: p.y }}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => setSelectedPoi(poi)}
            >
              {zoom >= 10 ? <span>{poi.name}</span> : null}
            </button>
          );
        })}
        {layers.hotspots && spots?.features.map((feature, index) => {
          const [lon, lat] = feature.geometry.coordinates as number[];
          const p = project(lon, lat, center, zoom, size);
          if (p.x < -30 || p.y < -30 || p.x > size.x + 30 || p.y > size.y + 30) return null;
          return (
            <button
              key={`spot-${feature.properties.species_id}-${index}`}
              className="recommendedSpot"
              style={{ left: p.x, top: p.y }}
              title={`Spot #${(feature.properties as any).spot_rank || index + 1}: ${feature.properties.score.toFixed(2)}`}
              onPointerDown={(e) => e.stopPropagation()}
              onClick={() => {
                if (!geojson) return;
                const matchingIndex = geojson.features.findIndex((cell) => {
                  const [cellLon, cellLat] = cell.geometry.coordinates as number[];
                  return Math.abs(cellLon - lon) < 1e-6 && Math.abs(cellLat - lat) < 1e-6;
                });
                onSelect(matchingIndex >= 0 ? matchingIndex : index);
                onSpotSelect(index);
              }}
            >
              {(feature.properties as any).spot_rank || index + 1}
            </button>
          );
        })}
        <div className="mapZoomControl" onPointerDown={(e) => e.stopPropagation()}>
          <button onClick={() => zoomBy(1)}>+</button>
          <button onClick={() => zoomBy(-1)}>-</button>
        </div>
        <MapLegend />
        {selected && (
          <div className="mapSelection predictionPopup">
            <strong>{selected.properties.common_name}</strong>
            <small>Model: {selected.properties.model_source === "deep_learning" ? "Deep Learning" : "Scikit-learn"}</small>
            <span>{selected.properties.rating}: {selected.properties.score.toFixed(2)} / 100</span>
            <small>{(selected.geometry.coordinates as number[])[1].toFixed(3)}, {(selected.geometry.coordinates as number[])[0].toFixed(3)}</small>
            <small>SST source: {selected.properties.sst_source_date || "unavailable"}</small>
          </div>
        )}
        {selectedSpot && (() => {
          const props = selectedSpot.properties;
          return (
            <div className="mapSelection predictionPopup">
              <strong>Spot #{props.spot_rank}: {props.common_name}</strong>
              <small>Model: {props.model_source === "deep_learning" ? "Deep Learning" : "Scikit-learn"}</small>
              <span>{props.rating}: {props.score.toFixed(2)} / 100</span>
              <small>SST: {typeof props.sst_c === "number" ? `${props.sst_c.toFixed(1)}C` : "unavailable"} | Source: {props.sst_source_date || props.date || "unavailable"}</small>
              <small>Current: {typeof props.current_speed === "number" ? `${props.current_speed.toFixed(2)}m/s` : "unavailable"}</small>
              <small>Depth: {typeof props.depth_m === "number" ? `${props.depth_m.toFixed(0)}m` : "unavailable"} | Coast: {typeof props.distance_to_coast_km === "number" ? `${props.distance_to_coast_km.toFixed(1)}km` : "unavailable"}</small>
              {props.nearest_poi?.name && <small>POI context: {props.nearest_poi.name} ({props.nearest_poi.distance_km}km)</small>}
              <small>Relative suitability only; not exact fish location.</small>
            </div>
          );
        })()}
        {selectedPoi && (() => {
          const p = project(selectedPoi.longitude, selectedPoi.latitude, center, zoom, size);
          return (
            <div className="mapSelection poiPopup" style={{ left: clamp(p.x + 14, 14, Math.max(14, size.x - 300)), top: clamp(p.y + 14, 14, Math.max(14, size.y - 140)), right: "auto", bottom: "auto" }}>
              <strong>{selectedPoi.name}</strong>
              <span>{selectedPoi.poi_type.replaceAll("_", " ")}</span>
              <small>{selectedPoi.notes}</small>
              <small>Demo-only POI, not a verified fishing mark.</small>
            </div>
          );
        })()}
      </div>
    </section>
  );
}
