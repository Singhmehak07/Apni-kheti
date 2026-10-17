"""Interview engine: one question at a time, re-ask when unclear (max 2), leave a field
empty when the farmer doesn't know, and let one answer fill several fields."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from config import get_settings
from integrations.http import Timer
from knowledge import district_by_id, districts, load, t
from . import llm_extract
from .display import value_display
from .extract import IRR_VALUE, ParseResult, field_ready_options, opportunistic, parse_field

log = logging.getLogger("flow")
ORDER: list[str] = load("questions")["order"]
QUESTIONS: dict = load("questions")["questions"]
COMMON: dict = load("questions")["common"]
BUDGET_BUCKETS = [(15000, "low"), (25000, "mid"), (10 ** 9, "high")]


def new_state(lang: str) -> dict:
    return {
        "lang": lang,
        "fields": {f: {"status": "pending", "value": None, "source": None, "attempts": 0, "raw": None, "via": None}
                   for f in ORDER},
        "extras": {"salt_concern": False},
        "report": None,
        "history": [],
        "confirmed": False,
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def _set(state: dict, fid: str, status: str, value=None, source: str | None = "farmer", raw=None, via=None) -> None:
    f = state["fields"][fid]
    f.update(status=status, value=value, source=source if status == "answered" else None)
    if raw is not None:
        f["raw"] = raw
    if via is not None:
        f["via"] = via


def apply_skips(state: dict) -> None:
    F = state["fields"]
    ws = F["water_source"]
    if ws["status"] == "answered" and ws["value"] in ("canal", "rain") and F["water_quality"]["status"] == "pending":
        F["water_quality"]["status"] = "skipped"
    if ws["status"] == "answered" and ws["value"] == "rain" and F["irrigations"]["status"] == "pending":
        _set(state, "irrigations", "answered", {"bucket": "0", "count": 0}, source="derived")


def reset_dependents(state: dict, fid: str) -> None:
    F = state["fields"]
    if fid == "water_source":
        if F["water_quality"]["status"] == "skipped":
            F["water_quality"].update(status="pending", attempts=0)
        if F["irrigations"]["source"] == "derived":
            F["irrigations"].update(status="pending", value=None, source=None, attempts=0)


def next_field(state: dict) -> str | None:
    apply_skips(state)
    return next((f for f in ORDER if state["fields"][f]["status"] == "pending"), None)


def _progress(state: dict, fid: str | None) -> dict:
    active = [f for f in ORDER if state["fields"][f]["status"] != "skipped"]
    done = sum(1 for f in active if state["fields"][f]["status"] not in ("pending",))
    return {"done": done, "total": len(active)}


def question_payload(state: dict, fid: str, lang: str, today: date, feedback_code: str | None = None) -> dict:
    q = QUESTIONS[fid]
    attempts = state["fields"][fid]["attempts"]
    if attempts == 0:
        text = t(q["prompt"], lang)
    else:
        prefix = t(COMMON.get(feedback_code) or COMMON["retry_prefix"], lang)
        text = f"{prefix} {t(q['rephrase'], lang)}"
        if attempts >= 2:
            text += " " + t(COMMON["retry_last"], lang)
    payload = {"field": fid, "kind": q["kind"], "icon": q["icon"], "label": t(q["label"], lang), "text": text,
               "base_prompt": t(q["prompt"], lang), "attempt": attempts, "options": [],
               "dont_know_label": t(COMMON["dont_know"], lang), "progress": _progress(state, fid)}
    if q["kind"] == "choice":
        payload["options"] = [{"id": o["id"], "icon": o["icon"], "label": t(o["label"], lang)} for o in q["options"]]
    elif q["kind"] == "district":
        payload["options"] = [{"id": d["id"], "icon": "map-pin", "label": t(d, lang),
                               "sub": d["en"] if lang != "en" else d["pa"]} for d in districts()]
    elif q["kind"] == "number":
        payload["units"] = [{"id": u["id"], "label": t(u["label"], lang), "acres": u["acres"]} for u in q["units"]]
    elif q["kind"] == "date":
        opts = field_ready_options(today, load("questions")["field_ready_options"])
        payload["options"] = [{"id": o["id"], "icon": "calendar", "label": t(o["label"], lang), "date": o["date"]} for o in opts]
    return payload


def _value_from_option(fid: str, option_id: str, today: date):
    q = QUESTIONS[fid]
    if q["kind"] == "district":
        return option_id if district_by_id(option_id) else None
    if q["kind"] == "date":
        opts = field_ready_options(today, load("questions")["field_ready_options"])
        o = next((o for o in opts if o["id"] == option_id), None)
        return {"date": o["date"], "option": option_id} if o else None
    o = next((o for o in q.get("options", []) if o["id"] == option_id), None)
    if not o:
        return None
    if fid == "irrigations":
        return {"bucket": option_id, "count": IRR_VALUE[option_id]}
    if fid == "budget":
        return {"rs_per_acre": o["value"], "bucket": option_id}
    return option_id


def _value_from_numeric(fid: str, value: dict) -> ParseResult:
    if fid == "land_area":
        try:
            amount = float(value.get("amount"))
        except (TypeError, ValueError):
            return ParseResult("invalid", code="invalid_area")
        unit = value.get("unit", "killa")
        units = {u["id"]: u["acres"] for u in QUESTIONS["land_area"]["units"]}
        units.update({"acre": 1.0, "marla": 1 / 160})
        if unit not in units:
            return ParseResult("invalid", code="invalid_area")
        acres = round(amount * units[unit], 3)
        if acres <= 0 or acres > 500:
            return ParseResult("invalid", code="invalid_area")
        return ParseResult("ok", {"acres": acres, "amount": amount, "unit": unit})
    if fid == "budget":
        try:
            v = int(value.get("rs_per_acre"))
        except (TypeError, ValueError):
            return ParseResult("invalid")
        return ParseResult("ok", {"rs_per_acre": v}) if 1000 <= v <= 200000 else ParseResult("invalid", code="invalid_budget")
    if fid == "field_ready":
        try:
            date.fromisoformat(value.get("date"))
            return ParseResult("ok", {"date": value["date"]})
        except (TypeError, ValueError):
            return ParseResult("invalid")
    return ParseResult("invalid")


def _normalise_value(fid: str, value):
    if fid == "budget" and isinstance(value, dict) and "bucket" not in value:
        v = value["rs_per_acre"]
        value = {**value, "bucket": next(b for lim, b in BUDGET_BUCKETS if v < lim or lim == 10 ** 9)}
    return value


async def handle_answer(state: dict, fid: str, *, option_id: str | None = None, value: dict | None = None,
                        text: str | None = None, skip: bool = False, via: str = "typed",
                        timer: Timer | None = None, editing: bool = False) -> dict:
    s = get_settings()
    timer = timer or Timer()
    lang = state["lang"]
    today = s.today()
    f = state["fields"][fid]
    understood: list[dict] = []
    feedback = None
    used_llm = False

    def accept(field_id: str, r: ParseResult, source: str = "farmer"):
        v = _normalise_value(field_id, r.value)
        if field_id != fid:
            reset_dependents(state, field_id)
        _set(state, field_id, "answered", v, source=source, raw=text, via=via)
        if r.extra.get("salt_concern"):
            state["extras"]["salt_concern"] = True
        if field_id == "soil_type" and v != "salt_affected" and not r.extra.get("salt_concern"):
            state["extras"]["salt_concern"] = False
        understood.append({"field": field_id, "label": t(QUESTIONS[field_id]["label"], lang),
                           "display": value_display(field_id, v, lang)})

    if editing:
        reset_dependents(state, fid)
    if skip:
        _set(state, fid, "not_available", None, via=via)
        result = "not_available"
    elif option_id is not None:
        v = _value_from_option(fid, option_id, today)
        if v is None:
            result, feedback = "unclear", "retry_prefix"
        else:
            accept(fid, ParseResult("ok", v, extra={"salt_concern": v == "salt_affected"}))
            result = "accepted"
    elif value is not None:
        r = _value_from_numeric(fid, value)
        if r.status == "ok":
            accept(fid, r)
            result = "accepted"
        else:
            result, feedback = "unclear", r.code
    else:
        text = (text or "").strip()
        with timer.span("parse"):
            r = parse_field(fid, text, today)
            extra = opportunistic(text, fid)
        if r.status in ("unclear", "invalid") and r.code != "bigha_unit" and s.llm_enabled and text:
            try:
                with timer.span("llm_extract"):
                    llm = await llm_extract.extract(text, fid, lang, today)
                used_llm = True
                if fid in llm:
                    r = llm.pop(fid)
                if llm.pop("_salt_concern", None):
                    state["extras"]["salt_concern"] = True
                for k, v in llm.items():
                    if v.status == "ok":
                        extra.setdefault(k, v)
            except Exception as exc:  # LLM down → deterministic result stands
                log.warning("llm extract failed: %s", exc)
        for k, v in extra.items():
            if k in state["fields"] and state["fields"][k]["status"] == "pending" and v.status == "ok":
                accept(k, v, source="farmer")
        if r.status == "ok":
            accept(fid, r)
            result = "accepted"
        elif r.status == "unknown":
            _set(state, fid, "not_available", None, raw=text, via=via)
            result = "not_available"
        else:
            feedback = r.code
            result = "unclear"
    if result == "unclear" and not editing:
        f["attempts"] += 1
        if f["attempts"] > s.max_reasks:
            _set(state, fid, "not_provided", None, raw=text, via=via)
            result = "not_provided"
    if result != "unclear" and fid not in state["history"]:
        state["history"].append(fid)
    understood.sort(key=lambda u: u["field"] != fid)
    nxt = next_field(state)
    out = {"result": result, "field": fid, "understood": understood, "feedback_code": feedback, "used_llm": used_llm,
           "action": "upload_report" if (fid == "soil_report" and f["value"] == "yes" and not state.get("report")) else None,
           "done": nxt is None, "next": None, "timings_ms": timer.done()}
    if result == "unclear":
        out["next"] = question_payload(state, fid, lang, today, feedback)
    elif nxt:
        out["next"] = question_payload(state, nxt, lang, today)
    return out


def go_back(state: dict) -> str | None:
    while state["history"]:
        fid = state["history"].pop()
        if state["fields"][fid]["source"] == "derived":
            continue
        state["fields"][fid].update(status="pending", value=None, source=None, attempts=0)
        reset_dependents(state, fid)
        return fid
    return None


def profile_view(state: dict, lang: str) -> dict:
    items = []
    for fid in ORDER:
        f = state["fields"][fid]
        if f["status"] == "skipped":
            continue
        q = QUESTIONS[fid]
        prov = {"answered": "report" if f["source"] == "report" else ("derived" if f["source"] == "derived" else "farmer"),
                "not_available": "not_available", "not_provided": "not_available", "pending": "not_available"}[f["status"]]
        items.append({"field": fid, "label": t(q["label"], lang), "icon": q["icon"], "kind": q["kind"],
                      "status": f["status"], "value": f["value"], "display": value_display(fid, f["value"], lang),
                      "provenance": prov, "via": f["via"]})
    return {"items": items, "report": state.get("report"), "salt_concern": state["extras"].get("salt_concern", False),
            "confirmed": state.get("confirmed", False)}
