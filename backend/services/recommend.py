"""Workflow steps 3–5: add weather & market context → evaluate crops → compare returns."""
from __future__ import annotations

import asyncio
from datetime import date

from config import get_settings
from integrations import market, weather
from integrations.http import Timer
from knowledge import crops, load, t
from . import economics
from .display import fmt_date, fmt_window, weekday
from .facts import facts_from_state
from .reasons import render_all
from .rules import STATUS_ORDER, R, evaluate_crop

TYPE_ORDER = {"fit": 0, "money": 1, "caution": 2, "data": 3, "info": 4}


async def context(state: dict, timer: Timer | None = None) -> dict:
    timer = timer or Timer()
    district = state["fields"]["district"]["value"] if state["fields"]["district"]["status"] == "answered" else None

    async def w():
        with timer.span("weather"):
            return await weather.forecast(district) if district else {"status": "unavailable", "reason": "no_district"}

    async def m():
        with timer.span("market"):
            return await market.prices(list(crops().keys()))

    async def r():
        if not district:
            return None
        with timer.span("ml_rainfall"):
            try:
                from ml.src.predict_rainfall import RainfallPredictor
                today = get_settings().today()
                rp = RainfallPredictor()
                return rp.predict_month(district=district, target_month=today.month, target_year=today.year)
            except Exception:
                return None

    wx, mk, rf = await asyncio.gather(w(), m(), r())
    res = {"weather": wx, "market": mk}
    if rf:
        res["rainfall_ml"] = rf
    return res


def evaluate(state: dict, ctx: dict, today: date) -> dict:
    f = facts_from_state(state)
    out = []
    for cid in crops():
        ev = evaluate_crop(cid, f, ctx.get("weather"), today)
        eco = economics.compute(cid, ev, f, ctx["market"][cid])
        ev["economics"] = eco
        pr = eco["price"]
        if pr["kind"] == "msp_benchmark":
            ev["reasons"].append(R("price_benchmark", "info", None, crop=cid, msp=eco["msp_rs_q"]))
        else:
            ev["reasons"].append(R("price_mandi", "info", None, avg=pr["avg"], scope=pr["scope"], date=pr["date"]))
        ev["reasons"].append(R("money_base", "money", None, net=eco["net_rs_acre"]["base"]))
        if f["budget"]:
            if eco["cost_rs_acre"] > f["budget"]:
                ev["reasons"].append(R("budget_over", "caution", None, cost=eco["cost_rs_acre"], budget=f["budget"]))
            else:
                ev["reasons"].append(R("budget_ok", "money", None, cost=eco["cost_rs_acre"]))
        out.append(ev)
    usual = f["usual_crop"]
    by_id = {e["crop_id"]: e for e in out}
    if usual in by_id:
        base_usual = by_id[usual]["economics"]["net_rs_acre"]["base"]
        for e in out:
            if e["crop_id"] == usual:
                e["reasons"].append(R("is_usual", "info", None))
                e["vs_usual"] = 0
            else:
                diff = e["economics"]["net_rs_acre"]["base"] - base_usual
                e["vs_usual"] = diff
                e["reasons"].append(R("vs_usual_more" if diff >= 0 else "vs_usual_less", "money", None,
                                      diff=abs(diff), usual=usual))
    if f["missing"]:
        for e in out:
            e["reasons"].append(R("missing_info", "data", None, fields=f["missing"]))
    out.sort(key=lambda e: (STATUS_ORDER[e["status"]], -e["economics"]["net_rs_acre"]["base"]))
    for i, e in enumerate(out):
        e["rank"] = i + 1
        e["reasons"].sort(key=lambda r: TYPE_ORDER.get(r["type"], 9))
    s = get_settings()
    ml_status = "skipped"
    ml_result = None
    if s.ml_enabled:
        try:
            from ml.src.predict import CropPredictor
            cp = CropPredictor()
            rep = state.get("report") or {}
            params = rep.get("params") or {}
            n_val = (params.get("n") or {}).get("value") or (params.get("nitrogen") or {}).get("value")
            p_val = (params.get("p") or {}).get("value") or (params.get("phosphorus") or {}).get("value")
            k_val = (params.get("k") or {}).get("value") or (params.get("potassium") or {}).get("value")
            ph_val = f.get("ph") or (params.get("ph") or {}).get("value")

            wx = ctx.get("weather") or {}
            sm = wx.get("summary") or {}
            temp = sm.get("tmax_avg")
            days = wx.get("days") or []
            rhs = [d["rh"] for d in days if d.get("rh") is not None]
            humidity = (sum(rhs) / len(rhs)) if rhs else None
            rainfall = sm.get("rain_total_mm")

            features = {
                "N": n_val, "P": p_val, "K": k_val,
                "temperature": temp, "humidity": humidity,
                "ph": ph_val, "rainfall": rainfall
            }
            res = cp.predict(
                features,
                mode="rules_with_ml",
                regional_approved=True,
                candidate_crop=usual
            )
            ml_status = res["ml_status"]
            ml_result = res
        except Exception as exc:
            ml_status = "skipped"
            ml_result = {"ml_status": "skipped", "ml_skip_reasons": [str(exc)]}

    fs = {**f, "sow_date": f["sow_date"].isoformat() if f["sow_date"] else None}
    ret = {"crops": out, "facts": fs, "usual_crop": usual, "ml_status": ml_status, "engine": "rules_v1",
           "today": today.isoformat()}
    if ml_result:
        ret["ml_result"] = ml_result
    return ret


def view(rec: dict, lang: str) -> dict:
    """Language-specific view of a stored recommendation."""
    heads = load("messages")["headlines"]
    sources = load("sources")
    crops_v = []
    for e in rec["crops"]:
        c = crops()[e["crop_id"]]
        w0, w1 = (date.fromisoformat(x) for x in e["window"])
        crops_v.append({
            "crop_id": e["crop_id"], "name": t(c["names"], lang), "color": c["color"], "rank": e["rank"],
            "status": e["status"], "headline": t(heads[e["status"]], lang),
            "variety": (e.get("variety") or {}).get("name"), "sow_date": e["sow_date"],
            "sow_date_label": fmt_date(e["sow_date"], lang), "sow_date_assumed": e["sow_date_assumed"],
            "window_label": fmt_window(w0, w1, lang), "reasons": render_all(e["reasons"], lang),
            "economics": e["economics"], "vs_usual": e.get("vs_usual"),
            "sources": [{"id": s, **sources[s]} for s in c["source_ids"] + [e["economics"]["price"]["source_id"]]
                        if s in sources],
        })
    wx = rec["context"]["weather"]
    if wx.get("status") == "ok":
        wx = {**wx, "days": [{**d, "label": weekday(d["date"], lang), "date_label": fmt_date(d["date"], lang)}
                             for d in wx["days"]]}
    v = {"id": rec["id"], "crops": crops_v, "usual_crop": rec["usual_crop"], "facts": rec["facts"],
         "weather": wx, "ml_status": rec["ml_status"], "engine": rec["engine"], "lang": lang,
         "timings_ms": rec.get("timings_ms")}
    if "ml_result" in rec:
        v["ml_result"] = rec["ml_result"]
    if "rainfall_ml" in rec.get("context", {}):
        v["rainfall_ml"] = rec["context"]["rainfall_ml"]
    return v
