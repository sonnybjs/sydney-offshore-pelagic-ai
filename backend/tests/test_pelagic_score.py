from app.scoring.pelagic_score import score_pelagic_habitat
from app.scoring.species_profiles import get_species_profile


def test_score_always_between_zero_and_one_hundred():
    profile = get_species_profile("yellowfin_tuna")
    result = score_pelagic_habitat(
        profile,
        {
            "sst_c": 22,
            "gradient_strength": 1.3,
            "current_speed_m_s": 0.7,
            "poi_type": "canyon",
            "depth_class": "deep",
            "data_confidence": "mock",
        },
    )
    assert 0 <= result["score"] <= 100


def test_yellowfin_ideal_conditions_score_higher_than_poor_conditions():
    profile = get_species_profile("yellowfin_tuna")
    ideal = score_pelagic_habitat(
        profile,
        {"sst_c": 22, "gradient_strength": 1.6, "current_speed_m_s": 0.8, "poi_type": "canyon", "depth_class": "deep", "data_confidence": "mock"},
        month=4,
    )
    poor = score_pelagic_habitat(
        profile,
        {"sst_c": 15, "gradient_strength": 0.1, "current_speed_m_s": 0.2, "poi_type": "harbour_departure", "depth_class": "shallow", "data_confidence": "mock"},
        month=8,
    )
    assert ideal["score"] > poor["score"]


def test_mahi_near_warm_fad_scores_higher_than_cool_featureless_water():
    profile = get_species_profile("mahi_mahi")
    ideal = score_pelagic_habitat(
        profile,
        {"sst_c": 24, "gradient_strength": 1.0, "current_speed_m_s": 0.65, "poi_type": "fad_demo", "depth_class": "shelf", "data_confidence": "mock"},
        month=2,
    )
    poor = score_pelagic_habitat(
        profile,
        {"sst_c": 17, "gradient_strength": 0.1, "current_speed_m_s": 0.2, "poi_type": "current_edge", "depth_class": "very_deep", "data_confidence": "mock"},
        month=7,
    )
    assert ideal["score"] > poor["score"]

