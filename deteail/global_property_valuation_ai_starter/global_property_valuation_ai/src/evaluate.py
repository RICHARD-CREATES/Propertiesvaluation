import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from common import ROOT, load_data, save_json

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/processed/property_training.csv")
    args = ap.parse_args()
    path = Path(args.data); path = path if path.is_absolute() else ROOT / path
    df = load_data(path).sort_values("transaction_date")
    report = {"overall":{}, "by_country_asset":{}}
    for (country, asset), g in df.groupby(["country_code","asset_type"]):
        g = g.sort_values("transaction_date")
        split = max(int(len(g)*0.8),1)
        test = g.iloc[split:]
        if len(test) == 0: continue
        # Baseline: median price/sqm from training period only.
        baseline = g.iloc[:split]["price_per_sqm"].median()
        y = test["price_per_sqm"].values
        pred = np.full(len(test), baseline)
        key=f"{country}_{asset}"
        report["by_country_asset"][key] = {
            "test_rows":int(len(test)),
            "baseline_median_price_sqm":float(baseline),
            "mae":float(mean_absolute_error(y,pred)),
            "rmse":float(mean_squared_error(y,pred)**0.5),
            "median_ape":float(np.median(np.abs(y-pred)/y)*100),
            "r2":float(r2_score(y,pred)) if len(y)>1 else None
        }
    save_json(report, ROOT/"reports"/"baseline_evaluation.json")
    print(json.dumps(report, indent=2))
if __name__ == "__main__": main()
