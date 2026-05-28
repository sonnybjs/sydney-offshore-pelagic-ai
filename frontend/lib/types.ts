export type SpeciesProfile = {
  species_id: string;
  common_name: string;
  scientific_name?: string;
  aliases: string[];
  preferred_sst_range_c: number[];
  good_sst_range_c?: number[];
  extended_sst_range_c: number[];
  depth_preference: string[];
  structure_preference: string[];
  ocean_feature_preference: string[];
  seasonality_notes: string;
  model_notes: string;
  key_features: string[];
  disclaimer: string;
};

export type OceanCondition = {
  timestamp: string;
  data_source: string;
  region_name: string;
  bounding_box: Record<string, number>;
  sst_min_c: number;
  sst_max_c: number;
  dominant_current_direction: string;
  current_strength_label: string;
  chlorophyll_status: string;
  sea_level_anomaly_status: string;
  cloud_warning: string;
  freshness_note: string;
  confidence: string;
};

export type Feature<T> = {
  type: "Feature";
  geometry: { type: string; coordinates: number[] | number[][] };
  properties: T;
};

export type FeatureCollection<T> = {
  type: "FeatureCollection";
  features: Feature<T>[];
};

export type HotspotProperties = {
  id: string;
  species_id: string;
  species_name: string;
  latitude: number;
  longitude: number;
  area_name: string;
  score: number;
  rating: string;
  confidence: string;
  explanation: string[];
  suggested_strategy: string;
  ocean_summary: Record<string, string | number | boolean>;
  key_drivers: string[];
  caution_notes: string[];
  demo_only: boolean;
};

export type LayerState = {
  heatmap: boolean;
  hotspots: boolean;
  sst: boolean;
  fronts: boolean;
  currents: boolean;
  pois: boolean;
  shelf: boolean;
};

export type POI = {
  id: string;
  name: string;
  latitude: number;
  longitude: number;
  area: string;
  poi_type: string;
  depth_class: string;
  notes: string;
  demo_only: boolean;
};

export type CurrentProperties = {
  direction_degrees: number;
  speed_m_s: number;
  direction_label: string;
  notes: string;
  demo_only: boolean;
};

export type SstProperties = {
  sst_c: number;
  sst_category: string;
  gradient_strength: number;
  notes: string;
  demo_only: boolean;
};

export type FrontProperties = {
  front_strength: string;
  sst_change_c: number;
  notes: string;
  demo_only: boolean;
};

export type PredictionMode = "demo" | "current";

export type PredictionSpeciesManifest = {
  available: boolean;
  mode?: PredictionMode;
  species_id: string;
  common_name: string;
  prediction_date?: string;
  target_date?: string;
  available_dates?: string[];
  file_path?: string;
  model_type?: string;
  model_confidence?: string;
  feature_set_name?: string;
  data_source_dates?: {
    sst?: string | null;
    physics?: string | null;
    chl?: string | null;
    bathymetry?: string | null;
  };
  available_layers?: string[];
  notes?: string;
  reason?: string;
  audit_status?: string;
  warning?: string;
  score_explanation?: string;
};

export type PredictionManifest = {
  demo: { mode: "demo"; date?: string | null; species: Record<string, PredictionSpeciesManifest>; notes?: string };
  current: { mode: "current"; target_date?: string; species: Record<string, PredictionSpeciesManifest>; notes?: string };
};

export type PredictionProperties = {
  species_id: string;
  common_name: string;
  mode?: PredictionMode;
  target_date?: string;
  prediction_date?: string;
  date?: string;
  lat?: number;
  lon?: number;
  score: number;
  rating: string;
  confidence: string;
  model_type?: string;
  feature_set_name?: string;
  top_drivers?: string[];
  explanation?: string[];
  limitations?: string[];
  sst_source_date?: string | null;
  physics_source_date?: string | null;
  chl_source_date?: string | null;
  has_sst?: boolean;
  has_bathymetry?: boolean;
  has_physics?: boolean;
  has_chl?: boolean;
  data_sources_available?: string;
  sst_c?: number | null;
  sst_gradient?: number | null;
  sst_front_strength?: number | null;
  depth_m?: number | null;
  distance_to_coast_km?: number | null;
  current_speed?: number | null;
  current_direction_degrees?: number | null;
  current_edge_score?: number | null;
  spot_rank?: number;
  recommendation_radius_m?: number;
  coast_priority_band?: string;
  nearest_poi?: {
    id?: string;
    name?: string;
    poi_type?: string;
    distance_km?: number;
    demo_only?: boolean;
    notes?: string;
  };
  poi_context?: string;
};

export type PredictionMapResponse = {
  metadata: {
    mode: PredictionMode;
    species_id: string;
    common_name: string;
    prediction_date?: string;
    target_date?: string;
    available_dates?: string[];
    data_source_dates?: PredictionSpeciesManifest["data_source_dates"];
    model_confidence?: string;
    feature_set_name?: string;
    available_layers?: string[];
    notes?: string;
    audit_status?: string;
    warning?: string;
    score_explanation?: string;
    spot_count?: number;
    recommendation_radius_m?: number;
    min_separation_km?: number;
    model_grid_resolution_note?: string;
  };
  geojson: FeatureCollection<PredictionProperties>;
};
