"""Flatten interview state + soil report into plain facts for the rules engine."""
from __future__ import annotations

from datetime import date

from knowledge import district_zone


def facts_from_state(state: dict) -> dict:
    F = state["fields"]

    def val(fid):
        return F[fid]["value"] if F[fid]["status"] == "answered" else None

    land = val("land_area") or {}
    irr = val("irrigations")
    ready = val("field_ready")
    budget = val("budget")
    rep = (state.get("report") or {}).get("params") or {}
    soil = val("soil_type")
    missing = [f for f in ("district", "land_area", "soil_type", "water_source", "irrigations", "field_ready", "usual_crop")
               if F[f]["status"] in ("not_available", "not_provided", "pending")]
    return {
        "district": val("district"),
        "zone": district_zone(val("district")),
        "acres": land.get("acres"),
        "soil_type": soil,
        "salt_concern": bool(state["extras"].get("salt_concern")) or soil == "salt_affected",
        "water_source": val("water_source"),
        "water_quality": val("water_quality"),
        "irrigations": irr.get("count") if irr else None,
        "irrigations_bucket": irr.get("bucket") if irr else None,
        "usual_crop": val("usual_crop"),
        "previous_crop": val("previous_crop"),
        "sow_date": date.fromisoformat(ready["date"]) if ready else None,
        "tractor": val("tractor"),
        "budget": budget.get("rs_per_acre") if budget else None,
        "ph": (rep.get("ph") or {}).get("value"),
        "ec": (rep.get("ec") or {}).get("value"),
        "oc": (rep.get("oc") or {}).get("value"),
        "missing": missing,
    }
