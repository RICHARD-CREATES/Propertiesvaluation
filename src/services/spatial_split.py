"""
Spatially Aware Train / Validation / Test Splitter & Geographic Leakage Auditor (Milestone 7 - Task 2).

Ensures nearby properties and micro-markets never appear in both training and testing splits
by building connected Haversine spatial clusters before assigning split groups.
"""
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Tuple
import numpy as np

from src.services.location_intelligence import haversine_km


class SpatialLeakageError(ValueError):
    """Raised when geographic or transaction ID overlap is detected across dataset splits."""


def assign_spatial_clusters(
    records: List[Dict[str, Any]],
    cluster_radius_km: float = 3.0,
) -> List[Dict[str, Any]]:
    """
    Groups transactions into connected spatial micro-market components where any two points
    within `cluster_radius_km` belong to the same `geo_cluster_id`.
    """
    n = len(records)
    if n == 0:
        return []

    visited = [False] * n
    clustered = [dict(r) for r in records]
    cluster_idx = 0

    for i in range(n):
        if visited[i]:
            continue
        cluster_idx += 1
        cluster_id = f"GEO_C{cluster_idx:04d}"
        queue = [i]
        visited[i] = True

        while queue:
            curr = queue.pop(0)
            clustered[curr]["geo_cluster_id"] = cluster_id
            lat1, lon1 = float(clustered[curr]["latitude"]), float(clustered[curr]["longitude"])
            for j in range(n):
                if not visited[j]:
                    lat2, lon2 = float(clustered[j]["latitude"]), float(clustered[j]["longitude"])
                    if haversine_km(lat1, lon1, lat2, lon2) <= cluster_radius_km:
                        visited[j] = True
                        queue.append(j)

    return clustered


def verify_no_geographic_leakage(
    train_records: List[Dict[str, Any]],
    val_records: List[Dict[str, Any]],
    test_records: List[Dict[str, Any]],
    min_separation_km: float = 2.0,
) -> Dict[str, Any]:
    """
    Audits splits for ID leakage, shared geo-cluster leakage, and sub-threshold proximity leakage.
    Raises SpatialLeakageError on any violation.
    """
    splits = {"train": train_records, "validation": val_records, "test": test_records}

    # 1. Transaction ID & Cluster ID overlap check
    seen_ids: Dict[str, str] = {}
    seen_clusters: Dict[str, str] = {}
    for split_name, rows in splits.items():
        for r in rows:
            tid = str(r.get("transaction_id") or r.get("id"))
            cid = r.get("geo_cluster_id")
            if tid in seen_ids and seen_ids[tid] != split_name:
                raise SpatialLeakageError(f"Transaction ID leakage: '{tid}' appears in both '{seen_ids[tid]}' and '{split_name}'.")
            seen_ids[tid] = split_name

            if cid:
                if cid in seen_clusters and seen_clusters[cid] != split_name:
                    raise SpatialLeakageError(
                        f"Micro-market cluster leakage: '{cid}' appears in both '{seen_clusters[cid]}' and '{split_name}'."
                    )
                seen_clusters[cid] = split_name

    # 2. Pairwise boundary distance check (Train vs Test & Train vs Val)
    min_train_test_km: Optional[float] = None
    for tr in train_records:
        for te in test_records:
            d = haversine_km(float(tr["latitude"]), float(tr["longitude"]), float(te["latitude"]), float(te["longitude"]))
            if min_train_test_km is None or d < min_train_test_km:
                min_train_test_km = d
            if d < min_separation_km:
                raise SpatialLeakageError(
                    f"Geographic boundary leakage: train tx ({tr.get('locality')}) and test tx ({te.get('locality')}) "
                    f"are only {d:.2f} km apart (< {min_separation_km} km threshold)."
                )

    min_train_val_km: Optional[float] = None
    for tr in train_records:
        for va in val_records:
            d = haversine_km(float(tr["latitude"]), float(tr["longitude"]), float(va["latitude"]), float(va["longitude"]))
            if min_train_val_km is None or d < min_train_val_km:
                min_train_val_km = d
            if d < min_separation_km:
                raise SpatialLeakageError(
                    f"Geographic boundary leakage: train tx ({tr.get('locality')}) and validation tx ({va.get('locality')}) "
                    f"are only {d:.2f} km apart (< {min_separation_km} km threshold)."
                )

    return {
        "leakage_detected": False,
        "min_train_test_separation_km": round(min_train_test_km, 2) if min_train_test_km is not None else None,
        "min_train_val_separation_km": round(min_train_val_km, 2) if min_train_val_km is not None else None,
        "enforced_threshold_km": min_separation_km,
    }


def _summarize_split_geography(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {
            "transaction_count": 0,
            "states": [],
            "cities": [],
            "localities": [],
            "property_type_distribution": {},
            "date_distribution": None,
        }

    states = sorted({str(r.get("state", "Unknown")) for r in rows})
    cities = sorted({str(r.get("city", "Unknown")) for r in rows})
    localities = sorted({str(r.get("locality", "Unknown")) for r in rows})
    prop_counts = dict(Counter(str(r.get("property_type", "unknown")) for r in rows))
    dates = sorted(str(r.get("transaction_date"))[:10] for r in rows if r.get("transaction_date"))

    return {
        "transaction_count": len(rows),
        "states": states,
        "cities": cities,
        "localities": localities,
        "geo_clusters": sorted({str(r.get("geo_cluster_id")) for r in rows if r.get("geo_cluster_id")}),
        "property_type_distribution": prop_counts,
        "date_distribution": {"earliest": dates[0], "latest": dates[-1]} if dates else None,
    }


def create_spatial_splits(
    records: List[Dict[str, Any]],
    train_ratio: float = 0.60,
    val_ratio: float = 0.20,
    test_ratio: float = 0.20,
    cluster_radius_km: float = 3.0,
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Performs zero-leakage spatially clustered splitting across Train / Validation / Test.
    """
    if len(records) < 3:
        return {
            "status": "INSUFFICIENT_CLUSTERS",
            "message": "At least 3 distinct transactions in separate spatial clusters are required to create train/val/test splits.",
            "train": [],
            "validation": [],
            "test": records,
            "leakage_audit": {"leakage_detected": False},
            "split_report": {
                "train_geography": _summarize_split_geography([]),
                "validation_geography": _summarize_split_geography([]),
                "testing_geography": _summarize_split_geography(records),
            },
        }

    clustered = assign_spatial_clusters(records, cluster_radius_km=cluster_radius_km)
    by_cluster: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in clustered:
        by_cluster[r["geo_cluster_id"]].append(r)

    cluster_ids = list(by_cluster.keys())
    if len(cluster_ids) < 2:
        return {
            "status": "SINGLE_CLUSTER_WARNING",
            "message": (
                f"All {len(records)} transactions fall inside 1 geographic cluster (<={cluster_radius_km} km). "
                "Assigning all to held-out 'test' to guarantee zero spatial leakage."
            ),
            "train": [],
            "validation": [],
            "test": clustered,
            "leakage_audit": {"leakage_detected": False},
            "split_report": {
                "train_geography": _summarize_split_geography([]),
                "validation_geography": _summarize_split_geography([]),
                "testing_geography": _summarize_split_geography(clustered),
            },
        }

    rng = np.random.default_rng(seed)
    shuffled_clusters = list(rng.permutation(cluster_ids))

    total_clusters = len(shuffled_clusters)
    n_test = max(1, round(total_clusters * test_ratio))
    n_val = max(1, round(total_clusters * val_ratio)) if total_clusters >= 3 else 0
    n_train = max(1, total_clusters - n_test - n_val)

    train_c = set(shuffled_clusters[:n_train])
    val_c = set(shuffled_clusters[n_train : n_train + n_val])
    test_c = set(shuffled_clusters[n_train + n_val :])

    train_rows = [dict(r, split_group="train") for c in train_c for r in by_cluster[c]]
    val_rows = [dict(r, split_group="validation") for c in val_c for r in by_cluster[c]]
    test_rows = [dict(r, split_group="test") for c in test_c for r in by_cluster[c]]

    # Audit against cluster_radius_km boundary
    audit = verify_no_geographic_leakage(
        train_rows, val_rows, test_rows, min_separation_km=min(cluster_radius_km, 2.0)
    )

    return {
        "status": "SUCCESS",
        "cluster_count": total_clusters,
        "cluster_radius_km": cluster_radius_km,
        "train": train_rows,
        "validation": val_rows,
        "test": test_rows,
        "leakage_audit": audit,
        "split_report": {
            "train_geography": _summarize_split_geography(train_rows),
            "validation_geography": _summarize_split_geography(val_rows),
            "testing_geography": _summarize_split_geography(test_rows),
        },
    }
