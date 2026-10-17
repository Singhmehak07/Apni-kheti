"""Render reason codes + raw params into farmer-friendly text in pa / hi / en."""
from __future__ import annotations

from knowledge import district_by_id, load, t
from .display import crop_name, fmt_date, fmt_window, num, option_label, rs
from datetime import date

DATE_KEYS = {"date", "start", "end", "day"}
MONEY_KEYS = {"cost", "budget", "diff", "net", "msp", "avg"}


def fmt_param(key: str, val, lang: str) -> str:
    if val is None:
        return "—"
    if key in DATE_KEYS:
        return fmt_date(val, lang)
    if key == "window":
        return fmt_window(date.fromisoformat(val[0]), date.fromisoformat(val[1]), lang)
    if key in ("crop", "usual"):
        return crop_name(val, lang)
    if key == "district":
        d = district_by_id(val)
        return t(d, lang) if d else str(val)
    if key == "soil":
        return option_label("soil_type", val, lang)
    if key == "irr":
        return option_label("irrigations", val, lang)
    if key in MONEY_KEYS:
        return rs(val)
    if key == "fields":
        qs = load("questions")["questions"]
        return ", ".join(t(qs[f]["label"], lang) for f in val)
    if isinstance(val, float):
        return num(val)
    return str(val)


def render(reason: dict, lang: str) -> str:
    tpl = t(load("messages")["reasons"][reason["code"]], lang)
    params = {k: fmt_param(k, v, lang) for k, v in reason["params"].items()}
    try:
        return tpl.format(**params)
    except KeyError:
        return tpl


def render_all(reasons: list[dict], lang: str) -> list[dict]:
    return [{"code": r["code"], "type": r["type"], "affects": r["affects"], "text": render(r, lang)} for r in reasons]
