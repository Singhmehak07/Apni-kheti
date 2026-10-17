"""
Tests for Dual-Horizon Weather Feasibility Engine
Validates:
1. Seasonal gating (e.g. Rice in October/November penalized; Wheat favored).
2. Acute soil moisture and waterlogging hazards (e.g. Chickpea / pulses rot in saturated soil).
3. Dry seedbed irrigation guidance.
4. Fungal incubation alert triggering on sustained humidity.
5. Composite ranking integration.
"""

from datetime import date
import pytest
from ml.src.feasibility import WeatherFeasibilityEngine
from backend.services.feasibility_service import FeasibilityRecommendationService

@pytest.fixture
def engine():
    return WeatherFeasibilityEngine()

@pytest.fixture
def base_acute_weather():
    return {
        "status": "live_extracted",
        "latitude": 30.9010,
        "longitude": 75.8573,
        "total_rain_10d_mm": 5.0,
        "max_24h_rain_mm": 3.0,
        "avg_soil_moisture": 0.22,
        "latest_soil_moisture": 0.22,
        "moisture_state": "optimal",
        "moisture_description": "Optimal seedbed soil moisture.",
        "mean_temperature_c": 21.0,
        "max_temperature_c": 27.0,
        "min_temperature_c": 14.0,
        "mean_relative_humidity": 65.0,
        "heat_stress_hours_35c": 0,
        "frost_risk_hours_4c": 0,
        "fungal_risk_hours": 2
    }

@pytest.fixture
def base_climatology():
    return {
        "monthly_climatology": {
            str(m): {
                "mean_temp_c": 20.0,
                "mean_tmax_c": 26.0,
                "mean_tmin_c": 14.0,
                "avg_monthly_rain_mm": 20.0,
                "avg_monthly_et0_mm": 70.0
            }
            for m in range(1, 13)
        }
    }

def test_out_of_season_rice_penalized_in_november(engine, base_acute_weather, base_climatology):
    # In November, Rice (Kharif) should receive an out-of-season penalty
    eval_rice = engine.evaluate_crop_feasibility(
        crop="rice",
        model_score=0.95,
        acute_10d=base_acute_weather,
        climatology=base_climatology,
        query_date=date(2024, 11, 5)
    )
    assert eval_rice["weather_feasibility_score"] <= 25.0
    assert eval_rice["tier"] == "INFEASIBLE"
    assert "OUT OF SEASON" in eval_rice["seasonal_status"]

def test_in_season_wheat_optimal_in_november(engine, base_acute_weather, base_climatology):
    # In November, Wheat (Rabi) should be in prime season
    eval_wheat = engine.evaluate_crop_feasibility(
        crop="wheat",
        model_score=0.90,
        acute_10d=base_acute_weather,
        climatology=base_climatology,
        query_date=date(2024, 11, 5)
    )
    assert eval_wheat["weather_feasibility_score"] >= 75.0
    assert eval_wheat["tier"] == "HIGH_FEASIBILITY"
    assert "optimal seasonal sowing window" in eval_wheat["seasonal_status"]

def test_waterlogging_hazard_for_chickpea(engine, base_acute_weather, base_climatology):
    # Simulate heavy recent rain and waterlogged soil
    saturated_weather = dict(base_acute_weather)
    saturated_weather["latest_soil_moisture"] = 0.40
    saturated_weather["moisture_state"] = "waterlogged"
    saturated_weather["max_24h_rain_mm"] = 45.0

    eval_chickpea = engine.evaluate_crop_feasibility(
        crop="chickpea",
        model_score=0.85,
        acute_10d=saturated_weather,
        climatology=base_climatology,
        query_date=date(2024, 10, 20)
    )
    assert any("CRITICAL HAZARD: Field is waterlogged" in w for w in eval_chickpea["field_warnings"])
    assert eval_chickpea["weather_feasibility_score"] < 50.0

def test_critically_dry_seedbed_triggers_rauni_advisory(engine, base_acute_weather, base_climatology):
    dry_weather = dict(base_acute_weather)
    dry_weather["latest_soil_moisture"] = 0.08
    dry_weather["moisture_state"] = "critically_dry"

    eval_wheat = engine.evaluate_crop_feasibility(
        crop="wheat",
        model_score=0.90,
        acute_10d=dry_weather,
        climatology=base_climatology,
        query_date=date(2024, 11, 5)
    )
    assert any("DRY SEEDBED" in w for w in eval_wheat["field_warnings"])
    assert any("Rauni" in w for w in eval_wheat["field_warnings"])

def test_pathogen_alert_triggers_on_high_humidity(engine, base_acute_weather, base_climatology):
    humid_weather = dict(base_acute_weather)
    humid_weather["fungal_risk_hours"] = 28

    eval_wheat = engine.evaluate_crop_feasibility(
        crop="wheat",
        model_score=0.90,
        acute_10d=humid_weather,
        climatology=base_climatology,
        query_date=date(2024, 11, 5)
    )
    assert any("PATHOGEN ALERT" in w for w in eval_wheat["field_warnings"])
    assert any("fungicide seed treatment" in w for w in eval_wheat["field_warnings"])

def test_full_feasibility_service_pipeline():
    service = FeasibilityRecommendationService()
    soil = {"N": 90, "P": 45, "K": 40, "ph": 7.0}
    res = service.get_weather_aware_recommendation(
        soil_features=soil,
        latitude=30.9010,
        longitude=75.8573,
        query_date=date(2024, 10, 25),
        top_k=3
    )
    assert res["status"] == "success"
    assert "weather_context" in res
    assert len(res["recommendations"]) == 3
    # In late October, top crop must be a Rabi crop (e.g. Wheat or Mustard)
    top = res["recommendations"][0]
    assert top["season"] == "Rabi"
