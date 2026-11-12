"""
Spatial & Attribute Deduplication Module.
Identifies and eliminates duplicate listings, repeat scrapes, and overlapping observations.
"""
from typing import List, Dict, Any
import pandas as pd
import numpy as np


def deduplicate_transactions(df: pd.DataFrame, spatial_precision_decimals: int = 4) -> pd.DataFrame:
    """
    Deduplicates property records based on exact keys and spatial-temporal proximity.
    
    1. Exact hash of property_id if present.
    2. Spatial rounding (~11 meters at 4 decimals) + area + floor + transaction year.
    """
    if df.empty:
        return df

    init_len = len(df)
    
    # 1. Exact property_id deduplication
    if "property_id" in df.columns:
        df = df.drop_duplicates(subset=["property_id"], keep="last")

    # 2. Spatial proximity deduplication
    df["lat_rounded"] = df["latitude"].round(spatial_precision_decimals)
    df["lon_rounded"] = df["longitude"].round(spatial_precision_decimals)
    df["area_rounded"] = (df["area_sqft"] / 25.0).round() * 25.0 # Round to nearest 25 sqft
    
    dedup_cols = ["lat_rounded", "lon_rounded", "area_rounded", "property_category"]
    if "transaction_year" in df.columns:
        dedup_cols.append("transaction_year")
    if "target_type" in df.columns:
        dedup_cols.append("target_type")

    df_clean = df.drop_duplicates(subset=dedup_cols, keep="last").copy()
    df_clean = df_clean.drop(columns=["lat_rounded", "lon_rounded", "area_rounded"])

    removed = init_len - len(df_clean)
    if removed > 0:
        print(f"[Deduplication] Removed {removed} duplicate or near-identical records ({init_len} -> {len(df_clean)}).")

    return df_clean
