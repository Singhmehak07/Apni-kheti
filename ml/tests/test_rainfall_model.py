"""
Unit & Integration Tests for Monthly Rainfall Trend Prediction System.
"""

from pathlib import Path
import pytest
from ml.src.predict_rainfall import RainfallPredictor
from ml.src.rainfall_features import compute_linear_slope

CURRENT_DIR = Path(__file__).resolve().parent
MODELS_DIR = CURRENT_DIR.parent / "models"

@pytest.fixture
def predictor():
    return RainfallPredictor()

def test_rainfall_model_artifacts_exist():
    assert (MODELS_DIR / "rainfall_model.joblib").exists(), "rainfall_model.joblib must exist"
    assert (MODELS_DIR / "rainfall_features_manifest.json").exists(), "rainfall_features_manifest.json must exist"

def test_linear_trend_slope_calculation():
    # Constant series -> slope 0
    assert compute_linear_slope([10.0, 10.0, 10.0]) == 0.0
    # Linearly increasing by 5 per step
    assert pytest.approx(compute_linear_slope([10.0, 15.0, 20.0, 25.0]), rel=1e-3) == 5.0
    # Empty or single value
    assert compute_linear_slope([]) == 0.0
    assert compute_linear_slope([50.0]) == 0.0

def test_predict_month_valid_ranges(predictor):
    res = predictor.predict_month(district="Ludhiana", target_month=7, target_year=2026)
    assert res["location"] == "Ludhiana"
    assert res["target_period"]["month_number"] == 7
    assert res["target_period"]["month_name"] == "July"
    assert res["prediction"]["expected_rainfall_mm"] >= 0.0
    assert res["prediction"]["expected_rainy_days"] >= 0
    assert "same_month_historical_trend" in res
    assert len(res["same_month_historical_trend"]["past_observations"]) >= 5
    assert "agronomic_advisory" in res

def test_predict_all_twelve_months(predictor):
    for m in range(1, 13):
        res = predictor.predict_month(district="Amritsar", target_month=m, target_year=2026)
        pred = res["prediction"]["expected_rainfall_mm"]
        assert pred >= 0.0
        assert res["prediction"]["confidence_range_80pct"]["low_estimate_mm"] <= pred
        assert res["prediction"]["confidence_range_80pct"]["high_estimate_mm"] >= pred

def test_invalid_month_raises_error(predictor):
    with pytest.raises(ValueError):
        predictor.predict_month(district="Patiala", target_month=13)
    with pytest.raises(ValueError):
        predictor.predict_month(district="Patiala", target_month=0)

def test_arbitrary_coordinates_lookup(predictor):
    # GPS coordinates near Bathinda (30.21, 74.95)
    res = predictor.predict_month(coords=(30.21, 74.95), target_month=8, target_year=2026)
    assert res["location"] == "Bathinda"
    assert res["prediction"]["expected_rainfall_mm"] >= 0.0
