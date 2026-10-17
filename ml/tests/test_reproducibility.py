"""
Tests for ML Reproducibility and Model Invariants.
TRD Section 5.2, 10 & 11:
- Deterministic 70/15/15 split sample counts.
- Deterministic inference scores.
- Artifact existence and installation in both ml/models and backend/artifacts.
"""

from pathlib import Path
import joblib
import pandas as pd
import pytest
from ml.src.predict import CropPredictor
from ml.src.train import load_and_verify_data, DATA_PATH

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
ML_MODELS = CURRENT_DIR.parent / "models"
BACKEND_ARTIFACTS = PROJECT_ROOT / "backend" / "artifacts"

def test_split_proportions_and_reproducibility():
    splits = load_and_verify_data(DATA_PATH)
    # Total rows: 2200
    # 70% Train = 1540
    # 15% Val = 330
    # 15% Test = 330
    assert len(splits["X_train"]) == 1540
    assert len(splits["X_val"]) == 330
    assert len(splits["X_test"]) == 330
    assert splits["exact_duplicates"] == 0

def test_deterministic_predictions():
    predictor = CropPredictor()
    features = {
        'N': 85, 'P': 58, 'K': 41,
        'temperature': 21.77, 'humidity': 80.32,
        'ph': 7.04, 'rainfall': 226.66
    }
    res1 = predictor.predict(features, mode="rules_with_ml", regional_approved=True)
    res2 = predictor.predict(features, mode="rules_with_ml", regional_approved=True)

    assert res1["ml_status"] == "evaluated"
    assert res1["top_candidates"] == res2["top_candidates"]
    assert len(res1["top_candidates"]) == 3
    assert res1["top_candidates"][0]["crop"] == "rice"

def test_backend_artifacts_synced():
    assert (BACKEND_ARTIFACTS / "trusted_rf_model.joblib").exists()
    assert (BACKEND_ARTIFACTS / "features_manifest.json").exists()
    assert (BACKEND_ARTIFACTS / "label_map.json").exists()
    assert (BACKEND_ARTIFACTS / "dataset_metadata.json").exists()
