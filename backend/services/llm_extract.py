"""LLM fallback for answers the deterministic parser could not understand.

One Gemini Flash-Lite call with a JSON schema extracts *all* farm fields mentioned in
the answer; every value is then re-validated by the same rules as the fast path.
"""
from __future__ import annotations

from datetime import date, timedelta

from integrations import gemini
from knowledge import districts, load
from .extract import ACRE_UNITS, IRR_VALUE, ParseResult, bucket_irrigations

ENUMS = {
    "soil_report": ["yes", "no"],
    "soil_type": ["sandy", "loam", "clay", "salt_affected"],
    "water_source": ["canal", "tubewell", "both", "rain"],
    "water_quality": ["sweet", "salty"],
    "usual_crop": ["wheat", "raya", "gram", "barley", "potato", "other"],
    "previous_crop": ["paddy", "basmati", "cotton", "maize", "fallow", "other"],
    "tractor": ["own", "rent", "none"],
}


def schema() -> dict:
    props: dict = {
        "understood": {"type": "boolean", "description": "true only if the answer clearly answers the asked question"},
        "dont_know": {"type": "boolean", "description": "farmer says they don't know / don't have this"},
        "district": {"type": "string", "enum": [d["id"] for d in districts()]},
        "land_amount": {"type": "number", "minimum": 0},
        "land_unit": {"type": "string", "enum": list(ACRE_UNITS.keys())},
        "salt_concern": {"type": "boolean"},
        "irrigations_count": {"type": "integer", "minimum": 0, "maximum": 20},
        "field_ready_date": {"type": "string", "description": "YYYY-MM-DD"},
        "budget_rs_per_acre": {"type": "integer", "minimum": 0},
    }
    for k, v in ENUMS.items():
        props[k] = {"type": "string", "enum": v}
    return {"type": "object", "properties": props, "required": ["understood", "dont_know"]}


SYSTEM = ("You read a Punjab farmer's short spoken answer (Punjabi, Hindi, English or mixed; it may be an imperfect "
          "speech transcript) and extract farm facts. Fill a field ONLY if the farmer clearly stated it; never guess "
          "or use defaults. 'killa' means acre. If the farmer says they do not know or do not have the thing asked, "
          "set dont_know=true. Dates are in the coming rabi sowing season.")


async def extract(text: str, field_id: str, lang: str, today: date) -> dict[str, ParseResult]:
    q = load("questions")["questions"][field_id]
    dlist = "; ".join(f"{d['id']}={d['en']}/{d['pa']}" for d in districts())
    prompt = (f"Today is {today.isoformat()}.\nQuestion asked (field '{field_id}'): {q['prompt']['en']}\n"
              f"Farmer's answer: \"{text}\"\nDistrict ids: {dlist}\nReturn JSON.")
    out = await gemini.generate_json(prompt, schema(), system=SYSTEM)
    return to_results(out, field_id, today)


def to_results(out: dict, field_id: str, today: date) -> dict[str, ParseResult]:
    res: dict[str, ParseResult] = {}
    if out.get("dont_know") and not out.get("understood", False):
        res[field_id] = ParseResult("unknown")
    for k in ENUMS:
        v = out.get(k)
        if v in ENUMS[k]:
            res[k] = ParseResult("ok", v, extra={"salt_concern": True} if v == "salt_affected" else {})
    if out.get("district") in {d["id"] for d in districts()}:
        res["district"] = ParseResult("ok", out["district"])
    amt, unit = out.get("land_amount"), out.get("land_unit") or "killa"
    if isinstance(amt, (int, float)):
        factor = ACRE_UNITS.get(unit, (None, 1.0))[1]
        if unit == "bigha" or factor is None:
            res["land_area"] = ParseResult("invalid", code="bigha_unit")
        elif 0 < amt * factor <= 500:
            res["land_area"] = ParseResult("ok", {"acres": round(amt * factor, 3), "amount": amt, "unit": unit})
        else:
            res["land_area"] = ParseResult("invalid", code="invalid_area")
    n = out.get("irrigations_count")
    if isinstance(n, int) and 0 <= n <= 20:
        b = bucket_irrigations(n)
        res["irrigations"] = ParseResult("ok", {"bucket": b, "count": min(n, IRR_VALUE[b] if n > 5 else n)})
    d = out.get("field_ready_date")
    if isinstance(d, str):
        try:
            dd = date.fromisoformat(d[:10])
            if today - timedelta(days=7) <= dd <= today + timedelta(days=120):
                res["field_ready"] = ParseResult("ok", {"date": max(dd, today).isoformat()})
        except ValueError:
            pass
    b = out.get("budget_rs_per_acre")
    if isinstance(b, int) and 1000 <= b <= 200000:
        res["budget"] = ParseResult("ok", {"rs_per_acre": b})
    if out.get("salt_concern") and "soil_type" not in res:
        res["_salt_concern"] = ParseResult("ok", True)
    if not out.get("understood") and field_id in res and res[field_id].status == "ok" and field_id in ("soil_report", "tractor"):
        # yes/no style fields: only trust when the model says it understood
        res.pop(field_id)
    return res
