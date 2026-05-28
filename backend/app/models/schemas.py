from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SpeciesProfile(BaseModel):
    species_id: str
    common_name: str
    scientific_name: Optional[str] = None
    category: str = "offshore_pelagic"
    aliases: List[str] = []
    preferred_sst_range_c: List[float]
    good_sst_range_c: Optional[List[float]] = None
    extended_sst_range_c: List[float]
    depth_preference: List[str]
    structure_preference: List[str]
    ocean_feature_preference: List[str]
    seasonality_by_month: Dict[str, str]
    positive_drivers: List[str]
    negative_drivers: List[str]
    key_features: List[str]
    seasonality_notes: str
    model_notes: str
    notes: str
    disclaimer: str


class OceanCondition(BaseModel):
    timestamp: str
    data_source: str = "mock"
    region_name: str
    bounding_box: Dict[str, float]
    sst_min_c: float
    sst_max_c: float
    dominant_current_direction: str
    current_strength_label: str
    chlorophyll_status: str
    sea_level_anomaly_status: str
    cloud_warning: str
    freshness_note: str
    confidence: str


class OceanGridCell(BaseModel):
    latitude: float
    longitude: float
    sst_c: float
    sst_category: str
    gradient_strength: float
    notes: str
    demo_only: bool = True


class CurrentVector(BaseModel):
    latitude: float
    longitude: float
    direction_degrees: float
    speed_m_s: float
    direction_label: str
    notes: str
    demo_only: bool = True


class OffshorePOI(BaseModel):
    id: str
    name: str
    latitude: float
    longitude: float
    area: str
    poi_type: str
    depth_class: str
    notes: str
    demo_only: bool = True


class HotspotPrediction(BaseModel):
    id: str
    species_id: str
    species_name: str
    latitude: float
    longitude: float
    area_name: str
    score: float = Field(ge=0, le=100)
    rating: str
    confidence: str
    explanation: List[str]
    suggested_strategy: str
    ocean_summary: Dict[str, Any]
    key_drivers: List[str]
    caution_notes: List[str]
    demo_only: bool = True


class GeoJSONFeature(BaseModel):
    type: str = "Feature"
    geometry: Dict[str, Any]
    properties: Dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJSONFeature]

