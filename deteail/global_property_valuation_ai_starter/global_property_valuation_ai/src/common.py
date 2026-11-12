from pathlib import Path
import json
import yaml
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = yaml.safe_load((ROOT / "configs" / "schema.yaml").read_text())

def load_data(path):
    df = pd.read_csv(path, low_memory=False)
    required = ["sale_price", "currency", "country_code", "asset_type", "transaction_date"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    df["sale_price"] = pd.to_numeric(df["sale_price"], errors="coerce")
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce", utc=True)
    df["country_code"] = df["country_code"].astype("string").str.upper()
    df["asset_type"] = df["asset_type"].astype("string").str.lower()
    area = pd.to_numeric(df.get("built_area_sqm"), errors="coerce") if "built_area_sqm" in df else pd.Series(np.nan, index=df.index)
    land = pd.to_numeric(df.get("land_area_sqm"), errors="coerce") if "land_area_sqm" in df else pd.Series(np.nan, index=df.index)
    # Use built area for buildings, land area for land; retain area basis explicitly.
    is_land = df["asset_type"].eq("land")
    df["valuation_area_sqm"] = np.where(is_land, land, area)
    df["price_per_sqm"] = df["sale_price"] / df["valuation_area_sqm"]
    df = df.replace([np.inf, -np.inf], np.nan)
    df = df.dropna(subset=["sale_price", "price_per_sqm", "transaction_date", "country_code", "asset_type"])
    df = df[(df["sale_price"] > 0) & (df["price_per_sqm"] > 0) & (df["valuation_area_sqm"] > 0)]
    return df

def feature_list(cluster, df):
    cols = CONFIG["clusters"][cluster]
    return [c for c in cols if c in df.columns and df[c].notna().sum() > 0 and df[c].nunique(dropna=True) > 1]

def save_json(obj, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, indent=2, default=str))
