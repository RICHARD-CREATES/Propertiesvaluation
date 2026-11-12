"""
Unified Feature Assembler.
Aggregates all 7 clusters, invokes the property-type dual-signal interaction engine,
encodes categoricals, and outputs a clean, high-dimensional numeric feature vector.
"""
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np

from src.clusters.cluster1_connectivity import ConnectivityFeatureExtractor
from src.clusters.cluster2_traffic import TrafficFeatureExtractor
from src.clusters.cluster3_population import PopulationFeatureExtractor
from src.clusters.cluster4_development import FutureDevelopmentFeatureExtractor
from src.clusters.cluster5_government import GovernmentSignalFeatureExtractor
from src.clusters.cluster6_market import MarketConditionFeatureExtractor
from src.clusters.cluster7_physical import PhysicalAttributeFeatureExtractor
from src.pipeline.interaction_layer import PropertyTypeInteractionEngine


class UnifiedFeatureAssembler:
    """Orchestrates 7-cluster feature extraction and builds matrix ready for ML."""

    def __init__(self):
        self.c1_extractor = ConnectivityFeatureExtractor()
        self.c2_extractor = TrafficFeatureExtractor()
        self.c3_extractor = PopulationFeatureExtractor()
        self.c4_extractor = FutureDevelopmentFeatureExtractor()
        self.c5_extractor = GovernmentSignalFeatureExtractor()
        self.c6_extractor = MarketConditionFeatureExtractor()
        self.c7_extractor = PhysicalAttributeFeatureExtractor()
        self.interaction_engine = PropertyTypeInteractionEngine()

        # Categorical ordinal mappings
        self.grade_map = {"Grade_C": 0.0, "Grade_B": 1.0, "Grade_A": 2.0}
        self.zoning_map = {"Green Belt": 0.0, "Residential": 1.0, "Mixed-Use": 2.0, "Commercial": 3.0, "Industrial": 2.5}
        self.orientation_map = {"North": 1.0, "East": 1.0, "West": 0.5, "South": 0.0}
        self.zone_type_map = {
            "residential_neighborhood": 0.0,
            "office_commuter": 1.0,
            "retail_market": 2.0,
            "logistics": 3.0,
        }

    def assemble_single(
        self,
        lat: float,
        lon: float,
        property_type: str,
        overrides: Dict[str, Any] = None,
    ) -> Dict[str, float]:
        """Runs full 7-cluster pipeline for a single property and returns flat feature dict."""
        overrides = overrides or {}

        # 1. Extract from all 7 clusters
        c1 = self.c1_extractor.extract(lat, lon, overrides)
        c2 = self.c2_extractor.extract(lat, lon, overrides)
        c3 = self.c3_extractor.extract(lat, lon, overrides)
        c4 = self.c4_extractor.extract(lat, lon, overrides)
        c5 = self.c5_extractor.extract(lat, lon, overrides)
        c6 = self.c6_extractor.extract(lat, lon, overrides)
        c7 = self.c7_extractor.extract(overrides)

        # Merge base features
        base_features = {}
        for c in [c1, c2, c3, c4, c5, c6, c7]:
            base_features.update(c)

        # 2. Compute Property-Type Conditional Interactions
        interactions = self.interaction_engine.compute_interactions(base_features, property_type)

        # 3. Assemble and encode categoricals into purely numeric dictionary
        vector_dict: Dict[str, float] = {}

        # Numeric cluster features
        for k, v in base_features.items():
            if isinstance(v, (int, float, np.number)):
                vector_dict[k] = float(v)
            elif k == "construction_grade":
                vector_dict["construction_grade_score"] = self.grade_map.get(v, 1.0)
            elif k == "master_plan_zoning":
                vector_dict["zoning_class_score"] = self.zoning_map.get(v, 1.0)
            elif k == "property_orientation":
                vector_dict["orientation_score"] = self.orientation_map.get(v, 0.5)
            elif k == "traffic_zone_type":
                vector_dict["traffic_zone_type_code"] = self.zone_type_map.get(v, 0.0)

        # Add interactions
        for k, v in interactions.items():
            vector_dict[k] = float(v)

        return vector_dict

    def assemble_batch(self, property_records: List[Dict[str, Any]]) -> pd.DataFrame:
        """Processes a list of raw property dictionaries into a clean DataFrame."""
        rows = []
        for prop in property_records:
            lat = prop.get("latitude", 19.1254)  # Default Mumbai / Powai
            lon = prop.get("longitude", 72.9157)
            prop_type = prop.get("property_type", "residential")
            feat_dict = self.assemble_single(lat, lon, prop_type, prop)
            
            # Keep target price if available for training
            if "target_price_inr" in prop:
                feat_dict["target_price_inr"] = float(prop["target_price_inr"])
            if "property_id" in prop:
                feat_dict["property_id"] = prop["property_id"]
            if "property_type" in prop:
                feat_dict["property_type_label"] = prop["property_type"]

            rows.append(feat_dict)

        df = pd.DataFrame(rows)
        return df
