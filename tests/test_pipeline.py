"""
Unit & Integration Tests for the 7-Cluster Valuation Pipeline.
"""
import pytest
import numpy as np
import pandas as pd

from src.pipeline.feature_assembler import UnifiedFeatureAssembler
from src.pipeline.interaction_layer import PropertyTypeInteractionEngine
from src.clusters.cluster1_connectivity import ConnectivityFeatureExtractor
from src.clusters.cluster2_traffic import TrafficFeatureExtractor
from src.clusters.cluster3_population import PopulationFeatureExtractor
from src.clusters.cluster4_development import FutureDevelopmentFeatureExtractor
from src.clusters.cluster5_government import GovernmentSignalFeatureExtractor
from src.clusters.cluster6_market import MarketConditionFeatureExtractor
from src.clusters.cluster7_physical import PhysicalAttributeFeatureExtractor
from src.models.trainer import PropertyValuationModel
from src.data_generator import generate_synthetic_real_estate_dataset


def test_cluster_extractors():
    lat, lon = 19.1254, 72.9157
    c1 = ConnectivityFeatureExtractor().extract(lat, lon)
    c2 = TrafficFeatureExtractor().extract(lat, lon)
    c3 = PopulationFeatureExtractor().extract(lat, lon)
    c4 = FutureDevelopmentFeatureExtractor().extract(lat, lon)
    c5 = GovernmentSignalFeatureExtractor().extract(lat, lon)
    c6 = MarketConditionFeatureExtractor().extract(lat, lon)
    c7 = PhysicalAttributeFeatureExtractor().extract()

    assert "dist_nh_km" in c1
    assert "traffic_vehicles_per_min" in c2
    assert "traffic_noise_proxy_db" in c2
    assert "colony_density_sqkm" in c3
    assert "fsi_far_allowable" in c4
    assert "is_smart_city_mission" in c5
    assert "price_psqft_12m_delta_pct" in c6
    assert "carpet_area_sqft" in c7


def test_dual_signal_interactions():
    engine = PropertyTypeInteractionEngine()
    base_features = {
        "traffic_vehicles_per_min": 50.0,
        "traffic_congestion_index": 0.4,
        "traffic_noise_proxy_db": 74.0,
        "traffic_heavy_vehicle_pct": 18.0,
        "traffic_weekday_weekend_ratio": 1.35,
        "dist_nh_km": 0.8,
        "dist_metro_station_km": 0.9,
        "fsi_far_allowable": 3.0,
    }

    # Test Residential: should have positive friction and 0 retail footfall
    res_inter = engine.compute_interactions(base_features, "residential")
    assert res_inter["residential_traffic_friction"] > 0
    assert res_inter["commercial_retail_footfall_score"] == 0.0

    # Test Commercial Retail: should have positive footfall score and 0 residential friction
    ret_inter = engine.compute_interactions(base_features, "commercial_retail")
    assert ret_inter["commercial_retail_footfall_score"] > 0
    assert ret_inter["residential_traffic_friction"] == 0.0


def test_assembler_vector_shape():
    assembler = UnifiedFeatureAssembler()
    vec = assembler.assemble_single(19.1254, 72.9157, "residential")
    assert isinstance(vec, dict)
    assert len(vec) >= 30
    # Ensure no NaN or Inf
    for k, v in vec.items():
        assert not np.isnan(v), f"Feature {k} has NaN value"
        assert not np.isinf(v), f"Feature {k} has Inf value"


def test_end_to_end_model_pipeline():
    raw_data = generate_synthetic_real_estate_dataset(n_samples=80, random_seed=99)
    assembler = UnifiedFeatureAssembler()
    df = assembler.assemble_batch(raw_data)
    
    model = PropertyValuationModel(random_state=99)
    summary = model.train(df, target_col="target_price_inr")
    assert summary["mean_cv_r2"] > 0.70

    test_rec = assembler.assemble_single(19.1254, 72.9157, "residential")
    df_test = pd.DataFrame([test_rec])
    point, low, high = model.predict(df_test)
    assert point[0] > 0
    assert low[0] <= point[0] <= high[0]
