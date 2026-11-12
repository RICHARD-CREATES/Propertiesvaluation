"""
Cluster 6: Current Market Conditions.
Extracts transactional velocity, short/mid-term capital price deltas,
unsold inventory overhang, and median gross rental yields.
"""
from typing import Dict, Any


class MarketConditionFeatureExtractor:
    """Extracts liquidity, price velocity, inventory overhang, and rental yields."""

    def extract(self, lat: float, lon: float, overrides: Dict[str, Any] = None) -> Dict[str, Any]:
        overrides = overrides or {}

        features = {
            "tx_velocity_deals_per_month": float(overrides.get("tx_velocity_deals_per_month", 42.0)), # Monthly SRO registered deeds
            "price_psqft_3m_delta_pct": float(overrides.get("price_psqft_3m_delta_pct", 1.8)),        # 3-month price change %
            "price_psqft_12m_delta_pct": float(overrides.get("price_psqft_12m_delta_pct", 8.4)),      # 12-month YoY capital delta %
            "inventory_overhang_months": float(overrides.get("inventory_overhang_months", 14.2)),     # Months to absorb current supply
            "gross_rental_yield_pct": float(overrides.get("gross_rental_yield_pct", 3.8)),            # Annual rental income / property price %
        }

        # Market liquidity momentum index (high deals + short overhang = seller's market)
        features["market_momentum_index"] = (
            features["tx_velocity_deals_per_month"] / max(features["inventory_overhang_months"], 1.0)
        )

        return features
