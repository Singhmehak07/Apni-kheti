"""
Apni Kheti — Dual-Horizon Weather Feasibility Engine
Evaluates candidate crops against:
1. Past 10-Day Acute Weather (Soil moisture, waterlogging, heatwave spikes, frost hours, fungal incubation).
2. 10-Year Regional Climatological Baseline (Long-term thermal & rainfall suitability for crop lifecycle).
Produces calibrated Feasibility Scores, Risk Flags, and Field Guidance.
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
THRESHOLDS_FILE = PROJECT_ROOT / "data" / "reference" / "crop_agro_climatic_thresholds.json"

class WeatherFeasibilityEngine:
    def __init__(self, thresholds_path: Optional[Path] = None):
        self.thresholds_path = thresholds_path or THRESHOLDS_FILE
        self.rules = self._load_rules()

    def _load_rules(self) -> Dict[str, Any]:
        if not self.thresholds_path.exists():
            return {"crops": {}}
        try:
            with open(self.thresholds_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("crops", {})
        except Exception:
            return {}

    def evaluate_crop_feasibility(
        self,
        crop: str,
        model_score: float,
        acute_10d: Dict[str, Any],
        climatology: Dict[str, Any],
        query_date: Optional[date] = None
    ) -> Dict[str, Any]:
        """
        Evaluates a single crop against 10-day acute conditions and 10-year climatology.
        """
        if query_date is None:
            query_date = date.today()

        crop_norm = crop.lower().strip()
        rule = self.rules.get(crop_norm)

        # If crop not in our agronomic knowledge base, apply conservative general defaults
        if not rule:
            return self._evaluate_unmapped_crop(crop, model_score, acute_10d, query_date)

        current_month = query_date.month
        sowing_months = rule.get("sowing_window_months", [])
        
        # -------------------------------------------------------------
        # 1. Macro-Climatic & Seasonal Suitability (0.0 to 1.0, weight: 35%)
        # -------------------------------------------------------------
        seasonal_score = 0.0
        seasonal_notes = []

        # Geographic suitability check (e.g., coconut/coffee in North India plains or apple in low altitude)
        regional_tag = rule.get("regional_suitability", "general")
        lat = acute_10d.get("latitude", 30.0)
        
        # North India plains (lat > 26°N and non-Himalayan)
        if lat > 26.0:
            if regional_tag in ["tropical_highlands_only", "coastal_tropical_only", "temperate_highlands_only"]:
                return {
                    "crop": crop_norm,
                    "display_name": rule.get("display_name", crop.title()),
                    "season": rule.get("season", "Unknown"),
                    "soil_suitability_score": float(round(model_score, 4)),
                    "weather_feasibility_score": 0.0,
                    "composite_score": float(round(model_score * 0.15, 4)),
                    "tier": "INFEASIBLE",
                    "status_badge": "GEOGRAPHICALLY_INCOMPATIBLE",
                    "seasonal_status": f"INCOMPATIBLE GEOGRAPHY: {rule.get('display_name')} requires {regional_tag.replace('_', ' ')} (cannot grow in North India plains).",
                    "field_readiness_status": "Geographic exclusion applied.",
                    "field_warnings": [f"{rule.get('display_name')} is not ecologically viable in this agro-climatic zone."],
                    "field_positives": [],
                    "acute_weather_snapshot": acute_10d
                }

        if current_month in sowing_months:
            seasonal_score = 1.0
            seasonal_notes.append(f"In optimal seasonal sowing window ({rule.get('season')} season: {rule.get('sowing_window_desc')}).")
        elif (current_month - 1) in sowing_months or (current_month + 1) in sowing_months:
            seasonal_score = 0.50
            seasonal_notes.append(f"Marginal/border sowing window. Standard window is {rule.get('sowing_window_desc')}.")
        else:
            seasonal_score = 0.05
            seasonal_notes.append(f"OUT OF SEASON: This is a {rule.get('season')} crop (sowing: {rule.get('sowing_window_desc')}). Planting now risks total crop failure.")

        # Check climatological temperature comfort for upcoming 3 months
        monthly_clim = climatology.get("monthly_climatology", {})
        t_opt_min, t_opt_max = rule.get("temperature_optimal", [18.0, 30.0])
        next_3_months = [(current_month + i - 1) % 12 + 1 for i in range(3)]
        temp_fit_count = 0
        for m in next_3_months:
            m_stat = monthly_clim.get(str(m), {})
            m_temp = m_stat.get("mean_temp_c", 22.0)
            if t_opt_min - 3.0 <= m_temp <= t_opt_max + 3.0:
                temp_fit_count += 1
        
        clim_temp_factor = temp_fit_count / 3.0
        climate_subscore = (seasonal_score * 0.70) + (clim_temp_factor * 0.30)

        # -------------------------------------------------------------
        # 2. Immediate 10-Day Field & Soil Readiness (0.0 to 1.0, weight: 40%)
        # -------------------------------------------------------------
        field_subscore = 1.0
        field_warnings = []
        field_positives = []

        soil_moisture = acute_10d.get("latest_soil_moisture", 0.20)
        moisture_state = acute_10d.get("moisture_state", "optimal")
        total_rain_10d = acute_10d.get("total_rain_10d_mm", 0.0)
        max_24h_rain = acute_10d.get("max_24h_rain_mm", 0.0)
        max_temp_10d = acute_10d.get("max_temperature_c", 28.0)
        min_temp_10d = acute_10d.get("min_temperature_c", 18.0)
        heat_hours = acute_10d.get("heat_stress_hours_35c", 0)
        frost_hours = acute_10d.get("frost_risk_hours_4c", 0)
        fungal_hours = acute_10d.get("fungal_risk_hours", 0)

        waterlogging_tol = rule.get("waterlogging_tolerance", "low")

        # Waterlogging & Soil Moisture Checks
        if moisture_state == "waterlogged" or max_24h_rain >= 35.0:
            if waterlogging_tol in ["extremely_low", "very_low"]:
                field_subscore -= 0.65
                field_warnings.append(
                    f"CRITICAL HAZARD: Field is waterlogged ({soil_moisture:.2f} m3/m3, {max_24h_rain:.1f}mm 24h rain). "
                    f"{rule.get('display_name')} seeds will suffer rotting and damping-off. Postpone sowing until soil drains."
                )
            elif waterlogging_tol == "low":
                field_subscore -= 0.40
                field_warnings.append(f"Excess moisture ({soil_moisture:.2f} m3/m3). Poor germination aeration expected.")
            elif waterlogging_tol == "high":
                field_positives.append("Tolerates standing water; moisture conditions favorable for transplanting/nursery.")
        elif moisture_state == "critically_dry":
            field_subscore -= 0.30
            field_warnings.append(
                f"DRY SEEDBED: Topsoil moisture is very low ({soil_moisture:.2f} m3/m3). "
                "Must apply pre-sowing irrigation (Rauni) before seed drilling."
            )
        elif moisture_state == "moderate_deficit":
            field_subscore -= 0.10
            field_warnings.append(f"Light moisture deficit ({soil_moisture:.2f} m3/m3). Light irrigation recommended prior to sowing.")
        else:
            field_positives.append(f"Optimal seedbed soil moisture ({soil_moisture:.2f} m3/m3) for immediate sowing.")

        # Thermal Stress Checks in Last 10 Days
        max_limit = rule.get("max_temp_limit", 40.0)
        min_limit = rule.get("min_temp_limit", 5.0)

        if max_temp_10d > max_limit or heat_hours > 15:
            field_subscore -= 0.35
            field_warnings.append(f"HEAT STRESS: Recent temperatures hit {max_temp_10d}°C with {heat_hours} hours >=35°C. Risk of seedling desiccation.")
        
        if min_temp_10d < min_limit or frost_hours > 0:
            field_subscore -= 0.45
            field_warnings.append(f"FROST RISK: Night temperatures dropped to {min_temp_10d}°C ({frost_hours} hours <=4°C). Lethal to young seedlings.")

        # Fungal Incubation Threat
        if fungal_hours >= 18:
            field_subscore -= 0.15
            field_warnings.append(f"PATHOGEN ALERT: {fungal_hours} hours of high humidity (RH>85%) in 14-26°C range detected. High fungal incubation risk; use certified fungicide seed treatment.")

        field_subscore = max(0.0, min(1.0, field_subscore))

        # -------------------------------------------------------------
        # 3. Composite Feasibility Score Calculation
        # -------------------------------------------------------------
        # Base environmental feasibility combines macro climate (45%) and immediate field (55%)
        env_feasibility = (climate_subscore * 0.45) + (field_subscore * 0.55)

        # If field readiness suffered a severe critical hazard (waterlogging or extreme frost/heat), cap feasibility
        if field_subscore <= 0.40 and waterlogging_tol in ["extremely_low", "very_low"]:
            env_feasibility = min(env_feasibility, 0.40)

        # If completely out of season, hard cap feasibility at 20%
        if seasonal_score <= 0.05:
            env_feasibility = min(env_feasibility, 0.20)

        # Composite score combines soil match (35%) with environmental feasibility (65%)
        composite_score = float(round((model_score * 0.35) + (env_feasibility * 0.65), 4))
        feasibility_pct = float(round(env_feasibility * 100, 1))

        # Tier classification
        if feasibility_pct >= 75.0:
            tier = "HIGH_FEASIBILITY"
            status_badge = "RECOMMENDED_FOR_PLANTING"
        elif feasibility_pct >= 50.0:
            tier = "MODERATE_FEASIBILITY"
            status_badge = "CONDITIONALLY_FEASIBLE"
        elif feasibility_pct >= 25.0:
            tier = "LOW_FEASIBILITY"
            status_badge = "HIGH_RISK"
        else:
            tier = "INFEASIBLE"
            status_badge = "NOT_RECOMMENDED"

        return {
            "crop": crop_norm,
            "display_name": rule.get("display_name", crop.title()),
            "season": rule.get("season", "Unknown"),
            "soil_suitability_score": float(round(model_score, 4)),
            "weather_feasibility_score": feasibility_pct,
            "composite_score": composite_score,
            "tier": tier,
            "status_badge": status_badge,
            "seasonal_status": seasonal_notes[0] if seasonal_notes else "Season checked",
            "field_readiness_status": acute_10d.get("moisture_description", "Moisture evaluated"),
            "field_warnings": field_warnings,
            "field_positives": field_positives,
            "acute_weather_snapshot": {
                "total_rain_10d_mm": total_rain_10d,
                "latest_soil_moisture": soil_moisture,
                "moisture_state": moisture_state,
                "max_temp_10d_c": max_temp_10d,
                "min_temp_10d_c": min_temp_10d,
                "fungal_risk_hours": fungal_hours
            }
        }

    def _evaluate_unmapped_crop(self, crop: str, model_score: float, acute_10d: Dict[str, Any], query_date: date) -> Dict[str, Any]:
        """Handles non-standard crops with generic environmental heuristics."""
        moisture = acute_10d.get("latest_soil_moisture", 0.20)
        feasibility = 60.0
        warnings = [f"Crop '{crop}' lacks fine-grained regional agronomic rules. Feasibility estimated from general soil moisture ({moisture:.2f} m3/m3)."]
        return {
            "crop": crop.lower(),
            "display_name": crop.title(),
            "season": "Unspecified",
            "soil_suitability_score": float(round(model_score, 4)),
            "weather_feasibility_score": feasibility,
            "composite_score": float(round((model_score * 0.5) + (feasibility / 100 * 0.5), 4)),
            "tier": "MODERATE_FEASIBILITY",
            "status_badge": "PRELIMINARY_EVALUATION",
            "seasonal_status": "No seasonal rules registered for this crop in pilot registry.",
            "field_readiness_status": acute_10d.get("moisture_description", "Generic check"),
            "field_warnings": warnings,
            "field_positives": [],
            "acute_weather_snapshot": {
                "total_rain_10d_mm": acute_10d.get("total_rain_10d_mm", 0.0),
                "latest_soil_moisture": moisture,
                "moisture_state": acute_10d.get("moisture_state", "optimal"),
                "max_temp_10d_c": acute_10d.get("max_temperature_c", 25.0),
                "min_temp_10d_c": acute_10d.get("min_temperature_c", 15.0),
                "fungal_risk_hours": 0
            }
        }

    def rank_candidate_crops(
        self,
        candidate_crops: List[Dict[str, Any]],
        acute_10d: Dict[str, Any],
        climatology: Dict[str, Any],
        query_date: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """
        Ranks top-k candidates by composite score (Soil Match + Real-World Weather Feasibility).
        """
        evaluated = []
        for cand in candidate_crops:
            crop_name = cand.get("crop")
            score = cand.get("model_score", 0.5)
            res = self.evaluate_crop_feasibility(
                crop=crop_name,
                model_score=score,
                acute_10d=acute_10d,
                climatology=climatology,
                query_date=query_date
            )
            evaluated.append(res)

        # Re-sort descending by composite_score
        evaluated.sort(key=lambda x: x["composite_score"], reverse=True)
        for idx, item in enumerate(evaluated):
            item["feasibility_rank"] = idx + 1

        return evaluated
