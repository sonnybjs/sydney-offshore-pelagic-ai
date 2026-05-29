import { fallbackFronts, fallbackHotspots, fallbackOcean, fallbackPois, fallbackSpecies } from "./mockFallback";
import type { FeatureCollection, FrontProperties, HotspotProperties, ModelSource, OceanCondition, POI, PredictionMapResponse, PredictionManifest, PredictionMode, SpeciesProfile } from "./types";

function defaultApiBase() {
  return "/api/backend";
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || defaultApiBase();

async function getJson<T>(path: string, fallback: T): Promise<{ data: T; offline: boolean }> {
  try {
    const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return { data: (await response.json()) as T, offline: false };
  } catch {
    return { data: fallback, offline: true };
  }
}

export function fetchSpecies() {
  return getJson<SpeciesProfile[]>("/species", fallbackSpecies);
}

export function fetchOcean() {
  return getJson<OceanCondition>("/ocean/mock/latest", fallbackOcean);
}

export function fetchHotspots(speciesId: string) {
  return getJson<FeatureCollection<HotspotProperties>>(`/hotspots/${speciesId}`, fallbackHotspots);
}

export function fetchPois() {
  return getJson<POI[]>("/pois", fallbackPois);
}

export function fetchFronts() {
  return getJson<FeatureCollection<FrontProperties>>("/layers/mock/fronts", fallbackFronts);
}

export function fetchPredictionManifest() {
  return getJson<PredictionManifest>("/predictions/manifest", {
    demo: { mode: "demo", species: {} },
    current: { mode: "current", species: {} }
  });
}

export function fetchPredictionMap(mode: PredictionMode, speciesId: string, date?: string | null, modelSource: ModelSource = "scikit_learn") {
  const dateParam = date ? `&date=${date}` : "";
  return getJson<PredictionMapResponse | null>(`/predictions/map?mode=${mode}&species_id=${speciesId}${dateParam}&model_source=${modelSource}`, null);
}

export function fetchPredictionSpots(mode: PredictionMode, speciesId: string, radiusM = 500, date?: string | null, modelSource: ModelSource = "scikit_learn") {
  const dateParam = date ? `&date=${date}` : "";
  return getJson<PredictionMapResponse | null>(`/predictions/spots?mode=${mode}&species_id=${speciesId}${dateParam}&model_source=${modelSource}&radius_m=${radiusM}&limit=30&min_separation_km=4`, null);
}
