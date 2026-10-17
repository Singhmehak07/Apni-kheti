"""
Apni Kheti — Open-Meteo Weather Integration Client
Implements dual-horizon weather extraction:
1. Acute 10-Day Horizon: Hourly observations for immediate field & sowing feasibility
   (soil moisture 0-7cm, waterlogging, rainfall spikes, heat stress, frost shock, fungal risk).
2. Long-Term Climatological Baseline: 10-year monthly normals & distributions
   for seasonal agro-climatic crop suitability.
"""

import os
import json
import hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import httpx
import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent.parent
CACHE_DIR = PROJECT_ROOT / "data" / "processed" / "weather_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

class OpenMeteoClient:
    ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    def _get_cache_path(self, prefix: str, lat: float, lon: float, extra_key: str = "") -> Path:
        raw_key = f"{prefix}_{lat:.4f}_{lon:.4f}_{extra_key}"
        hashed = hashlib.md5(raw_key.encode()).hexdigest()[:12]
        return CACHE_DIR / f"{prefix}_{hashed}.json"

    def fetch_recent_10d(
        self,
        latitude: float,
        longitude: float,
        reference_date: Optional[date] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Fetches hourly weather data for the 10 days preceding reference_date.
        Extracts acute field readiness and risk indicators.
        """
        if reference_date is None:
            # Default to yesterday to ensure archive data availability
            reference_date = date.today() - timedelta(days=1)

        start_date = reference_date - timedelta(days=10)
        cache_key = f"{start_date.isoformat()}_{reference_date.isoformat()}"
        cache_file = self._get_cache_path("acute_10d", latitude, longitude, cache_key)

        if use_cache and cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start_date.isoformat(),
            "end_date": reference_date.isoformat(),
            "hourly": [
                "temperature_2m",
                "relative_humidity_2m",
                "precipitation",
                "soil_temperature_0_to_7cm",
                "soil_moisture_0_to_7cm",
                "wind_speed_10m"
            ],
            "timezone": "auto"
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(self.ARCHIVE_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            # Fallback for network disruption: synthetic estimate from district norms
            return self._build_synthetic_10d_fallback(latitude, longitude, reference_date, str(e))

        hourly = payload.get("hourly", {})
        times = hourly.get("time", [])
        temps = [t for t in hourly.get("temperature_2m", []) if t is not None]
        rhs = [r for r in hourly.get("relative_humidity_2m", []) if r is not None]
        precip = [p for p in hourly.get("precipitation", []) if p is not None]
        soil_moisture = [sm for sm in hourly.get("soil_moisture_0_to_7cm", []) if sm is not None]
        soil_temp = [st for st in hourly.get("soil_temperature_0_to_7cm", []) if st is not None]

        # Calculate acute indicators
        total_rain_10d = float(round(sum(precip), 2)) if precip else 0.0
        
        # Max rolling 24h precipitation
        max_24h_rain = 0.0
        if len(precip) >= 24:
            precip_arr = np.array(precip)
            rolling_24 = np.convolve(precip_arr, np.ones(24), mode='valid')
            max_24h_rain = float(round(np.max(rolling_24), 2))
        elif precip:
            max_24h_rain = total_rain_10d

        avg_sm = float(round(np.mean(soil_moisture), 3)) if soil_moisture else 0.20
        latest_sm = float(round(soil_moisture[-1], 3)) if soil_moisture else avg_sm

        # Moisture classification
        if latest_sm >= 0.36 or max_24h_rain >= 40.0:
            moisture_state = "waterlogged"
            moisture_desc = f"Soil saturated ({latest_sm:.2f} m3/m3). Severe risk of hypoxia/damping off."
        elif latest_sm >= 0.20:
            moisture_state = "optimal"
            moisture_desc = f"Adequate seedbed moisture ({latest_sm:.2f} m3/m3) for rapid germination."
        elif latest_sm >= 0.12:
            moisture_state = "moderate_deficit"
            moisture_desc = f"Moderate moisture deficit ({latest_sm:.2f} m3/m3). Pre-sowing irrigation recommended."
        else:
            moisture_state = "critically_dry"
            moisture_desc = f"Dry seedbed ({latest_sm:.2f} m3/m3). Poor germination likely without irrigation."

        # Thermal stress
        heat_hours_35 = sum(1 for t in temps if t >= 35.0)
        frost_hours_4 = sum(1 for t in temps if t <= 4.0)

        # Fungal hazard hours: RH >= 85% and temp between 14C and 26C
        fungal_hours = 0
        min_len = min(len(temps), len(rhs))
        for i in range(min_len):
            if rhs[i] >= 85.0 and 14.0 <= temps[i] <= 26.0:
                fungal_hours += 1

        result = {
            "status": "live_extracted",
            "start_date": start_date.isoformat(),
            "end_date": reference_date.isoformat(),
            "latitude": latitude,
            "longitude": longitude,
            "total_rain_10d_mm": total_rain_10d,
            "max_24h_rain_mm": max_24h_rain,
            "avg_soil_moisture": avg_sm,
            "latest_soil_moisture": latest_sm,
            "moisture_state": moisture_state,
            "moisture_description": moisture_desc,
            "mean_temperature_c": float(round(np.mean(temps), 1)) if temps else 22.0,
            "max_temperature_c": float(round(max(temps), 1)) if temps else 30.0,
            "min_temperature_c": float(round(min(temps), 1)) if temps else 15.0,
            "mean_relative_humidity": float(round(np.mean(rhs), 1)) if rhs else 65.0,
            "heat_stress_hours_35c": heat_hours_35,
            "frost_risk_hours_4c": frost_hours_4,
            "fungal_risk_hours": fungal_hours
        }

        # Cache result
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception:
            pass

        return result

    def fetch_climatological_baseline(
        self,
        latitude: float,
        longitude: float,
        start_year: int = 2015,
        end_year: int = 2024,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """
        Retrieves 10-year monthly climatology (temperatures, rainfall, evapotranspiration)
        for seasonal macro-crop suitability analysis.
        """
        cache_key = f"{start_year}_{end_year}"
        cache_file = self._get_cache_path("climatology_10yr", latitude, longitude, cache_key)

        if use_cache and cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        # Query Open-Meteo with daily aggregates over the 10-year period
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": f"{start_year}-01-01",
            "end_date": f"{end_year}-12-31",
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "temperature_2m_mean",
                "precipitation_sum",
                "et0_fao_evapotranspiration"
            ],
            "timezone": "auto"
        }

        try:
            with httpx.Client(timeout=45.0) as client:
                resp = client.get(self.ARCHIVE_URL, params=params)
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            return self._build_synthetic_climatology_fallback(latitude, longitude, str(e))

        daily = payload.get("daily", {})
        times = daily.get("time", [])
        t_means = daily.get("temperature_2m_mean", [])
        t_maxs = daily.get("temperature_2m_max", [])
        t_mins = daily.get("temperature_2m_min", [])
        precips = daily.get("precipitation_sum", [])
        et0s = daily.get("et0_fao_evapotranspiration", [])

        # Group by month (1 to 12)
        monthly_stats = {m: {"temps": [], "tmax": [], "tmin": [], "rain": [], "et0": []} for m in range(1, 13)}

        for i, dt_str in enumerate(times):
            m = int(dt_str[5:7])
            if t_means[i] is not None:
                monthly_stats[m]["temps"].append(t_means[i])
            if t_maxs[i] is not None:
                monthly_stats[m]["tmax"].append(t_maxs[i])
            if t_mins[i] is not None:
                monthly_stats[m]["tmin"].append(t_mins[i])
            if precips[i] is not None:
                monthly_stats[m]["rain"].append(precips[i])
            if et0s[i] is not None:
                monthly_stats[m]["et0"].append(et0s[i])

        summary_by_month = {}
        for m in range(1, 13):
            # Sum of rain per month divided by number of years (10)
            annual_rain = float(round(sum(monthly_stats[m]["rain"]) / (end_year - start_year + 1), 1))
            mean_temp = float(round(np.mean(monthly_stats[m]["temps"]), 1)) if monthly_stats[m]["temps"] else 20.0
            mean_max = float(round(np.mean(monthly_stats[m]["tmax"]), 1)) if monthly_stats[m]["tmax"] else 25.0
            mean_min = float(round(np.mean(monthly_stats[m]["tmin"]), 1)) if monthly_stats[m]["tmin"] else 15.0
            mean_et0 = float(round(sum(monthly_stats[m]["et0"]) / (end_year - start_year + 1), 1)) if monthly_stats[m]["et0"] else 80.0

            summary_by_month[str(m)] = {
                "mean_temp_c": mean_temp,
                "mean_tmax_c": mean_max,
                "mean_tmin_c": mean_min,
                "avg_monthly_rain_mm": annual_rain,
                "avg_monthly_et0_mm": mean_et0
            }

        result = {
            "status": "live_extracted",
            "start_year": start_year,
            "end_year": end_year,
            "latitude": latitude,
            "longitude": longitude,
            "monthly_climatology": summary_by_month,
            "kharif_rainfall_avg_mm": float(round(sum(summary_by_month[str(m)]["avg_monthly_rain_mm"] for m in [6, 7, 8, 9]), 1)),
            "rabi_rainfall_avg_mm": float(round(sum(summary_by_month[str(m)]["avg_monthly_rain_mm"] for m in [10, 11, 12, 1, 2, 3]), 1)),
        }

        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2)
        except Exception:
            pass

        return result

    def _build_synthetic_10d_fallback(self, lat: float, lon: float, ref_date: date, err: str) -> Dict[str, Any]:
        """Provides defensible regional agronomic defaults if offline."""
        month = ref_date.month
        # Rough North India temperature curves
        temp_curve = {1: 13, 2: 17, 3: 22, 4: 29, 5: 34, 6: 35, 7: 31, 8: 30, 9: 29, 10: 25, 11: 19, 12: 14}
        t = temp_curve.get(month, 22.0)
        return {
            "status": "offline_fallback",
            "error_note": err,
            "start_date": (ref_date - timedelta(days=10)).isoformat(),
            "end_date": ref_date.isoformat(),
            "latitude": lat,
            "longitude": lon,
            "total_rain_10d_mm": 5.0,
            "max_24h_rain_mm": 4.0,
            "avg_soil_moisture": 0.22,
            "latest_soil_moisture": 0.22,
            "moisture_state": "optimal",
            "moisture_description": "Default regional seedbed moisture estimate.",
            "mean_temperature_c": float(t),
            "max_temperature_c": float(t + 6),
            "min_temperature_c": float(t - 6),
            "mean_relative_humidity": 60.0,
            "heat_stress_hours_35c": 0,
            "frost_risk_hours_4c": 0,
            "fungal_risk_hours": 0
        }

    def _build_synthetic_climatology_fallback(self, lat: float, lon: float, err: str) -> Dict[str, Any]:
        return {
            "status": "offline_fallback",
            "error_note": err,
            "start_year": 2015,
            "end_year": 2024,
            "latitude": lat,
            "longitude": lon,
            "monthly_climatology": {
                str(m): {"mean_temp_c": 22.0, "mean_tmax_c": 28.0, "mean_tmin_c": 16.0, "avg_monthly_rain_mm": 35.0, "avg_monthly_et0_mm": 90.0}
                for m in range(1, 13)
            },
            "kharif_rainfall_avg_mm": 450.0,
            "rabi_rainfall_avg_mm": 110.0
        }

if __name__ == "__main__":
    client = OpenMeteoClient()
    # Test Ludhiana (Punjab) coordinates
    print("Testing 10-day acute weather extraction for Ludhiana (30.9010, 75.8573)...")
    res_10d = client.fetch_recent_10d(30.9010, 75.8573)
    print(f"10-Day Status: {res_10d['status']}")
    print(f"10-Day Rain: {res_10d['total_rain_10d_mm']} mm, Soil Moisture: {res_10d['latest_soil_moisture']} m3/m3 ({res_10d['moisture_state']})")
    print(f"Mean Temp: {res_10d['mean_temperature_c']}°C (Min: {res_10d['min_temperature_c']}°C, Max: {res_10d['max_temperature_c']}°C)")
