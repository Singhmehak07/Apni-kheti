"""
Apni Kheti — Weather-Aware Crop Recommendation & Feasibility Service
Coordinates:
1. Soil-based ML crop prediction (CropPredictor) + Regional pilot staples (Wheat, Mustard).
2. Open-Meteo dual-horizon weather extraction (OpenMeteoClient):
   - 10-day acute hourly window (soil moisture 0-7cm, waterlogging, heat stress, frost risk, fungal incubation).
   - 10-year climatological baseline (temperature normals, seasonal rainfall distributions).
3. Field & climatic feasibility scoring (WeatherFeasibilityEngine).
4. Agricultural economics context (MSP, expected yields, cost of cultivation).
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd
import sys

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.integrations.open_meteo import OpenMeteoClient
from ml.src.predict import CropPredictor
from ml.src.feasibility import WeatherFeasibilityEngine

class FeasibilityRecommendationService:
    def __init__(self):
        self.predictor = CropPredictor()
        self.weather_client = OpenMeteoClient()
        self.engine = WeatherFeasibilityEngine()

    def _estimate_regional_staple_soil_score(self, crop: str, soil: Dict[str, float]) -> float:
        """
        Agronomic rule-based soil scoring for regional staples (Wheat, Mustard, etc.)
        whose labels are excluded from the synthetic Kaggle model.
        """
        n = soil.get("N", 90.0)
        p = soil.get("P", 40.0)
        k = soil.get("K", 40.0)
        ph = soil.get("ph", 7.0)

        crop_norm = crop.lower().strip()
        score = 0.70

        if crop_norm == "wheat":
            # Wheat prefers balanced N (80-140), medium P (30-60), K (30-50), pH 6.0-8.2
            if 70 <= n <= 140 and 25 <= p <= 65 and 6.0 <= ph <= 8.2:
                score = 0.92
            elif 50 <= n <= 160:
                score = 0.80
        elif crop_norm == "mustard":
            # Mustard has lower N demand (50-90), good with pH 6.0-8.5
            if 40 <= n <= 90 and 15 <= p <= 45 and 6.0 <= ph <= 8.5:
                score = 0.88
            else:
                score = 0.75
        elif crop_norm == "chickpea":
            # Legume; low N (15-40), medium P (30-70), sensitive to acid soil
            if n <= 50 and p >= 30 and 6.5 <= ph <= 8.5:
                score = 0.90
            else:
                score = 0.72

        return score

    def get_weather_aware_recommendation(
        self,
        soil_features: Dict[str, float],
        latitude: float,
        longitude: float,
        query_date: Optional[date] = None,
        top_k: int = 5,
        mode: str = "rules_with_ml",
        regional_approved: bool = True
    ) -> Dict[str, Any]:
        """
        End-to-end handler for farmer recommendation:
        1. Fetches dual-horizon weather from Open-Meteo.
        2. Queries Soil ML model and injects regional pilot staples.
        3. Evaluates all candidates across the 10-day field window and 10-year climate norm.
        4. Re-ranks crops and attaches economic indicators (MSP, yield, costs).
        """
        if query_date is None:
            query_date = date.today()

        # Step 1: Extract dual-horizon weather from Open-Meteo
        acute_10d = self.weather_client.fetch_recent_10d(latitude, longitude, reference_date=query_date)
        climatology = self.weather_client.fetch_climatological_baseline(latitude, longitude)

        # Step 2: Augment soil inputs with actual real-time weather if missing
        features = dict(soil_features)
        if "temperature" not in features or features["temperature"] is None:
            features["temperature"] = acute_10d.get("mean_temperature_c", 24.0)
        if "humidity" not in features or features["humidity"] is None:
            features["humidity"] = acute_10d.get("mean_relative_humidity", 65.0)
        if "rainfall" not in features or features["rainfall"] is None:
            features["rainfall"] = acute_10d.get("total_rain_10d_mm", 20.0)

        # Step 3: Run Soil ML Predictor
        ml_result = self.predictor.predict(
            features=features,
            mode=mode,
            regional_approved=regional_approved,
            top_k=top_k
        )

        candidates = list(ml_result.get("top_candidates", []))

        # Augment with regional pilot staples if in North India / Punjab zone
        candidate_crop_names = [c["crop"].lower() for c in candidates]
        month = query_date.month

        # In Rabi season (Oct - March), ensure Wheat, Mustard, Chickpea are evaluated
        if month in [9, 10, 11, 12, 1, 2]:
            for staple in ["wheat", "mustard", "chickpea"]:
                if staple not in candidate_crop_names:
                    s_score = self._estimate_regional_staple_soil_score(staple, soil_features)
                    candidates.append({"crop": staple, "model_score": s_score, "rank": len(candidates) + 1})

        # In Kharif season (April - Aug), ensure Rice, Maize, Cotton are evaluated
        if month in [4, 5, 6, 7, 8]:
            for staple in ["rice", "maize", "cotton"]:
                if staple not in candidate_crop_names:
                    candidates.append({"crop": staple, "model_score": 0.85, "rank": len(candidates) + 1})

        # Step 4: Re-rank using Dual-Horizon Weather Feasibility
        feasibility_ranked = self.engine.rank_candidate_crops(
            candidate_crops=candidates,
            acute_10d=acute_10d,
            climatology=climatology,
            query_date=query_date
        )

        return {
            "status": "success",
            "query_metadata": {
                "latitude": latitude,
                "longitude": longitude,
                "query_date": query_date.isoformat(),
                "query_month": query_date.strftime("%B"),
                "soil_inputs": {k: v for k, v in soil_features.items() if k in ['N', 'P', 'K', 'ph']}
            },
            "weather_context": {
                "acute_10d_status": acute_10d.get("status"),
                "total_rain_10d_mm": acute_10d.get("total_rain_10d_mm"),
                "max_24h_rain_mm": acute_10d.get("max_24h_rain_mm"),
                "soil_moisture_m3_m3": acute_10d.get("latest_soil_moisture"),
                "soil_moisture_condition": acute_10d.get("moisture_state"),
                "moisture_advice": acute_10d.get("moisture_description"),
                "mean_temperature_c": acute_10d.get("mean_temperature_c"),
                "max_temperature_c": acute_10d.get("max_temperature_c"),
                "min_temperature_c": acute_10d.get("min_temperature_c"),
                "heat_stress_hours_35c": acute_10d.get("heat_stress_hours_35c"),
                "frost_risk_hours_4c": acute_10d.get("frost_risk_hours_4c"),
                "fungal_risk_hours": acute_10d.get("fungal_risk_hours")
            },
            "recommendations": feasibility_ranked[:top_k],
            "top_choice": feasibility_ranked[0] if feasibility_ranked else None
        }

if __name__ == "__main__":
    service = FeasibilityRecommendationService()
    # Scenario: Farmer in Ludhiana, Punjab testing soil on Oct 25 (Rabi sowing window)
    sample_soil = {"N": 95, "P": 45, "K": 42, "ph": 7.2}
    print("=" * 75)
    print("DEMO: DUAL-HORIZON WEATHER-AWARE RECOMMENDATION ENGINE (Ludhiana, Oct 25)")
    print("=" * 75)
    out = service.get_weather_aware_recommendation(
        soil_features=sample_soil,
        latitude=30.9010,
        longitude=75.8573,
        query_date=date(2024, 10, 25),
        top_k=4
    )
    w = out["weather_context"]
    print(f"\n[WEATHER SNAPSHOT] Rain (10d): {w['total_rain_10d_mm']} mm | Soil Moisture: {w['soil_moisture_m3_m3']} m3/m3 ({w['soil_moisture_condition']})")
    print(f"Advice: {w['moisture_advice']}")
    print(f"Thermal Profile: Mean {w['mean_temperature_c']}°C (Min: {w['min_temperature_c']}°C, Max: {w['max_temperature_c']}°C) | Fungal Threat: {w['fungal_risk_hours']} hrs")

    print("\n" + "=" * 75)
    print("TOP FEASIBILITY-ADJUSTED RECOMMENDATIONS:")
    print("=" * 75)
    for rec in out["recommendations"]:
        print(f"\n#{rec['feasibility_rank']} {rec['display_name']} ({rec['season']} Season) — [{rec['status_badge']}]")
        print(f"  • Soil Suitability:     {rec['soil_suitability_score']*100:.1f}%")
        print(f"  • Weather Feasibility:  {rec['weather_feasibility_score']:.1f}%")
        print(f"  • Final Composite Score: {rec['composite_score']*100:.1f}%")
        print(f"  • Sowing Window:        {rec['seasonal_status']}")
        if rec["field_positives"]:
            for p in rec["field_positives"]:
                print(f"  * [ADVANTAGE]: {p}")
        if rec["field_warnings"]:
            for warn in rec["field_warnings"]:
                print(f"  * [FIELD ALERT]: {warn}")
