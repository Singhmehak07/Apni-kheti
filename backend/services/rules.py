"""Rule-based crop evaluation (PAU Package of Practices, Rabi 2025-26).

ML is intentionally off (ml_status="skipped"); these rules are the decision layer.
Each reason is {code, type, params, affects_status}; text is rendered later per language.
"""
from __future__ import annotations

from datetime import date, timedelta

from knowledge import crops

STATUS_ORDER = {"feasible": 0, "conditional": 1, "insufficient_information": 2, "not_suitable": 3}
DEFAULT_PREP_DAYS = 14


def season_date(today: date, mmdd: str) -> date:
    m, d = map(int, mmdd.split("-"))
    year = today.year if m >= 7 else today.year + 1
    if today.month < 7 and m >= 7:
        year = today.year - 1
    return date(year, m, d)


def R(code: str, typ: str, affects: str | None = None, **params) -> dict:
    """affects: None (info only) | 'caution' (→ conditional) | 'block' (→ not suitable) | 'unknown' (→ need info)."""
    return {"code": code, "type": typ, "affects": affects, "params": params}


def pick_variety(cid: str, zone: str, window: str) -> dict | None:
    vs = crops()[cid]["varieties"]
    cands = [v for v in vs if v["window"] == window and (zone in v["zones"] or "all" in v["zones"])]
    if not cands:
        cands = [v for v in vs if v["window"] == "timely"]
    zone_specific = [v for v in cands if zone in v["zones"] and v.get("yield_q_acre")]
    pool = zone_specific or [v for v in cands if v.get("yield_q_acre")] or cands
    return max(pool, key=lambda v: v.get("yield_q_acre") or 0) if pool else None


def evaluate_crop(cid: str, f: dict, weather: dict | None, today: date) -> dict:
    c = crops()[cid]
    sw = c["sowing"]
    reasons: list[dict] = []
    sow = f["sow_date"]
    assumed_sow = sow is None
    if assumed_sow:
        sow = today + timedelta(days=DEFAULT_PREP_DAYS)
        reasons.append(R("sow_unknown", "data", None, date=sow.isoformat()))
    rainfed = f["irrigations"] == 0
    opt_s, opt_e = season_date(today, sw["optimal_start"]), season_date(today, sw["optimal_end"])
    if cid == "gram" and rainfed:
        opt_s, opt_e = season_date(today, sw["rainfed_start"]), season_date(today, sw["rainfed_end"])
    early_s, late_e = season_date(today, sw["early_start"]), season_date(today, sw["late_end"])
    window = [opt_s.isoformat(), opt_e.isoformat()]
    late_weeks = 0
    timing = "timely"
    if cid == "wheat" and early_s <= sow < opt_s:
        reasons.append(R("sow_early_wheat", "fit", None, date=sow.isoformat(), window=window))
    elif sow < min(early_s, opt_s) or (cid != "wheat" and sow < opt_s):
        code = {"wheat": "sow_early_wheat", "gram": "sow_early_gram"}.get(cid, "sow_early")
        reasons.append(R(code, "caution", "caution", date=sow.isoformat(), window=window, crop=cid,
                         start=opt_s.isoformat()))
    elif sow <= opt_e:
        reasons.append(R("sow_optimal", "fit", None, date=sow.isoformat(), window=window, crop=cid))
    elif sow <= late_e:
        late_weeks = max(1, round((sow - opt_e).days / 7))
        timing = "late"
        if cid == "wheat":
            reasons.append(R("sow_late_wheat", "caution", "caution", date=sow.isoformat(), weeks=late_weeks,
                             late_variety=sw.get("late_label", "")))
        else:
            reasons.append(R("sow_late", "caution", "caution", date=sow.isoformat(), window=window))
    else:
        reasons.append(R("sow_too_late", "caution", "block", date=sow.isoformat(), crop=cid, end=late_e.isoformat()))

    # water
    irr, need = f["irrigations"], c["irrigations_needed"]
    need_here = 2 if (cid == "barley" and f["zone"] == "south_western") else (f"{need}–{c['irrigations_ideal']}" if c["irrigations_ideal"] > need else need)
    if irr is None:
        reasons.append(R("water_unknown", "data", "unknown" if cid == "wheat" else None, need=need))
    elif irr == 0:
        if c["rainfed_ok"]:
            rv = pick_variety(cid, f["zone"], "rainfed")
            reasons.append(R("water_rainfed", "fit", None, crop=cid, variety=(rv or {}).get("name", "desi")))
            timing = "rainfed" if cid == "raya" else timing
        else:
            reasons.append(R("water_none", "caution", "block", crop=cid))
    elif irr < need:
        reasons.append(R("water_short", "caution", "caution", crop=cid, need=f"{need}–{c['irrigations_ideal']}",
                         irr=f["irrigations_bucket"]))
    elif need >= 3 and f["irrigations_bucket"] == "3-4":
        reasons.append(R("water_borderline", "caution", None, crop=cid, need=f"{need}–{c['irrigations_ideal']}",
                         irr=f["irrigations_bucket"]))
    elif need >= 3:
        reasons.append(R("water_ok", "fit", None, irr=f["irrigations_bucket"], need=f"{need}–{c['irrigations_ideal']}"))
    else:
        reasons.append(R("water_low_need", "fit", None, crop=cid, need=need_here))

    # soil, salt, report
    soil, salt = f["soil_type"], f["salt_concern"]
    saline = f["ec"] is not None and f["ec"] > 0.8
    alkali = f["ph"] is not None and f["ph"] > 9.3
    salty_water = f["water_quality"] == "salty"
    if f["ph"] is not None and f["ec"] is not None and not saline and not alkali and cid == "wheat":
        reasons.append(R("report_normal", "fit", None, ph=f["ph"], ec=f["ec"]))
    if saline:
        reasons.append(R("report_saline", "caution", None, ec=f["ec"]))
    if alkali:
        reasons.append(R("report_alkali", "caution", "caution" if cid != "gram" else None, ph=f["ph"]))
    if cid == "gram":
        if saline or alkali:
            reasons.append(R("salt_sensitive", "caution", "block"))
        elif salt:
            reasons.append(R("salt_sensitive", "caution", "caution"))
            reasons.append(R("salt_reported", "data", None))
        if salty_water:
            reasons.append(R("salty_water", "caution", "caution", crop=cid))
        if soil == "clay":
            reasons.append(R("soil_clay_gram", "caution", "caution"))
    elif cid == "barley":
        if salt or saline or alkali or salty_water:
            reasons.append(R("salt_tolerant", "fit", None))
    elif cid == "wheat":
        if salt or saline:
            reasons.append(R("salt_extra_n", "caution", "caution"))
            if salt and not saline and f["ec"] is None:
                reasons.append(R("salt_reported", "data", None))
        if salty_water:
            reasons.append(R("salty_water", "caution", "caution", crop=cid))
    if soil and soil != "salt_affected" and c["soils"].get(soil) == "good":
        reasons.append(R("soil_good", "fit", None, soil=soil, crop=cid))

    if cid == "wheat" and f["previous_crop"] in ("paddy", "basmati"):
        reasons.append(R("after_paddy_wheat", "fit", None))

    variety = pick_variety(cid, f["zone"], timing)
    if f["zone"] == "south_western" and variety and "south_western" in variety["zones"] and f["district"]:
        reasons.append(R("zone_variety", "fit", None, district=f["district"], variety=variety["name"]))

    # weather (advice only; never changes status)
    if weather and weather.get("status") == "ok":
        sm = weather.get("summary", {})
        needs_rauni = not (c["pre_sowing_irrigation"] == "except_after_paddy" and f["previous_crop"] in ("paddy", "basmati"))
        if sm.get("wettest_day") and needs_rauni:
            reasons.append(R("weather_rain", "caution", None, mm=round(sm["wettest_mm"]), day=sm["wettest_day"]))
        tmax = sm.get("tmax_max")
        soon = (sow - today).days <= 10
        if tmax is not None and tmax >= 32 and soon:
            if cid == "gram":
                reasons.append(R("weather_warm_gram", "caution", None, tmax=round(tmax)))
            elif cid == "wheat" and sow < opt_s:
                reasons.append(R("weather_warm_wheat", "caution", None, tmax=round(tmax)))

    if f["tractor"] == "none":
        reasons.append(R("tractor_none", "caution", None))

    affects = {r["affects"] for r in reasons}
    if "block" in affects:
        status = "not_suitable"
    elif "unknown" in affects:
        status = "insufficient_information"
    elif "caution" in affects:
        status = "conditional"
    else:
        status = "feasible"
    return {"crop_id": cid, "status": status, "reasons": reasons, "variety": variety, "timing": timing,
            "sow_date": sow.isoformat(), "sow_date_assumed": assumed_sow, "window": window,
            "late_weeks": late_weeks, "rainfed": rainfed}
