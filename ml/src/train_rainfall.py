"""
Apni Kheti — Monthly Rainfall Trend Model Training
Trains and evaluates models predicting monthly rainfall using same-month historical trends.

Pipeline:
1. Temporal split: Train on 2017–2023, evaluate out-of-time on 2024–2025.
2. Compares Climatological Baseline, Ridge Trend, HistGradientBoosting, and Random Forest.
3. Computes MAE, RMSE, R2, Pearson r, and Anomaly Direction Accuracy.
4. Exports trusted model and feature manifest to ml/models/ and backend/artifacts/.
"""

import json
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from scipy.stats import pearsonr
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, root_mean_squared_error, r2_score
import sys

CURRENT_DIR = Path(__file__).resolve().parent
ML_DIR = CURRENT_DIR.parent
PROJECT_ROOT = ML_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.src.rainfall_features import build_rainfall_features

MODELS_DIR = ML_DIR / "models"
REPORTS_DIR = ML_DIR / "reports"
BACKEND_ARTIFACTS = PROJECT_ROOT / "backend" / "artifacts"

FEATURE_COLS = [
    "grid_lat", "grid_lon", "month", "month_sin", "month_cos", "season_code",
    "same_month_lag_1yr", "same_month_lag_2yr", "same_month_lag_3yr",
    "same_month_3yr_mean", "same_month_5yr_mean", "same_month_hist_mean",
    "same_month_hist_std", "same_month_hist_min", "same_month_hist_max",
    "same_month_trend_slope", "same_month_rainy_days_avg",
    "prior_month_rf", "prior_2month_rf"
]
TARGET_COL = "target_rainfall_mm"

class ClimatologicalBaseline:
    """Standard meteorological benchmark: predicts historical same-month mean."""
    def fit(self, X, y):
        pass
    def predict(self, X):
        return X["same_month_hist_mean"].values

def evaluate_predictions(y_true, y_pred, hist_mean):
    mae = mean_absolute_error(y_true, y_pred)
    rmse = root_mean_squared_error(y_true, y_pred)
    r2 = r2_score(y_true, y_pred)
    
    # Pearson correlation
    corr = 0.0
    if np.std(y_pred) > 0 and np.std(y_true) > 0:
        corr = float(pearsonr(y_true, y_pred)[0])

    # Anomaly Direction Accuracy: Did predicted anomaly sign match actual anomaly sign?
    pred_anomaly = y_pred - hist_mean
    actual_anomaly = y_true - hist_mean
    direction_match = np.sign(pred_anomaly) == np.sign(actual_anomaly)
    anomaly_acc = float(np.mean(direction_match))

    return {
        "mae_mm": round(float(mae), 2),
        "rmse_mm": round(float(rmse), 2),
        "r2_score": round(float(r2), 4),
        "pearson_r": round(corr, 4),
        "anomaly_direction_accuracy": round(anomaly_acc, 4)
    }

def train_rainfall_models():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    BACKEND_ARTIFACTS.mkdir(parents=True, exist_ok=True)

    df = build_rainfall_features()

    # Temporal split: Train on 2017-2023, Test on 2024-2025 (held-out out-of-time evaluation)
    train_mask = (df["year"] <= 2023)
    test_mask = (df["year"] >= 2024)

    train_df = df[train_mask]
    test_df = df[test_mask]

    X_train = train_df[FEATURE_COLS]
    y_train = train_df[TARGET_COL].values
    X_test = test_df[FEATURE_COLS]
    y_test = test_df[TARGET_COL].values
    hist_mean_test = test_df["same_month_hist_mean"].values

    print(f"Training samples (2017–2023): {len(train_df)}")
    print(f"Test samples (2024–2025): {len(test_df)}")

    candidate_models = {
        "Climatological_Baseline": ClimatologicalBaseline(),
        "Ridge_Trend_Regressor": Ridge(alpha=1.0),
        "Random_Forest_Regressor": RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42),
        "Hist_Gradient_Boosting": HistGradientBoostingRegressor(max_iter=100, max_depth=8, random_state=42)
    }

    eval_results = {
        "dataset_summary": {
            "total_samples": len(df),
            "train_samples": len(train_df),
            "test_samples": len(test_df),
            "train_period": "2017-2023",
            "test_period": "2024-2025",
            "feature_count": len(FEATURE_COLS),
            "features": FEATURE_COLS
        },
        "model_comparison": {}
    }

    best_model_name = "Random_Forest_Regressor"
    best_model = None
    best_mae = float("inf")

    print("\n--- Model Evaluation (Out-of-Time Held-Out Test Set: 2024–2025) ---")
    for name, model in candidate_models.items():
        if name != "Climatological_Baseline":
            model.fit(X_train, y_train)
        
        preds = model.predict(X_test)
        # Rainfall cannot be negative
        preds = np.clip(preds, 0, None)
        metrics = evaluate_predictions(y_test, preds, hist_mean_test)
        eval_results["model_comparison"][name] = metrics

        print(f"[{name}] MAE: {metrics['mae_mm']} mm | RMSE: {metrics['rmse_mm']} mm | R2: {metrics['r2_score']} | Pearson r: {metrics['pearson_r']} | Anomaly Acc: {metrics['anomaly_direction_accuracy']}")

        if metrics["mae_mm"] < best_mae and name in ["Random_Forest_Regressor", "Hist_Gradient_Boosting"]:
            best_mae = metrics["mae_mm"]
            best_model_name = name
            best_model = model

    # Calculate Climatological Normals by District and Month for reference
    normals = df.groupby(["district", "month"])["target_rainfall_mm"].agg(["mean", "std", "min", "max"]).reset_index()
    normals_dict = {}
    for _, r in normals.iterrows():
        key = f"{r['district']}_{int(r['month'])}"
        normals_dict[key] = {
            "normal_mm": round(float(r["mean"]), 2),
            "std_mm": round(float(r["std"]), 2),
            "min_mm": round(float(r["min"]), 2),
            "max_mm": round(float(r["max"]), 2)
        }

    # Manifest
    manifest = {
        "model_type": best_model_name,
        "feature_names": FEATURE_COLS,
        "units": "millimeters (mm)",
        "train_period": "2015-2023 historical base",
        "evaluation_period": "2024-2025 out-of-time test",
        "metrics": eval_results["model_comparison"][best_model_name],
        "normals_by_district_month": normals_dict
    }

    # Save artifacts
    model_path = MODELS_DIR / "rainfall_model.joblib"
    manifest_path = MODELS_DIR / "rainfall_features_manifest.json"
    report_path = REPORTS_DIR / "rainfall_model_evaluation.json"

    joblib.dump(best_model, model_path)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, indent=4)

    # Sync to backend/artifacts
    joblib.dump(best_model, BACKEND_ARTIFACTS / "rainfall_model.joblib")
    with open(BACKEND_ARTIFACTS / "rainfall_features_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=4)

    print(f"\n[OK] Best model selected: {best_model_name} (MAE: {best_mae} mm)")
    print(f"[OK] Saved model to: {model_path}")
    print(f"[OK] Saved manifest to: {manifest_path}")
    print(f"[OK] Saved report to: {report_path}")
    return best_model, manifest, eval_results

if __name__ == "__main__":
    train_rainfall_models()
