def ocean_summary_for(properties: dict) -> dict:
    return {
        "sst_c": properties["sst_c"],
        "gradient_strength": properties["gradient_strength"],
        "current_speed_m_s": properties["current_speed_m_s"],
        "feature_context": properties["poi_type"],
        "data_source": "mock",
    }

