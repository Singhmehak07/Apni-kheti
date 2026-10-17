"""Low / base / high return per acre, above listed costs (A2+FL), with every assumption labelled."""
from __future__ import annotations

from knowledge import crops, load


def compute(cid: str, ev: dict, f: dict, price: dict) -> dict:
    c = crops()[cid]
    eco = load("economics")
    avg = c["state_avg_yield_q_acre"]
    var = ev.get("variety") or {}
    assumptions = ["low_yield", "cost_basis", "excludes_straw"]
    if ev.get("rainfed") and cid == "raya" and var.get("window") == "rainfed":
        high = var["yield_q_acre"]
        base = high
        assumptions.append("rainfed_variety")
    else:
        high = var.get("yield_q_acre") or max((v["yield_q_acre"] or 0) for v in c["varieties"]) or avg
        base = avg
        assumptions.append("high_variety")
    low = base * c["low_yield_factor"]
    penalty = 0.0
    if cid == "wheat" and ev.get("late_weeks"):
        penalty = ev["late_weeks"] * c["late_penalty_q_per_week"]
        assumptions.append("late_penalty")
    y = {k: round(max(0.0, v - penalty), 2) for k, v in (("low", low), ("base", base), ("high", high))}
    p = {"low": price["min"], "base": price["avg"], "high": price["max"]}
    cop = eco["cost_of_production"]["rs_per_quintal"][cid]
    cost = round(cop * avg)
    gross = {k: round(y[k] * p[k]) for k in y}
    net = {k: gross[k] - cost for k in y}
    acres = f.get("acres")
    msp = eco["msp"]["rs_per_quintal"][c["msp_key"]]
    return {
        "yield_q_acre": y, "price_rs_q": p, "price": price, "cost_rs_acre": cost, "cop_rs_q": cop,
        "gross_rs_acre": gross, "net_rs_acre": net, "acres": acres,
        "net_total": {k: round(v * acres) for k, v in net.items()} if acres else None,
        "msp_rs_q": msp, "gross_at_msp_base": round(y["base"] * msp),
        "late_penalty_q": penalty, "assumptions": assumptions,
    }
