import type { FeatureCollection, FrontProperties, HotspotProperties, OceanCondition, POI, SpeciesProfile } from "./types";

export const fallbackSpecies: SpeciesProfile[] = [
  {
    species_id: "yellowfin_tuna",
    common_name: "Yellowfin Tuna",
    aliases: ["YFT"],
    preferred_sst_range_c: [20, 24.5],
    extended_sst_range_c: [17.5, 27],
    depth_preference: ["shelf_break", "deep"],
    structure_preference: ["shelf_break", "canyon"],
    ocean_feature_preference: ["temperature front", "current edge"],
    seasonality_notes: "Warm to moderate offshore water and bait-holding fronts are favoured.",
    model_notes: "Fallback profile used when backend is offline.",
    key_features: ["SST breaks", "current edges", "shelf/canyon structure"],
    disclaimer: "Habitat suitability only, not exact fish locations."
  },
  {
    species_id: "mahi_mahi",
    common_name: "Mahi Mahi / Dolphinfish",
    aliases: ["dolphinfish"],
    preferred_sst_range_c: [22, 27],
    extended_sst_range_c: [19.5, 29],
    depth_preference: ["shelf", "shelf_break"],
    structure_preference: ["fad_demo", "current_edge"],
    ocean_feature_preference: ["warm water", "FAD-like structure"],
    seasonality_notes: "Warm-water months are favoured.",
    model_notes: "Fallback profile used when backend is offline.",
    key_features: ["Warm SST", "FAD-like structure", "current line"],
    disclaimer: "Habitat suitability only, not exact fish locations."
  }
];

export const fallbackOcean: OceanCondition = {
  timestamp: new Date().toISOString(),
  data_source: "mock",
  region_name: "Sydney and nearby NSW offshore demo region",
  bounding_box: { north_latitude: -32, south_latitude: -36.5, west_longitude: 150.5, east_longitude: 154.5 },
  sst_min_c: 16.8,
  sst_max_c: 26.4,
  dominant_current_direction: "south to south-east",
  current_strength_label: "moderate offshore EAC-style flow",
  chlorophyll_status: "mock chlorophyll edge near the shelf/front boundary",
  sea_level_anomaly_status: "synthetic weak eddy signal east of Sydney",
  cloud_warning: "No real satellite cloud mask is used in v0.1.",
  freshness_note: "Fallback synthetic demo data; backend is offline.",
  confidence: "Low - v0.1 uses synthetic ocean data."
};

export const fallbackHotspots: FeatureCollection<HotspotProperties> = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [151.8, -34.05] },
      properties: {
        id: "fallback_yft_browns",
        species_id: "yellowfin_tuna",
        species_name: "Yellowfin Tuna",
        latitude: -34.05,
        longitude: 151.8,
        area_name: "Browns Mountain area demo",
        score: 78,
        rating: "Prime",
        confidence: "Low",
        explanation: ["Fallback synthetic hotspot for UI continuity.", "Confidence is limited because this v0.1 demo uses synthetic ocean data."],
        suggested_strategy: "Focus on temperature breaks and current edges near shelf/canyon structure.",
        ocean_summary: { sst_c: 22.4, gradient_strength: 1.4, data_source: "mock" },
        key_drivers: ["SST front / gradient", "POI structure", "SST suitability"],
        caution_notes: ["Demo coordinates are approximate and not verified fishing marks."],
        demo_only: true
      }
    }
  ]
};

export const fallbackPois: POI[] = [
  { id: "browns_mountain_demo", name: "Browns Mountain area demo", latitude: -34.05, longitude: 151.8, area: "Sydney offshore", poi_type: "seamount", depth_class: "very_deep", notes: "Approximate demo point only.", demo_only: true },
  { id: "fad_central_demo", name: "FAD-style central Sydney demo", latitude: -33.85, longitude: 151.55, area: "Sydney offshore", poi_type: "fad_demo", depth_class: "shelf", notes: "Synthetic FAD-style point only.", demo_only: true }
];

export const fallbackFronts: FeatureCollection<FrontProperties> = {
  type: "FeatureCollection",
  features: [
    { type: "Feature", geometry: { type: "LineString", coordinates: [[151.05, -36.3], [151.55, -35.3], [152, -34.3], [152.45, -33.3]] }, properties: { front_strength: "moderate", sst_change_c: 1.8, notes: "Synthetic SST front.", demo_only: true } }
  ]
};
