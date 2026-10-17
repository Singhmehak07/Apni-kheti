"""Human-readable values in pa/hi/en (dates, rupees, field values)."""
from __future__ import annotations

from datetime import date

from knowledge import district_by_id, load, t


def rs(n: float | int | None) -> str:
    """Indian digit grouping: 150000 → 1,50,000."""
    if n is None:
        return "—"
    neg = n < 0
    s = str(int(round(abs(n))))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if neg else "") + s


def num(x: float | None) -> str:
    if x is None:
        return "—"
    return str(int(x)) if float(x).is_integer() else f"{x:.2f}".rstrip("0").rstrip(".")


def fmt_date(d: date | str | None, lang: str) -> str:
    if not d:
        return "—"
    if isinstance(d, str):
        d = date.fromisoformat(d)
    m = load("messages")["months"][lang if lang in ("pa", "hi") else "en"][d.month - 1]
    return f"{d.day} {m}"


def fmt_window(start: date, end: date, lang: str) -> str:
    months = load("messages")["months"][lang if lang in ("pa", "hi") else "en"]
    if start.month == end.month:
        return f"{start.day}–{end.day} {months[start.month - 1]}"
    return f"{start.day} {months[start.month - 1]} – {end.day} {months[end.month - 1]}"


def weekday(d: str, lang: str) -> str:
    return load("messages")["weekdays"][lang if lang in ("pa", "hi") else "en"][date.fromisoformat(d).weekday()]


def option_label(field_id: str, option_id: str, lang: str) -> str:
    q = load("questions")["questions"][field_id]
    for o in q.get("options", []):
        if o["id"] == option_id:
            return t(o["label"], lang)
    return option_id


def unit_label(unit: str, lang: str) -> str:
    return t(load("messages")["units"].get(unit, {"en": unit}), lang)


def value_display(field_id: str, value, lang: str) -> str:
    if value is None:
        return ""
    if field_id == "district":
        d = district_by_id(value)
        return t(d, lang) if d else str(value)
    if field_id == "land_area":
        amount, unit, acres = value.get("amount"), value.get("unit", "killa"), value.get("acres")
        txt = f"{num(amount)} {unit_label(unit, lang)}"
        if unit not in ("killa", "acre"):
            txt += f" (≈ {num(round(acres, 2))} {unit_label('acre', lang)})"
        return txt
    if field_id == "field_ready":
        return fmt_date(value.get("date"), lang)
    if field_id == "irrigations":
        return option_label("irrigations", value.get("bucket"), lang)
    if field_id == "budget":
        return f"₹{rs(value.get('rs_per_acre'))}"
    if isinstance(value, str):
        return option_label(field_id, value, lang)
    return str(value)


def crop_name(crop_id: str, lang: str) -> str:
    from knowledge import crops
    c = crops().get(crop_id)
    if c:
        return t(c["names"], lang)
    return option_label("usual_crop", crop_id, lang)
