import { useEffect, useMemo, useRef, useState } from "react";
import type { FeatureCollection, FrontProperties, HotspotProperties, LayerState, POI } from "../lib/types";

const bounds: [number, number, number, number] = [150.5, -36.5, 154.5, -32.0];
const initialCenter = { longitude: 152.05, latitude: -34.15 };
const tileSize = 256;

type Point = { x: number; y: number };
type Center = { longitude: number; latitude: number };
type Tile = { key: string; x: number; y: number; left: number; top: number; url: string };

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function lonLatToWorld(longitude: number, latitude: number, zoom: number): Point {
  const sin = Math.sin((clamp(latitude, -85.0511, 85.0511) * Math.PI) / 180);
  const scale = tileSize * 2 ** zoom;
  return {
    x: ((longitude + 180) / 360) * scale,
    y: (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale
  };
}

function worldToLonLat(point: Point, zoom: number): Center {
  const scale = tileSize * 2 ** zoom;
  const longitude = (point.x / scale) * 360 - 180;
  const n = Math.PI - (2 * Math.PI * point.y) / scale;
  const latitude = (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  return {
    longitude: clamp(longitude, 149.4, 155.4),
    latitude: clamp(latitude, -37.5, -31.1)
  };
}

function tileUrl(x: number, y: number, zoom: number) {
  const servers = ["a", "b", "c", "d"];
  const server = servers[Math.abs(x + y) % servers.length];
  return `https://${server}.basemaps.cartocdn.com/rastertiles/voyager/${zoom}/${x}/${y}.png`;
}

function buildTiles(center: Center, zoom: number, size: Point): Tile[] {
  if (!size.x || !size.y) return [];
  const centerWorld = lonLatToWorld(center.longitude, center.latitude, zoom);
  const startX = centerWorld.x - size.x / 2;
  const startY = centerWorld.y - size.y / 2;
  const minTileX = Math.floor(startX / tileSize) - 1;
  const maxTileX = Math.floor((startX + size.x) / tileSize) + 1;
  const minTileY = Math.floor(startY / tileSize) - 1;
  const maxTileY = Math.floor((startY + size.y) / tileSize) + 1;
  const count = 2 ** zoom;
  const tiles: Tile[] = [];

  for (let x = minTileX; x <= maxTileX; x += 1) {
    const wrappedX = ((x % count) + count) % count;
    for (let y = minTileY; y <= maxTileY; y += 1) {
      if (y < 0 || y >= count) continue;
      tiles.push({
        key: `${zoom}-${x}-${y}`,
        x: wrappedX,
        y,
        left: x * tileSize - startX,
        top: y * tileSize - startY,
        url: tileUrl(wrappedX, y, zoom)
      });
    }
  }
  return tiles;
}

function projectToScreen(longitude: number, latitude: number, center: Center, zoom: number, size: Point) {
  const centerWorld = lonLatToWorld(center.longitude, center.latitude, zoom);
  const pointWorld = lonLatToWorld(longitude, latitude, zoom);
  return {
    x: pointWorld.x - centerWorld.x + size.x / 2,
    y: pointWorld.y - centerWorld.y + size.y / 2
  };
}

function projectToPercent(longitude: number, latitude: number) {
  const x = ((longitude - bounds[0]) / (bounds[2] - bounds[0])) * 100;
  const y = ((bounds[3] - latitude) / (bounds[3] - bounds[1])) * 100;
  return { x: clamp(x, 0, 100), y: clamp(y, 0, 100) };
}

function LocalFallbackArt() {
  return (
    <div className="fallbackMapArt" aria-hidden="true">
      <div className="fallbackLand" />
      <div className="fallbackCoastLabel labelSydney">Sydney</div>
      <div className="fallbackCoastLabel labelJervis">Jervis Bay</div>
      <div className="shelfLine shelfOne" />
      <div className="shelfLine shelfTwo" />
    </div>
  );
}

function FrontOverlay({
  fronts,
  center,
  zoom,
  size,
  online
}: {
  fronts: FeatureCollection<FrontProperties>;
  center: Center;
  zoom: number;
  size: Point;
  online: boolean;
}) {
  return (
    <>
      {fronts.features.map((front, index) => {
        const coords = front.geometry.coordinates as [number, number][];
        if (!coords?.length) return null;
        const start = online ? projectToScreen(coords[0][0], coords[0][1], center, zoom, size) : projectToPercent(coords[0][0], coords[0][1]);
        const end = online
          ? projectToScreen(coords[coords.length - 1][0], coords[coords.length - 1][1], center, zoom, size)
          : projectToPercent(coords[coords.length - 1][0], coords[coords.length - 1][1]);
        const length = Math.hypot(end.x - start.x, end.y - start.y);
        const angle = Math.atan2(end.y - start.y, end.x - start.x) * (180 / Math.PI);
        return (
          <div
            key={`front-${index}`}
            className="fallbackFront"
            style={{
              left: online ? `${start.x}px` : `${start.x}%`,
              top: online ? `${start.y}px` : `${start.y}%`,
              width: online ? `${length}px` : `${length}%`,
              transform: `rotate(${angle}deg)`
            }}
          />
        );
      })}
    </>
  );
}

export function MapView({
  hotspots,
  pois,
  fronts,
  layers,
  selectedHotspotId,
  onSelectHotspot
}: {
  hotspots: FeatureCollection<HotspotProperties>;
  pois: POI[];
  fronts: FeatureCollection<FrontProperties>;
  layers: LayerState;
  selectedHotspotId?: string;
  onSelectHotspot: (id: string) => void;
}) {
  const mapRef = useRef<HTMLDivElement | null>(null);
  const dragRef = useRef<{ pointerId: number; start: Point; centerWorld: Point } | null>(null);
  const [basemapMode, setBasemapMode] = useState<"online" | "local">("online");
  const [center, setCenter] = useState<Center>(initialCenter);
  const [zoom, setZoom] = useState(8);
  const [size, setSize] = useState<Point>({ x: 0, y: 0 });
  const [loadedTiles, setLoadedTiles] = useState(0);
  const [failedTiles, setFailedTiles] = useState(0);
  const selectedHotspot = useMemo(
    () => hotspots.features.find((feature) => feature.properties.id === selectedHotspotId)?.properties,
    [hotspots.features, selectedHotspotId]
  );
  const online = basemapMode === "online";
  const tiles = useMemo(() => buildTiles(center, zoom, size), [center, zoom, size]);
  const tileStatus = online
    ? loadedTiles > 0
      ? `Online real map visible (${loadedTiles} tiles loaded).`
      : failedTiles > 0
        ? "Online map tiles are blocked; use Local fallback."
        : "Loading online real map tiles..."
    : "Local NSW fallback map visible.";

  useEffect(() => {
    const updateSize = () => {
      const rect = mapRef.current?.getBoundingClientRect();
      if (rect) setSize({ x: rect.width, y: rect.height });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    if (mapRef.current) observer.observe(mapRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    setLoadedTiles(0);
    setFailedTiles(0);
  }, [center, zoom, basemapMode]);

  function resetView() {
    setCenter(initialCenter);
    setZoom(8);
  }

  function zoomBy(delta: number) {
    setZoom((value) => clamp(value + delta, 6, 11));
  }

  function onPointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (!online) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      pointerId: event.pointerId,
      start: { x: event.clientX, y: event.clientY },
      centerWorld: lonLatToWorld(center.longitude, center.latitude, zoom)
    };
  }

  function onPointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    const dx = event.clientX - drag.start.x;
    const dy = event.clientY - drag.start.y;
    setCenter(worldToLonLat({ x: drag.centerWorld.x - dx, y: drag.centerWorld.y - dy }, zoom));
  }

  function onPointerUp(event: React.PointerEvent<HTMLDivElement>) {
    if (dragRef.current?.pointerId === event.pointerId) dragRef.current = null;
  }

  return (
    <section className="mapPanel">
      <div className="mapToolbar">
        <div>
          <strong>Real Online Map: Sydney Offshore Demo</strong>
          <span>CARTO/OpenStreetMap tiles with pelagic feature overlays; local fallback remains available</span>
        </div>
        <button className="mapResetButton" onClick={resetView}>Reset view</button>
      </div>
      <div
        ref={mapRef}
        className={`realMapShell ${online ? "isOnline" : "isLocal"}`}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        <LocalFallbackArt />
        {online && (
          <div className="tileMap" aria-label="Online OpenStreetMap base map">
            {tiles.map((tile) => (
              <img
                key={tile.key}
                alt=""
                className="mapTile"
                src={tile.url}
                style={{ left: `${tile.left}px`, top: `${tile.top}px` }}
                draggable={false}
                onLoad={() => setLoadedTiles((count) => count + 1)}
                onError={() => setFailedTiles((count) => count + 1)}
              />
            ))}
          </div>
        )}
        {layers.fronts && <FrontOverlay fronts={fronts} center={center} zoom={zoom} size={size} online={online} />}
        {layers.pois && pois.slice(0, 26).map((poi) => {
          const point = online ? projectToScreen(poi.longitude, poi.latitude, center, zoom, size) : projectToPercent(poi.longitude, poi.latitude);
          return (
            <span
              key={poi.id}
              className={`fallbackPoi ${poi.poi_type}`}
              title={poi.name}
              style={{ left: online ? `${point.x}px` : `${point.x}%`, top: online ? `${point.y}px` : `${point.y}%` }}
            />
          );
        })}
        {layers.hotspots && hotspots.features.map((feature) => {
          const [longitude, latitude] = feature.geometry.coordinates as [number, number];
          const point = online ? projectToScreen(longitude, latitude, center, zoom, size) : projectToPercent(longitude, latitude);
          const score = feature.properties.score;
          return (
            <button
              key={feature.properties.id}
              className={`fallbackHotspot ${selectedHotspotId === feature.properties.id ? "selected" : ""}`}
              title={`${feature.properties.area_name}: ${score}/100`}
              onClick={(event) => {
                event.stopPropagation();
                onSelectHotspot(feature.properties.id);
              }}
              style={{
                left: online ? `${point.x}px` : `${point.x}%`,
                top: online ? `${point.y}px` : `${point.y}%`,
                width: `${18 + score * 0.22}px`,
                height: `${18 + score * 0.22}px`
              }}
            />
          );
        })}
        <div className="basemapToggle" aria-label="Base map mode">
          <button className={basemapMode === "online" ? "active" : ""} onClick={() => setBasemapMode("online")}>Online map</button>
          <button className={basemapMode === "local" ? "active" : ""} onClick={() => setBasemapMode("local")}>Local fallback</button>
        </div>
        <div className="mapZoomControl" aria-label="Map zoom controls">
          <button onClick={() => zoomBy(1)}>+</button>
          <button onClick={() => zoomBy(-1)}>-</button>
        </div>
        <div className="tileStatus">{tileStatus}</div>
        <div className="mapLegend">
          <span><i className="legendHot" /> Hotspot score</span>
          <span><i className="legendFront" /> SST front</span>
          <span><i className="legendPoi" /> Demo POI</span>
        </div>
        {selectedHotspot && (
          <div className="mapSelection">
            <strong>{selectedHotspot.area_name}</strong>
            <span>{selectedHotspot.rating} habitat score: {selectedHotspot.score}/100</span>
          </div>
        )}
      </div>
    </section>
  );
}
