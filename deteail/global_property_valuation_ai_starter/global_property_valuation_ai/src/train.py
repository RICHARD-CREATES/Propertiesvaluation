import argparse, json, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder
from sklearn.ensemble import HistGradientBoostingRegressor, ExtraTreesRegressor, RandomForestRegressor
from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from common import ROOT, CONFIG, load_data, feature_list, save_json

try:
    from catboost import CatBoostRegressor
    HAS_CATBOOST = True
except Exception:
    HAS_CATBOOST = False

MIN_ROWS_CLUSTER = 300
RANDOM_STATE = 42

def make_model(X):
    cats = X.select_dtypes(include=["object", "category", "string"]).columns.tolist()
    nums = [c for c in X.columns if c not in cats]
    transformers = []
    if nums:
        transformers.append(("num", Pipeline([("impute", SimpleImputer(strategy="median"))]), nums))
    if cats:
        transformers.append(("cat", Pipeline([
            ("impute", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=5, sparse_output=False))
        ]), cats))
    prep = ColumnTransformer(transformers, remainder="drop")
    model = HistGradientBoostingRegressor(max_iter=250, learning_rate=0.06, l2_regularization=2.0, random_state=RANDOM_STATE)
    return Pipeline([("prep", prep), ("model", model)])

def make_catboost(X):
    cat_cols = X.select_dtypes(include=["object", "category", "string"]).columns.tolist()
    X2 = X.copy()
    for c in cat_cols:
        X2[c] = X2[c].fillna("__MISSING__").astype(str)
    model = CatBoostRegressor(
        iterations=900, depth=8, learning_rate=0.035, loss_function="MAE",
        eval_metric="MAE", verbose=False, random_seed=RANDOM_STATE,
        allow_writing_files=False
    )
    return model, X2, cat_cols

def train_one(X, y, path):
    if HAS_CATBOOST:
        model, X2, cats = make_catboost(X)
        model.fit(X2, y, cat_features=cats)
        joblib.dump({"kind":"catboost", "model":model, "features":list(X.columns), "categorical":cats}, path)
        return model, X2, "catboost"
    model = make_model(X)
    model.fit(X, y)
    joblib.dump({"kind":"sklearn_pipeline", "model":model, "features":list(X.columns)}, path)
    return model, X, "hist_gradient_boosting"

def predict_bundle(bundle, X):
    if bundle["kind"] == "catboost":
        X = X.copy()
        for c in bundle["categorical"]:
            if c in X: X[c] = X[c].fillna("__MISSING__").astype(str)
        return bundle["model"].predict(X[bundle["features"]])
    return bundle["model"].predict(X[bundle["features"]])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default="data/processed/property_training.csv")
    ap.add_argument("--min-rows", type=int, default=MIN_ROWS_CLUSTER)
    args = ap.parse_args()
    data_path = Path(args.data)
    if not data_path.is_absolute(): data_path = ROOT / data_path
    df = load_data(data_path)
    # Country/asset cohorts prevent meaningless raw price mixing across currencies and asset classes.
    # Each cohort is trained separately. The label is log local-currency price per sqm.
    models_dir = ROOT / "models"; models_dir.mkdir(exist_ok=True)
    reports_dir = ROOT / "reports"; reports_dir.mkdir(exist_ok=True)
    summary = {"rows_after_quality_filters": int(len(df)), "clusters": {}, "cohorts": {}}
    for (country, asset), cohort in df.groupby(["country_code", "asset_type"]):
        cohort = cohort.sort_values("transaction_date").copy()
        cohort_key = f"{country}_{asset}".replace("/", "_")
        y = np.log1p(cohort["price_per_sqm"].astype(float))
        cohort_summary = {"rows": int(len(cohort)), "specialists": {}}
        specialist_predictions = pd.DataFrame(index=cohort.index)
        for cluster in CONFIG["clusters"]:
            feats = feature_list(cluster, cohort)
            if len(cohort) < args.min_rows or len(feats) < 1:
                cohort_summary["specialists"][cluster] = {"status":"skipped", "reason":"insufficient rows or usable features", "features":feats}
                continue
            X = cohort[feats].copy()
            # A temporal holdout: final 20% by date. No random split for headline validation.
            split = max(int(len(cohort) * 0.8), 1)
            X_train, X_test = X.iloc[:split], X.iloc[split:]
            y_train, y_test = y.iloc[:split], y.iloc[split:]
            if len(X_test) < 20:
                cohort_summary["specialists"][cluster] = {"status":"skipped", "reason":"fewer than 20 temporal holdout rows", "features":feats}
                continue
            model_path = models_dir / f"{cohort_key}__{cluster}.joblib"
            model, fitted_X, kind = train_one(X_train, y_train, model_path)
            if kind == "catboost":
                for c in fitted_X.select_dtypes(include=["object","category","string"]).columns:
                    X_test.loc[:, c] = X_test[c].fillna("__MISSING__").astype(str)
            pred = model.predict(X_test)
            actual_price = np.expm1(y_test)
            pred_price = np.expm1(pred)
            metrics = {
                "mae_price_per_sqm": float(mean_absolute_error(actual_price, pred_price)),
                "rmse_log_price_per_sqm": float(mean_squared_error(y_test, pred, squared=False)),
                "r2_log_price_per_sqm": float(r2_score(y_test, pred)),
                "holdout_rows": int(len(X_test))
            }
            cohort_summary["specialists"][cluster] = {"status":"trained", "model":str(model_path.relative_to(ROOT)), "kind":kind, "features":feats, "metrics":metrics}
        # Final generalist model uses the full schema features that exist; specialist model files remain independently deployable.
        all_features = sorted(set(c for cols in CONFIG["clusters"].values() for c in cols if c in cohort.columns))
        if len(cohort) >= args.min_rows and all_features:
            Xall = cohort[all_features].copy()
            general_path = models_dir / f"{cohort_key}__generalist.joblib"
            general_model, _, general_kind = train_one(Xall, y, general_path)
            cohort_summary["generalist"] = {"status":"trained", "model":str(general_path.relative_to(ROOT)), "kind":general_kind, "features":all_features}
        else:
            cohort_summary["generalist"] = {"status":"skipped", "reason":"insufficient rows/features"}
        summary["cohorts"][cohort_key] = cohort_summary
    save_json(summary, reports_dir / "training_summary.json")
    print(json.dumps(summary, indent=2))
    if not summary["cohorts"]:
        raise SystemExit("No trainable country/asset cohorts found.")

if __name__ == "__main__":
    main()
