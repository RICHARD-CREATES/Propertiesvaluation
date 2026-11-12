import argparse, json
from pathlib import Path
import joblib, pandas as pd, numpy as np
from common import ROOT

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--model", required=True, help="Path relative to project root or absolute")
    ap.add_argument("--input", required=True, help="CSV containing one or more property rows")
    ap.add_argument("--output", default="reports/predictions.csv")
    a=ap.parse_args()
    mp=Path(a.model); mp=mp if mp.is_absolute() else ROOT/mp
    ip=Path(a.input); ip=ip if ip.is_absolute() else ROOT/ip
    op=Path(a.output); op=op if op.is_absolute() else ROOT/op
    bundle=joblib.load(mp); X=pd.read_csv(ip)
    missing=[f for f in bundle["features"] if f not in X]
    if missing: raise ValueError(f"Input missing model features: {missing}")
    X=X[bundle["features"]].copy()
    if bundle["kind"]=="catboost":
        for c in bundle["categorical"]:
            X[c]=X[c].fillna("__MISSING__").astype(str)
    pred_log=bundle["model"].predict(X)
    out=pd.DataFrame({"predicted_price_per_sqm_local_currency":np.expm1(pred_log)})
    out.to_csv(op,index=False)
    print(f"Wrote {op}")
if __name__=="__main__": main()
