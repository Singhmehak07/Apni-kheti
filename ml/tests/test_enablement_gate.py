"""
Tests for TRD Section 5.3 Online Model Enablement Gate.
TRD 5.3 & 11:
- Mode 'rules_only' default skips ML execution.
- Regional evaluation gate requirement.
- Out-of-Distribution (OOD) feature rejection.
- Crops absent from dataset labels (Wheat, Mustard, Barley).
- Corrupted/untrusted artifact behavior.
"""

from pathlib import Path
import pytest
from ml.src.predict import CropPredictor

@pytest.fixture
def predictor():
    return CropPredictor()

@pytest.fixture
def base_features():
    return {
        'N': 70, 'P': 40, 'K': 40,
        'temperature': 25.0, 'humidity': 75.0,
        'ph': 6.8, 'rainfall': 150.0
    }

def test_default_mode_rules_only_skips_ml(predictor, base_features):
    result = predictor.predict(base_features) # Default mode is rules_only
    assert result["ml_status"] == "skipped"
    assert "MODE_RULES_ONLY_ACTIVE" in result["ml_skip_reasons"]
    assert result["top_candidates"] == []

def test_unapproved_regional_evaluation_skips_ml(predictor, base_features):
    result = predictor.predict(base_features, mode="rules_with_ml", regional_approved=False)
    assert result["ml_status"] == "skipped"
    assert "REGIONAL_EVALUATION_NOT_APPROVED_FOR_FIELD_DEPLOYMENT" in result["ml_skip_reasons"]

def test_unsupported_crop_label_flagged(predictor, base_features):
    # TRD 5.1 & Master Plan: Dataset has NO wheat, mustard, or barley.
    for unsupported_crop in ["wheat", "mustard", "barley"]:
        result = predictor.predict(
            base_features,
            mode="rules_with_ml",
            regional_approved=True,
            candidate_crop=unsupported_crop
        )
        assert result["ml_status"] == "skipped"
        assert any(f"CROP_NOT_IN_MODEL_LABEL_SET:{unsupported_crop}" in r for r in result["ml_skip_reasons"])

def test_out_of_distribution_ph(predictor, base_features):
    # Soil pH > 11 or < 3 is impossible or extreme OOD
    base_features['ph'] = 13.5
    result = predictor.predict(base_features, mode="rules_with_ml", regional_approved=True)
    assert result["ml_status"] == "skipped"
    assert any("OUT_OF_DISTRIBUTION_INPUTS" in r for r in result["ml_skip_reasons"])

def test_negative_rainfall_rejected(predictor, base_features):
    base_features['rainfall'] = -10.0
    result = predictor.predict(base_features, mode="rules_with_ml", regional_approved=True)
    assert result["ml_status"] == "skipped"
    assert any("OUT_OF_DISTRIBUTION_INPUTS" in r for r in result["ml_skip_reasons"])

def test_corrupted_model_fallback():
    # Point predictor to an empty directory
    empty_dir = Path("scratch_empty_model_dir")
    empty_dir.mkdir(exist_ok=True)
    try:
        broken_predictor = CropPredictor(model_dir=empty_dir)
        features = {'N': 50, 'P': 50, 'K': 50, 'temperature': 20, 'humidity': 50, 'ph': 7, 'rainfall': 100}
        result = broken_predictor.predict(features, mode="rules_with_ml", regional_approved=True)
        assert result["ml_status"] == "skipped"
        assert "TRUSTED_ARTIFACT_MISSING_OR_CORRUPT" in result["ml_skip_reasons"]
    finally:
        if empty_dir.exists():
            empty_dir.rmdir()
