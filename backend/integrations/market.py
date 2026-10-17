"""Mandi prices: live AGMARKNET feed on data.gov.in when a key is configured, otherwise a
dated snapshot. When neither has the crop, MSP is used as a clearly labelled benchmark."""
from __future__ import annotations

import time
from datetime import datetime

from config import get_settings
from knowledge import load
from . import http

_CACHE: dict[str, tuple[float, dict]] = {}
TTL_S = 6 * 3600


def _snapshot(crop: str) -> dict | None:
    snap = load("economics")["market_snapshot"]
    p = snap["prices"].get(crop)
    if not p:
        return None
    return {"kind": "mandi_snapshot", "min": p["min"], "avg": p["avg"], "max": p["max"], "scope": p["scope"],
            "date": p["date"], "source_id": snap["source_id"]}


def _benchmark(crop: str) -> dict:
    msp = load("economics")["msp"]
    v = msp["rs_per_quintal"][crop]
    return {"kind": "msp_benchmark", "min": v, "avg": v, "max": v, "scope": "MSP", "date": msp["announced"],
            "source_id": msp["source_id"]}


async def _live(crop: str) -> dict | None:
    s = get_settings()
    if not s.data_gov_api_key:
        return None
    names = load("economics")["market_snapshot"]["commodity_names"].get(crop, [])
    for name in names:
        params = {"api-key": s.data_gov_api_key, "format": "json", "limit": 500,
                  "filters[state.keyword]": "Punjab", "filters[commodity]": name}
        try:
            resp = await http.request("GET", f"{s.data_gov_base_url}/{s.agmarknet_resource_id}", params=params,
                                      timeout=6.0, retries=0)
            if resp.status_code != 200:
                continue
            recs = resp.json().get("records", [])
        except Exception:
            return None
        if not recs:
            continue
        def num(r, k):
            try:
                return float(r.get(k))
            except (TypeError, ValueError):
                return None
        latest = max(recs, key=lambda r: datetime.strptime(r.get("arrival_date", "01/01/1970"), "%d/%m/%Y"))
        day = latest.get("arrival_date")
        rows = [r for r in recs if r.get("arrival_date") == day]
        mins = [v for r in rows if (v := num(r, "min_price"))]
        maxs = [v for r in rows if (v := num(r, "max_price"))]
        modal = [v for r in rows if (v := num(r, "modal_price"))]
        if not modal:
            continue
        return {"kind": "mandi_live", "min": min(mins or modal), "avg": round(sum(modal) / len(modal), 1),
                "max": max(maxs or modal), "scope": f"Punjab, {len(rows)} mandi(s)",
                "date": datetime.strptime(day, "%d/%m/%Y").date().isoformat(), "source_id": "agmarknet"}
    return None


async def price(crop: str) -> dict:
    hit = _CACHE.get(crop)
    if hit and time.time() - hit[0] < TTL_S:
        return hit[1]
    result = await _live(crop) or _snapshot(crop) or _benchmark(crop)
    _CACHE[crop] = (time.time(), result)
    return result


async def prices(crops: list[str]) -> dict[str, dict]:
    import asyncio
    vals = await asyncio.gather(*(price(c) for c in crops))
    return dict(zip(crops, vals))
