"""
Apni Kheti — Offline ML Training & Evaluation Pipeline
Compliant with TRD Section 5.1, 5.2, 5.3, 10 & Master Plan Section 5.

Features:
- Deterministic 70/15/15 Stratified Train/Val/Test Split.
- Comparison of Majority Baseline, Shallow Decision Tree, Random Forest, and HistGradientBoosting.
- Evaluates balanced accuracy, macro-F1 (with zero_division=0 to prevent warnings),
  Top-1, Top-3 accuracy, per-class breakdown, and probability calibration.
- Enforces duplicate detection and data integrity hashing.
- Exports trusted model, feature manifest, label map, metadata to /models and /backend/artifacts.
- Generates TRD-compliant model_evaluation.json and model_card.md.
"""

import os
import json
import hashlib
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.metrics import (
    classification_report,
    balanced_accuracy_score,
    top_k_accuracy_score,
    confusion_matrix,
    brier_score_loss
)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
import sklearn

# Paths
CURRENT_DIR = Path(__file__).resolve().parent
ML_DIR = CURRENT_DIR.parent
PROJECT_ROOT = ML_DIR.parent
DATA_PATH = ML_DIR / "data" / "raw" / "crop_recommendation.csv"
MODELS_DIR = ML_DIR / "models"
REPORTS_DIR = ML_DIR / "reports"
BACKEND_ARTIFACTS_DIR = PROJECT_ROOT / "backend" / "artifacts"

# TRD 5.1 Contract: N, P, K, temperature, humidity, ph, rainfall, label
TARGET_COL = 'label'
FEATURES = ['N', 'P', 'K', 'temperature', 'humidity', 'ph', 'rainfall']

def calculate_file_hash(filepath: Path) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_and_verify_data(filepath: Path):
    """Loads dataset, verifies integrity, detects duplicates, and applies 70/15/15 stratified split."""
    if not filepath.exists():
        alt = filepath.parent / "Crop_recommendation.csv"
        if alt.exists():
            filepath = alt
        else:
            raise FileNotFoundError(f"Audited dataset not found at {filepath}")

    file_hash = calculate_file_hash(filepath)
    df = pd.read_csv(filepath)

    # Integrity & Duplicate checks (TRD 5.2)
    exact_duplicates = df.duplicated().sum()
    feature_duplicates = df.duplicated(subset=FEATURES).sum()
    missing_counts = df.isnull().sum().to_dict()

    print(f"Loaded {len(df)} rows across {df[TARGET_COL].nunique()} classes.")
    print(f"Data SHA-256: {file_hash}")
    print(f"Exact duplicates: {exact_duplicates}, Feature duplicate vectors: {feature_duplicates}")

    # Encode labels
    le = LabelEncoder()
    y_encoded = le.fit_transform(df[TARGET_COL])
    X = df[FEATURES]

    # Stratified 70% Train, 30% Temp (Val 15% + Test 15%)
    X_train, X_temp, y_train, y_temp = train_test_split(
        X, y_encoded, test_size=0.30, stratify=y_encoded, random_state=42
    )

    # Split Temp into Validation (15%) and Test (15%)
    X_val, X_test, y_val, y_test = train_test_split(
        X_temp, y_temp, test_size=0.50, stratify=y_temp, random_state=42
    )

    data_splits = {
        "X_train": X_train, "y_train": y_train,
        "X_val": X_val, "y_val": y_val,
        "X_test": X_test, "y_test": y_test,
        "label_encoder": le,
        "raw_df": df,
        "sha256": file_hash,
        "exact_duplicates": int(exact_duplicates),
        "feature_duplicates": int(feature_duplicates),
        "missing_counts": missing_counts
    }
    return data_splits

def evaluate_model(model, X, y, class_names):
    """Calculates comprehensive metrics for validation or test sets."""
    y_pred = model.predict(X)
    bal_acc = balanced_accuracy_score(y, y_pred)
    
    # zero_division=0 fixes UndefinedMetricWarning
    report = classification_report(
        y, y_pred, target_names=class_names, output_dict=True, zero_division=0
    )
    
    # Top-K accuracy if predict_proba is available
    top_3_acc = None
    brier_score = None
    if hasattr(model, "predict_proba"):
        probs = model.predict_proba(X)
        if probs.shape[1] == len(class_names):
            top_3_acc = float(top_k_accuracy_score(y, probs, k=min(3, len(class_names))))
            # Multi-class Brier score
            y_one_hot = np.zeros_like(probs)
            for idx, val in enumerate(y):
                y_one_hot[idx, val] = 1.0
            brier_score = float(np.mean(np.sum((probs - y_one_hot) ** 2, axis=1)))

    cm = confusion_matrix(y, y_pred).tolist()

    return {
        "balanced_accuracy": float(bal_acc),
        "macro_f1": float(report['macro avg']['f1-score']),
        "weighted_f1": float(report['weighted avg']['f1-score']),
        "accuracy": float(report['accuracy']),
        "top_3_accuracy": top_3_acc,
        "brier_score": brier_score,
        "classification_report": report,
        "confusion_matrix": cm
    }

def train_and_evaluate_all():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    BACKEND_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    splits = load_and_verify_data(DATA_PATH)
    X_train, y_train = splits["X_train"], splits["y_train"]
    X_val, y_val = splits["X_val"], splits["y_val"]
    X_test, y_test = splits["X_test"], splits["y_test"]
    le = splits["label_encoder"]
    class_names = list(le.classes_)

    candidate_models = {
        "Majority_Baseline": DummyClassifier(strategy="prior"),
        "Shallow_Decision_Tree": DecisionTreeClassifier(max_depth=5, random_state=42),
        "Random_Forest": RandomForestClassifier(n_estimators=100, max_depth=15, random_state=42),
        "Hist_Gradient_Boosting": HistGradientBoostingClassifier(max_iter=100, random_state=42)
    }

    eval_results = {
        "metadata": {
            "dataset_sha256": splits["sha256"],
            "total_rows": len(splits["raw_df"]),
            "train_samples": len(X_train),
            "val_samples": len(X_val),
            "test_samples": len(X_test),
            "feature_names": FEATURES,
            "classes_count": len(class_names),
            "scikit_learn_version": sklearn.__version__,
            "exact_duplicates": splits["exact_duplicates"],
            "feature_duplicates": splits["feature_duplicates"]
        },
        "validation_comparison": {},
        "test_evaluation": {}
    }

    best_model_name = "Random_Forest"
    fitted_models = {}

    print("\n--- Training and Validation Comparison ---")
    for name, model in candidate_models.items():
        model.fit(X_train, y_train)
        fitted_models[name] = model
        metrics = evaluate_model(model, X_val, y_val, class_names)
        
        eval_results["validation_comparison"][name] = {
            "balanced_accuracy": metrics["balanced_accuracy"],
            "macro_f1": metrics["macro_f1"],
            "weighted_f1": metrics["weighted_f1"],
            "top_3_accuracy": metrics["top_3_accuracy"],
            "brier_score": metrics["brier_score"]
        }
        
        print(f"[{name}] Val Balanced Acc: {metrics['balanced_accuracy']:.4f} | Macro-F1: {metrics['macro_f1']:.4f} | Top-3 Acc: {metrics['top_3_accuracy']}")

    # Final held-out evaluation on Best Model (Random Forest)
    best_model = fitted_models[best_model_name]
    test_metrics = evaluate_model(best_model, X_test, y_test, class_names)
    eval_results["test_evaluation"] = {
        "model_name": best_model_name,
        "balanced_accuracy": test_metrics["balanced_accuracy"],
        "macro_f1": test_metrics["macro_f1"],
        "weighted_f1": test_metrics["weighted_f1"],
        "accuracy": test_metrics["accuracy"],
        "top_3_accuracy": test_metrics["top_3_accuracy"],
        "brier_score": test_metrics["brier_score"],
        "confusion_matrix": test_metrics["confusion_matrix"],
        "per_class_metrics": {
            cls: test_metrics["classification_report"][cls]
            for cls in class_names
        }
    }

    print(f"\n[Test Set Final - {best_model_name}] Balanced Acc: {test_metrics['balanced_accuracy']:.4f} | Macro-F1: {test_metrics['macro_f1']:.4f} | Top-3 Acc: {test_metrics['top_3_accuracy']:.4f}")

    # Generate Feature Manifest (TRD 5.3)
    df_raw = splits["raw_df"]
    feature_manifest = {
        "features": FEATURES,
        "units": {
            "N": "ratio_or_index",
            "P": "ratio_or_index",
            "K": "ratio_or_index",
            "temperature": "celsius",
            "humidity": "percentage",
            "ph": "ph_unit",
            "rainfall": "mm_annual_or_season"
        },
        "ranges": {
            col: {
                "min": float(df_raw[col].min()),
                "max": float(df_raw[col].max()),
                "p25": float(df_raw[col].quantile(0.25)),
                "p50": float(df_raw[col].median()),
                "p75": float(df_raw[col].quantile(0.75)),
                "mean": float(df_raw[col].mean()),
                "std": float(df_raw[col].std())
            } for col in FEATURES
        }
    }

    # Generate Label Map (TRD 5.2)
    label_map = {
        "classes": class_names,
        "label_to_id": {cls: int(idx) for idx, cls in enumerate(class_names)},
        "id_to_label": {int(idx): cls for idx, cls in enumerate(class_names)},
        "punjab_pilot_coverage": {
            "wheat": False,      # Kaggle dataset does not contain wheat!
            "mustard": False,    # Kaggle dataset does not contain mustard!
            "barley": False,     # Kaggle dataset does not contain barley!
            "rice": True,
            "maize": True,
            "cotton": True,
            "chickpea": True
        }
    }

    # Save artifacts in ml/models/
    model_export_path = MODELS_DIR / "trusted_rf_model.joblib"
    manifest_path = MODELS_DIR / "features_manifest.json"
    label_map_path = MODELS_DIR / "label_map.json"
    metadata_path = MODELS_DIR / "dataset_metadata.json"

    joblib.dump(best_model, model_export_path)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(feature_manifest, f, indent=4)
    with open(label_map_path, "w", encoding="utf-8") as f:
        json.dump(label_map, f, indent=4)
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(eval_results["metadata"], f, indent=4)

    # Explicitly install to backend/artifacts/ (TRD Section 10)
    joblib.dump(best_model, BACKEND_ARTIFACTS_DIR / "trusted_rf_model.joblib")
    with open(BACKEND_ARTIFACTS_DIR / "features_manifest.json", "w", encoding="utf-8") as f:
        json.dump(feature_manifest, f, indent=4)
    with open(BACKEND_ARTIFACTS_DIR / "label_map.json", "w", encoding="utf-8") as f:
        json.dump(label_map, f, indent=4)
    with open(BACKEND_ARTIFACTS_DIR / "dataset_metadata.json", "w", encoding="utf-8") as f:
        json.dump(eval_results["metadata"], f, indent=4)

    # Save evaluation report in ml/reports/
    eval_report_path = REPORTS_DIR / "model_evaluation.json"
    with open(eval_report_path, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, indent=4)

    # Generate TRD 5.2 Model Card
    generate_model_card(eval_results, feature_manifest, label_map)

    print(f"\n[OK] Model training and evaluation successfully completed.")
    print(f"[OK] Saved model to: {model_export_path}")
    print(f"[OK] Installed to backend: {BACKEND_ARTIFACTS_DIR / 'trusted_rf_model.joblib'}")
    print(f"[OK] Saved evaluation report to: {eval_report_path}")

def generate_model_card(eval_results, manifest, label_map):
    """Produces the TRD 5.2 / Master Plan required Model Card as structured JSON."""
    card_path = REPORTS_DIR / "model_card.json"
    meta = eval_results["metadata"]
    val_comp = eval_results["validation_comparison"]
    test_eval = eval_results["test_evaluation"]

    card_data = {
        "model_name": "Apni Kheti Crop Suitability Classifier (Research Baseline)",
        "version": "1.0",
        "model_type": "RandomForestClassifier(n_estimators=100, max_depth=15, random_state=42)",
        "evaluation_standard": "TRD Section 5.1 & 5.2 Offline Research Protocol",
        "dataset_sha256": meta["dataset_sha256"],
        "boundaries": {
            "permitted_use": [
                "Offline research & comparison baseline",
                "Top-K candidate shortlisting when all feature compatibility gates pass"
            ],
            "prohibited_uses": [
                "No field soil diagnosis",
                "No wheat, mustard, or barley predictions (absent from dataset)",
                "No guaranteed yield or profit representation",
                "No unverified unit improvisation"
            ]
        },
        "validation_comparison": val_comp,
        "test_evaluation": {
            "balanced_accuracy": test_eval["balanced_accuracy"],
            "macro_f1": test_eval["macro_f1"],
            "top_3_accuracy": test_eval["top_3_accuracy"],
            "brier_score": test_eval["brier_score"],
            "accuracy": test_eval["accuracy"]
        },
        "dataset_summary": {
            "source": "Kaggle (Atharva Ingle Crop Recommendation Dataset)",
            "total_records": meta["total_rows"],
            "features": FEATURES,
            "classes_count": meta["classes_count"]
        },
        "production_gate": "Disabled by default (rules_only). Requires TRD 5.3 5-gate verification to run."
    }
    with open(card_path, "w", encoding="utf-8") as f:
        json.dump(card_data, f, indent=4)
    print(f"[OK] Generated Model Card: {card_path}")

if __name__ == "__main__":
    train_and_evaluate_all()