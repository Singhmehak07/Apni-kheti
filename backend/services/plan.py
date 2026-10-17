"""Workflow step 7: dated growing guidance for the crop the farmer chose."""
from __future__ import annotations

from datetime import date, timedelta

from knowledge import crops, load, t
from .display import fmt_date, fmt_window, num, rs
from .reasons import render
from .rules import season_date

def _offset(spec, sow: date, days: int, today: date) -> date:
    if isinstance(spec, int):
        return sow + timedelta(days=spec)
    if spec == "duration":
        return sow + timedelta(days=days)
    if spec == "duration+10":
        return sow + timedelta(days=days + 10)
    if isinstance(spec, str) and spec.startswith("abs:"):
        return season_date(today, spec[4:])
    return sow


def build(rec: dict, crop_id: str, today: date) -> dict:
    ev = next(c for c in rec["crops"] if c["crop_id"] == crop_id)
    c = crops()[crop_id]
    f = rec["facts"]
    sow = date.fromisoformat(ev["sow_date"])
    var = ev.get("variety") or {}
    days = var.get("days") or c["duration_days"]
    seed_rate = var.get("seed_kg_acre") or c["seed_kg_acre"]
    acres = f.get("acres")
    steps = []
    wx = rec["context"]["weather"]
    if wx.get("status") == "ok" and wx["summary"].get("wettest_day"):
        steps.append({"id": "weather", "icon": "weather", "start": today.isoformat(), "end": (today + timedelta(days=6)).isoformat(),
                      "reason": {"code": "weather_rain", "params": {"mm": round(wx["summary"]["wettest_mm"]),
                                                                       "day": wx["summary"]["wettest_day"]}}})
    for s in load("plans")["crops"][crop_id]:
        start, end = _offset(s["start"], sow, days, today), _offset(s["end"], sow, days, today)
        if s.get("min_offset") is not None:
            start = max(start, sow + timedelta(days=s["min_offset"]))
            end = max(end, start)
        variant = "after_paddy" if s.get("after_paddy") and f.get("previous_crop") in ("paddy", "basmati") else "text"
        steps.append({"id": s["id"], "icon": s["icon"], "start": start.isoformat(), "end": end.isoformat(),
                      "variant": variant, "text_ref": s.get("text_ref")})
    harvest_end = _offset("duration+10", sow, days, today)
    steps.append({"id": "sell", "icon": "sell", "start": harvest_end.isoformat(),
                  "end": (harvest_end + timedelta(days=20)).isoformat()})
    steps.sort(key=lambda x: (x["start"], x["id"] != "weather"))
    eco = ev["economics"]
    return {"crop_id": crop_id, "recommendation_id": rec["id"], "status": ev["status"], "variety": var.get("name"),
            "sow_date": ev["sow_date"], "window": ev["window"], "days": days, "seed_rate": seed_rate,
            "acres": acres, "salt": bool(f.get("salt_concern") or (f.get("ec") or 0) > 0.8),
            "msp": eco["msp_rs_q"], "economics": eco, "steps": steps, "reasons": ev["reasons"]}


def view(plan: dict, lang: str, today: date) -> dict:
    c = crops()[plan["crop_id"]]
    titles = load("plans")["titles"]
    steps_src = {s["id"]: s for s in load("plans")["crops"][plan["crop_id"]]}
    ferts = load("messages")["fertiliser"]
    w0, w1 = (date.fromisoformat(x) for x in plan["window"])
    acres = plan["acres"]
    seed_total = num(round(plan["seed_rate"] * acres, 1)) if acres else num(plan["seed_rate"])
    params = {"variety": plan["variety"] or "PAU", "seed_total": seed_total, "seed_rate": num(plan["seed_rate"]),
              "sow_date": fmt_date(plan["sow_date"], lang), "window": fmt_window(w0, w1, lang), "days": plan["days"],
              "msp": rs(plan["msp"])}
    out = []
    for s in plan["steps"]:
        if s["id"] == "weather":
            text = render({"code": "weather_rain", "params": s["reason"]["params"]}, lang)
        elif s["id"] == "sell":
            text = t(load("plans")["common"]["sell"], lang).format(**params)
        elif s.get("text_ref"):
            text = t(ferts[s["text_ref"]], lang)
            if plan["crop_id"] == "wheat" and plan["salt"]:
                text += " " + render({"code": "salt_extra_n", "params": {}}, lang)
        else:
            src = steps_src[s["id"]]
            text = t(src.get(s.get("variant", "text")) or src["text"], lang).format(**params)
        category = s.get("category", steps_src.get(s["id"], {}).get("category", "general"))
        dosage = ""
        if s.get("dosage"):
            dosage = t(s["dosage"], lang)
        elif s["id"] in steps_src and steps_src[s["id"]].get("dosage"):
            dosage = t(steps_src[s["id"]]["dosage"], lang)

        st, en = date.fromisoformat(s["start"]), date.fromisoformat(s["end"])
        when = fmt_date(st, lang) if st == en else fmt_window(st, en, lang)
        state = "done" if en < today else ("now" if st <= today <= en else "upcoming")
        out.append({"id": s["id"], "icon": s["icon"], "category": category, "dosage": dosage,
                    "title": t(titles[s["id"]], lang), "text": text,
                    "start": s["start"], "end": s["end"], "when": when, "state": state})
    eco = plan["economics"]
    harvest = next((s for s in out if s["id"] == "harvest"), None)
    reminders = [st for st in out if st.get("category") in ("fertilizer", "pesticide")]
    return {"id": plan["id"], "crop_id": plan["crop_id"], "name": t(c["names"], lang), "color": c["color"],
            "variety": plan["variety"], "acres": acres, "sow_date_label": fmt_date(plan["sow_date"], lang),
            "harvest_label": harvest["when"] if harvest else None, "steps": out, "reminders": reminders,
            "summary": {"yield_base_q_acre": eco["yield_q_acre"]["base"], "net_base_rs_acre": eco["net_rs_acre"]["base"],
                        "net_total": eco["net_total"], "cost_rs_acre": eco["cost_rs_acre"], "msp": eco["msp_rs_q"]},
            "lang": lang}
