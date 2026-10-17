"""
Tests for ML Feature Contract adherence.
TRD Section 5.1, 5.3 & 11:
- Exact schema / order / units.
- Missing feature rejection.
- Type integrity and non-numeric value rejection.
"""

import json
from pathlib import Path
import pytest
from ml.src.predict import CropPredictor

CURRENT_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = CURRENT_DIR.parent / "models" / "features_manifest.json"

@pytest.fixture
def predictor():
    return CropPredictor()

@pytest.fixture
def valid_features():
    return {
        'N': 90,
        'P': 42,
        'K': 43,
        'temperature': 20.88,
        'humidity': 82.00,
        'ph': 6.50,
        'rainfall': 202.94
    }

def test_feature_manifest_schema():
    assert MANIFEST_PATH.exists(), "features_manifest.json must exist in ml/models/"
    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    expected_features = ['N', 'P', 'K', 'temperature', 'humidity', 'ph', 'rainfall']
    assert manifest["features"] == expected_features, "Feature list order and names must match contract exactly"
    assert "units" in manifest
    assert "ranges" in manifest
    for f in expected_features:
        assert f in manifest["ranges"]
        assert "min" in manifest["ranges"][f]
        assert "max" in manifest["ranges"][f]

def test_missing_features_rejected(predictor, valid_features):
    # Remove 'rainfall'
    del valid_features['rainfall']
    result = predictor.predict(valid_features, mode="rules_with_ml", regional_approved=True)
    assert result["ml_status"] == "skipped"
    assert any("MISSING_REQUIRED_FEATURES" in r and "rainfall" in r for r in result["ml_skip_reasons"])

def test_non_numeric_features_rejected(predictor, valid_features):
    valid_features['ph'] = "neutral_alkaline"
    result = predictor.predict(valid_features, mode="rules_with_ml", regional_approved=True)
    assert result["ml_status"] == "skipped"
    assert any("NON_NUMERIC_FEATURE_VALUES" in r for r in result["ml_skip_reasons"])

def test_null_feature_values_rejected(predictor, valid_features):
    valid_features['temperature'] = None
    result = predictor.predict(valid_features, mode="rules_with_ml", regional_approved=True)
    assert result["ml_status"] == "skipped"
    assert any("MISSING_REQUIRED_FEATURES" in r for r in result["ml_skip_reasons"])
