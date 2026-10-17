"""Open-Meteo 7-day forecast for the farmer's district (cached per district for 1 hour)."""
from __future__ import annotations

import time
from datetime import datetime

from config import IST, get_settings
from knowledge import district_by_id
from . import http

_CACHE: dict[str, tuple[float, dict]] = {}
TTL_S = 3600


async def forecast(district_id: str) -> dict:
    d = district_by_id(district_id)
    if not d:
        return {"status": "unavailable", "reason": "unknown_district"}
    hit = _CACHE.get(district_id)
    if hit and time.time() - hit[0] < TTL_S:
        return {**hit[1], "cached": True}
    s = get_settings()
    params = {"latitude": d["lat"], "longitude": d["lon"], "timezone": "Asia/Kolkata", "forecast_days": 7,
              "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max",
              "hourly": "relative_humidity_2m"}
    try:
        resp = await http.request("GET", s.open_meteo_url, params=params, timeout=6.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:  # network/TLS/HTTP
        return {"status": "unavailable", "reason": type(exc).__name__}
    daily = data.get("daily", {})
    hum = data.get("hourly", {}).get("relative_humidity_2m", []) or []
    days = []
    for i, day in enumerate(daily.get("time", [])):
        rh_slice = [h for h in hum[i * 24:(i + 1) * 24] if h is not None]
        days.append({
            "date": day,
            "tmax": daily.get("temperature_2m_max", [None] * 7)[i],
            "tmin": daily.get("temperature_2m_min", [None] * 7)[i],
            "rain_mm": daily.get("precipitation_sum", [0] * 7)[i] or 0,
            "rain_prob": (daily.get("precipitation_probability_max") or [None] * 7)[i],
            "rh": round(sum(rh_slice) / len(rh_slice)) if rh_slice else None,
        })
    result = {"status": "ok", "source_id": "open_meteo", "district": district_id,
              "fetched_at": datetime.now(IST).isoformat(timespec="minutes"), "days": days,
              "summary": summarise(days)}
    _CACHE[district_id] = (time.time(), result)
    return result


def summarise(days: list[dict]) -> dict:
    if not days:
        return {}
    tmax = [d["tmax"] for d in days if d["tmax"] is not None]
    rain_total = round(sum(d["rain_mm"] or 0 for d in days), 1)
    wet = max(days, key=lambda d: d["rain_mm"] or 0)
    return {"tmax_max": max(tmax) if tmax else None, "tmax_avg": round(sum(tmax) / len(tmax), 1) if tmax else None,
            "rain_total_mm": rain_total, "wettest_day": wet["date"] if (wet["rain_mm"] or 0) >= 10 else None,
            "wettest_mm": wet["rain_mm"] if (wet["rain_mm"] or 0) >= 10 else None}
