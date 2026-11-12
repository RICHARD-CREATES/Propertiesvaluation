"""
Cohort Partitioning and Multi-Country Training Core.
Prevents cross-currency pooling, enforces country-asset cohort boundaries,
and executes time-based holdout validation.
"""
from pathlib import Path
from typing import Dict, Any, Tuple, List
import numpy as np
import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parents[2] / "configs" / "schema.yaml"
if CONFIG_PATH.exists():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        SCHEMA = yaml.safe_load(f)
else:
    SCHEMA = {"clusters": {}, "categorical": []}


def prepare_cohort_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Validates required columns and computes localized price per sqm."""
    required = ["sale_price", "currency", "country_code", "asset_type", "transaction_date"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required training columns: {missing}")

    clean = df.copy()
    clean["sale_price"] = pd.to_numeric(clean["sale_price"], errors="coerce")
    clean["transaction_date"] = pd.to_datetime(clean["transaction_date"], errors="coerce", utc=True)
    clean["country_code"] = clean["country_code"].astype("string").str.upper()
    clean["asset_type"] = clean["asset_type"].astype("string").str.lower()
    clean["currency"] = clean["currency"].astype("string").str.upper()

    area = pd.to_numeric(clean.get("built_area_sqm"), errors="coerce") if "built_area_sqm" in clean else pd.Series(np.nan, index=clean.index)
    land = pd.to_numeric(clean.get("land_area_sqm"), errors="coerce") if "land_area_sqm" in clean else pd.Series(np.nan, index=clean.index)

    # Use built area for residential/commercial, land area for land
    is_land = clean["asset_type"].eq("land")
    clean["valuation_area_sqm"] = np.where(is_land, land, area)
    clean["price_per_sqm"] = clean["sale_price"] / clean["valuation_area_sqm"]

    clean = clean.replace([np.inf, -np.inf], np.nan)
    clean = clean.dropna(subset=["sale_price", "price_per_sqm", "transaction_date", "country_code", "asset_type"])
    clean = clean[(clean["sale_price"] > 0) & (clean["price_per_sqm"] > 0) & (clean["valuation_area_sqm"] > 0)]
    return clean


def split_temporal_holdout(cohort_df: pd.DataFrame, train_ratio: float = 0.8) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Splits cohort by transaction date to prevent look-ahead leakage."""
    sorted_df = cohort_df.sort_values("transaction_date").copy()
    split_idx = max(int(len(sorted_df) * train_ratio), 1)
    train_df = sorted_df.iloc[:split_idx].copy()
    test_df = sorted_df.iloc[split_idx:].copy()
    return train_df, test_df
