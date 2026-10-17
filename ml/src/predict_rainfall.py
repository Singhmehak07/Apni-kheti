"""
Apni Kheti — Monthly Rainfall Predictor & Same-Month Trend Analyzer
Predicts rainfall for a specified month by analyzing historical same-month trends (2015–2025).

Supports:
- Named Punjab districts (e.g., "Ludhiana", "Amritsar", "Bathinda", "Patiala", etc.)
- Arbitrary (latitude, longitude) coordinates.
- Returns multi-year historical trend, trend slope (mm/yr), prediction, IMD category, and agronomic advisory.
"""

import sys
import argparse
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import joblib
import numpy as np
import pandas as pd

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.src.rainfall_extractor import PUNJAB_DISTRICTS
from ml.src.rainfall_features import compute_linear_slope

MODELS_DIR = PROJECT_ROOT / "ml" / "models"
BACKEND_ARTIFACTS = PROJECT_ROOT / "backend" / "artifacts"
PROCESSED_CSV = PROJECT_ROOT / "data" / "processed" / "punjab_monthly_rainfall_2015_2025.csv"

MONTH_NAMES = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

AGRONOMIC_MONTHLY_ADVISORY = {
    1: "Rabi Winter (Wheat vegetative/tillering). Light rainfall is highly beneficial; reduces tubewell irrigation demand. Watch for frost in rain-deficient weeks.",
    2: "Late Winter (Wheat jointing & flowering). Western disturbance showers help grain formation. High unseasonal rainfall with winds can cause crop lodging.",
    3: "Pre-Monsoon Spring (Wheat maturity & Mustard harvest). Dry weather preferred for harvesting. Excess rain damages mature standing crop.",
    4: "Spring/Harvest Window (Wheat harvesting & Baisakhi threshing). Rain is undesirable; causes grain discoloration and threshing delays.",
    5: "Pre-Kharif Summer (Land preparation & Cotton sowing). Hot and dry. Rainfall aids pre-sowing field soaking ('rauni') for cotton and green manuring (dhaincha).",
    6: "Monsoon Arrival (Paddy nursery transplantation begins). Timely rainfall significantly cuts peak tubewell power load for DSR/puddled transplantation.",
    7: "Peak Southwest Monsoon (Paddy tillering & Cotton flowering). Heaviest rainfall month in Punjab. Ensure field drainage to prevent waterlogging in cotton/maize.",
    8: "Late Monsoon (Paddy panicle initiation). Consistent moisture required. Monitor for sheath blight/bacterial leaf blight in warm, humid rainy spells.",
    9: "Monsoon Withdrawal (Paddy grain filling). Moderate showers helpful. Heavy storms cause lodging and grain shedding in basmati/PR varieties.",
    10: "Post-Monsoon (Paddy harvesting & Cotton picking). Clear dry weather essential. Rainfall delays combine harvesting and increases grain moisture content.",
    11: "Rabi Sowing Window (Wheat & Gram sowing). Dry conditions optimal for seedbed preparation. Pre-sowing irrigation depends on residual soil moisture.",
    12: "Early Winter (Wheat crown root initiation). Low baseline rainfall. Light showers assist fertilizer uptake (first urea top-dressing)."
}

class RainfallPredictor:
    def __init__(self, model_dir: Optional[Path] = None):
        if model_dir is not None and model_dir.exists():
            self.model_dir = model_dir
        elif BACKEND_ARTIFACTS.exists() and (BACKEND_ARTIFACTS / "rainfall_model.joblib").exists():
            self.model_dir = BACKEND_ARTIFACTS
        else:
            self.model_dir = MODELS_DIR

        self.model = None
        self.manifest = None
        self._load_artifacts()

        # Load historical monthly database
        if not PROCESSED_CSV.exists():
            from ml.src.rainfall_extractor import extract_all_districts
            self.df_history = extract_all_districts()
        else:
            self.df_history = pd.read_csv(PROCESSED_CSV)

    def _load_artifacts(self):
        model_path = self.model_dir / "rainfall_model.joblib"
        manifest_path = self.model_dir / "rainfall_features_manifest.json"

        if model_path.exists():
            self.model = joblib.load(model_path)
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                self.manifest = json.load(f)

    def resolve_location(self, district: Optional[str], coords: Optional[Tuple[float, float]]) -> Tuple[str, float, float]:
        """Resolves location name and coordinates."""
        if district:
            # Case-insensitive lookup
            for d, (lat, lon) in PUNJAB_DISTRICTS.items():
                if d.lower() == district.lower().strip():
                    return d, lat, lon
            # Default to nearest or provided
            return district.capitalize(), PUNJAB_DISTRICTS["Ludhiana"][0], PUNJAB_DISTRICTS["Ludhiana"][1]
        elif coords:
            lat, lon = coords
            # Find closest district
            best_dist = "Punjab"
            min_dist = float("inf")
            for d, (d_lat, d_lon) in PUNJAB_DISTRICTS.items():
                dist_val = np.hypot(d_lat - lat, d_lon - lon)
                if dist_val < min_dist:
                    min_dist = dist_val
                    best_dist = d
            return best_dist, lat, lon
        else:
            return "Ludhiana", PUNJAB_DISTRICTS["Ludhiana"][0], PUNJAB_DISTRICTS["Ludhiana"][1]

    def predict_month(
        self,
        district: Optional[str] = None,
        coords: Optional[Tuple[float, float]] = None,
        target_month: int = 7,
        target_year: int = 2026
    ) -> Dict[str, Any]:
        """
        Predicts rainfall for target_month analyzing previous years' same-month trend.
        """
        if district is None and coords is None:
            district = "Ludhiana"
        if target_month < 1 or target_month > 12:
            raise ValueError(f"target_month must be between 1 and 12, got {target_month}")

        loc_name, lat, lon = self.resolve_location(district, coords)

        # Filter historical records for this location and target month
        loc_mask = (self.df_history["district"].str.lower() == loc_name.lower()) & (self.df_history["month"] == target_month)
        loc_month_history = self.df_history[loc_mask].sort_values(by="year")

        if len(loc_month_history) == 0:
            # Fallback to Punjab regional average
            reg_mask = (self.df_history["month"] == target_month)
            loc_month_history = self.df_history[reg_mask].groupby("year")["rainfall_mm"].mean().reset_index()
            loc_month_history["district"] = loc_name
            loc_month_history["rainy_days"] = 5

        # Historical same-month series
        years = loc_month_history["year"].tolist()
        rf_series = loc_month_history["rainfall_mm"].tolist()
        rd_series = loc_month_history["rainy_days"].tolist()

        # Multi-year trend slope (mm per year)
        trend_slope = compute_linear_slope(rf_series)
        hist_mean = float(np.mean(rf_series))
        hist_std = float(np.std(rf_series)) if len(rf_series) > 1 else 10.0
        hist_min = float(np.min(rf_series))
        hist_max = float(np.max(rf_series))
        avg_rainy_days = float(np.mean(rd_series))

        # Recent lags
        lag_1yr = rf_series[-1] if len(rf_series) >= 1 else hist_mean
        lag_2yr = rf_series[-2] if len(rf_series) >= 2 else lag_1yr
        lag_3yr = rf_series[-3] if len(rf_series) >= 3 else lag_2yr
        mean_3yr = float(np.mean(rf_series[-3:])) if len(rf_series) >= 3 else hist_mean
        mean_5yr = float(np.mean(rf_series[-5:])) if len(rf_series) >= 5 else hist_mean

        # Antecedent months
        prev_m1 = target_month - 1 if target_month > 1 else 12
        prev_m1_sub = self.df_history[(self.df_history["district"].str.lower() == loc_name.lower()) & (self.df_history["month"] == prev_m1)]
        prior_rf = float(prev_m1_sub["rainfall_mm"].iloc[-1]) if len(prev_m1_sub) > 0 else hist_mean

        prev_m2 = target_month - 2 if target_month > 2 else (12 if target_month == 2 else 11)
        prev_m2_sub = self.df_history[(self.df_history["district"].str.lower() == loc_name.lower()) & (self.df_history["month"] == prev_m2)]
        prior_2rf = float(prev_m2_sub["rainfall_mm"].iloc[-1]) if len(prev_m2_sub) > 0 else hist_mean

        # Season code & cyclical encoding
        if target_month in [1, 2]:
            season_code = 0
            season_name = "Winter (Rabi)"
        elif target_month in [3, 4, 5]:
            season_code = 1
            season_name = "Pre-Monsoon / Summer (Zaid)"
        elif target_month in [6, 7, 8, 9]:
            season_code = 2
            season_name = "Southwest Monsoon (Kharif)"
        else:
            season_code = 3
            season_name = "Post-Monsoon"

        month_sin = float(np.sin(2 * np.pi * target_month / 12.0))
        month_cos = float(np.cos(2 * np.pi * target_month / 12.0))

        # Build feature vector
        features_dict = {
            "grid_lat": lat,
            "grid_lon": lon,
            "month": target_month,
            "month_sin": month_sin,
            "month_cos": month_cos,
            "season_code": season_code,
            "same_month_lag_1yr": lag_1yr,
            "same_month_lag_2yr": lag_2yr,
            "same_month_lag_3yr": lag_3yr,
            "same_month_3yr_mean": mean_3yr,
            "same_month_5yr_mean": mean_5yr,
            "same_month_hist_mean": hist_mean,
            "same_month_hist_std": hist_std,
            "same_month_hist_min": hist_min,
            "same_month_hist_max": hist_max,
            "same_month_trend_slope": trend_slope,
            "same_month_rainy_days_avg": avg_rainy_days,
            "prior_month_rf": prior_rf,
            "prior_2month_rf": prior_2rf
        }

        # Predict with model
        if self.model is not None and hasattr(self.model, "predict"):
            input_df = pd.DataFrame([features_dict])
            pred_rf = float(self.model.predict(input_df)[0])
            pred_rf = max(0.0, pred_rf)
        else:
            # Fallback to trend-adjusted climatology
            years_ahead = max(1, target_year - years[-1])
            pred_rf = max(0.0, hist_mean + trend_slope * years_ahead)

        pred_rf = round(pred_rf, 2)

        # Forecast interval (estimated standard error)
        std_err = max(8.0, hist_std * 0.6)
        pred_low = round(max(0.0, pred_rf - 1.28 * std_err), 2)
        pred_high = round(pred_rf + 1.28 * std_err, 2)

        # IMD Classification relative to long-term normal
        percent_of_normal = ((pred_rf - hist_mean) / hist_mean) * 100.0 if hist_mean > 0 else 0.0
        if percent_of_normal >= 20.0:
            category = "Excess (> +20% of normal)"
            category_code = "excess"
        elif percent_of_normal <= -20.0:
            category = "Deficit (< -20% of normal)"
            category_code = "deficit"
        else:
            category = "Normal (-19% to +19% of normal)"
            category_code = "normal"

        # Trend direction interpretation
        if trend_slope > 1.5:
            trend_desc = f"Increasing (+{trend_slope:.2f} mm/year over previous years)"
        elif trend_slope < -1.5:
            trend_desc = f"Decreasing ({trend_slope:.2f} mm/year over previous years)"
        else:
            trend_desc = f"Stable ({trend_slope:+.2f} mm/year variance)"

        # Historical track record table
        history_table = [
            {
                "year": int(y_val),
                "rainfall_mm": float(round(rf_val, 2)),
                "rainy_days": int(rd_val)
            }
            for y_val, rf_val, rd_val in zip(years, rf_series, rd_series)
        ]

        return {
            "location": loc_name,
            "coordinates": {"latitude": lat, "longitude": lon},
            "target_period": {
                "month_number": target_month,
                "month_name": MONTH_NAMES[target_month],
                "year": target_year,
                "season": season_name
            },
            "same_month_historical_trend": {
                "years_analyzed": len(years),
                "historical_mean_mm": round(hist_mean, 2),
                "historical_min_mm": round(hist_min, 2),
                "historical_max_mm": round(hist_max, 2),
                "historical_std_mm": round(hist_std, 2),
                "linear_trend_slope_mm_per_year": round(trend_slope, 3),
                "trend_interpretation": trend_desc,
                "past_observations": history_table
            },
            "prediction": {
                "expected_rainfall_mm": pred_rf,
                "confidence_range_80pct": {
                    "low_estimate_mm": pred_low,
                    "high_estimate_mm": pred_high
                },
                "expected_rainy_days": int(round(avg_rainy_days)),
                "climatological_normal_mm": round(hist_mean, 2),
                "departure_from_normal_pct": round(percent_of_normal, 1),
                "imd_category": category,
                "imd_category_code": category_code
            },
            "agronomic_advisory": AGRONOMIC_MONTHLY_ADVISORY.get(target_month, "Consult local PAU guidelines for monthly cultivation adjustments.")
        }

def main():
    parser = argparse.ArgumentParser(description="Apni Kheti Monthly Rainfall Trend Predictor")
    parser.add_argument("--district", type=str, default="Ludhiana", help="Punjab district name")
    parser.add_argument("--month", type=int, default=7, help="Target month (1-12)")
    parser.add_argument("--year", type=int, default=2026, help="Target year")
    args = parser.parse_args()

    predictor = RainfallPredictor()
    result = predictor.predict_month(
        district=args.district,
        target_month=args.month,
        target_year=args.year
    )

    print("=" * 65)
    print(f"  APNI KHETI — MONTHLY RAINFALL TREND PREDICTION")
    print(f"  Location: {result['location']} | Target: {result['target_period']['month_name']} {result['target_period']['year']}")
    print(f"  Season: {result['target_period']['season']}")
    print("=" * 65)
    print(f"\n[1] PREVIOUS YEARS SAME-MONTH TRACK RECORD ({result['target_period']['month_name']} 2015-2025):")
    for row in result['same_month_historical_trend']['past_observations']:
        bar = "#" * int(row['rainfall_mm'] / 15)
        print(f"    {row['year']}: {row['rainfall_mm']:6.2f} mm | {row['rainy_days']:2d} rainy days  {bar}")

    print(f"\n[2] INTER-ANNUAL TREND ANALYSIS:")
    print(f"    - Historical Climatological Mean: {result['same_month_historical_trend']['historical_mean_mm']} mm")
    print(f"    - 10-Year Range: {result['same_month_historical_trend']['historical_min_mm']} mm - {result['same_month_historical_trend']['historical_max_mm']} mm")
    print(f"    - Multi-Year Trend: {result['same_month_historical_trend']['trend_interpretation']}")

    print(f"\n[3] MODEL FORECAST FOR {result['target_period']['month_name'].upper()} {result['target_period']['year']}:")
    print(f"    - Expected Rainfall: {result['prediction']['expected_rainfall_mm']} mm")
    print(f"    - 80% Confidence Range: [{result['prediction']['confidence_range_80pct']['low_estimate_mm']} mm - {result['prediction']['confidence_range_80pct']['high_estimate_mm']} mm]")
    print(f"    - Estimated Rainy Days: ~{result['prediction']['expected_rainy_days']} days")
    print(f"    - Departure from Normal: {result['prediction']['departure_from_normal_pct']:+.1f}%")
    print(f"    - IMD Rainfall Category: {result['prediction']['imd_category']}")

    print(f"\n[4] AGRONOMIC IMPACT & FIELD ADVISORY:")
    print(f"    {result['agronomic_advisory']}")
    print("=" * 65)

if __name__ == "__main__":
    main()
