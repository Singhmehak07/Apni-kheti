"""'Why this crop' — LLM-structured explanation with a number-hallucination guard.

Deterministic reasons are always available instantly; this endpoint upgrades them into
short, plain-language reasons. Any LLM sentence containing a number that is not in the
facts we supplied is dropped; if nothing survives, the template reasons are used.
"""
from __future__ import annotations

import json
import logging
import re

from config import get_settings
from integrations import gemini
from integrations.http import Timer
from knowledge import crops
from .text_norm import normalize

log = logging.getLogger("explain")
LANG_NAME = {"pa": "Punjabi in Gurmukhi script", "hi": "Hindi in Devanagari script", "en": "simple English"}
_NUM = re.compile(r"\d+(?:[.,]\d+)*")


def numbers_in(text: str) -> set[float]:
    out = set()
    for m in _NUM.findall(normalize(text) if text else ""):
        try:
            out.add(round(float(m.replace(",", "")), 2))
        except ValueError:
            pass
    return out


def allowed_numbers(payload) -> set[float]:
    blob = json.dumps(payload, ensure_ascii=False)
    nums = numbers_in(blob)
    # also allow rupee values in Indian grouping & percentages derived as-is
    return nums


def guard(text: str, allowed: set[float]) -> bool:
    return numbers_in(text).issubset(allowed)


def template(view: dict) -> dict:
    out = []
    for c in view["crops"]:
        fits = [r for r in c["reasons"] if r["type"] == "fit"]
        money = [r for r in c["reasons"] if r["type"] == "money"][:1]
        cautions = [r for r in c["reasons"] if r["type"] == "caution"][:2]
        if c["status"] in ("not_suitable", "conditional"):
            rs = (cautions + money + fits)[:4]
        else:
            rs = (fits[:4 - len(money) - len(cautions)] + money + cautions)[:4]
        out.append({"crop_id": c["crop_id"], "headline": c["headline"],
                    "reasons": [{"kind": r["type"], "text": r["text"]} for r in rs], "source": "template"})
    return {"crops": out, "source": "template"}


def _schema(ids: list[str]) -> dict:
    return {"type": "object", "properties": {"crops": {"type": "array", "items": {
        "type": "object", "properties": {
            "crop_id": {"type": "string", "enum": ids},
            "headline": {"type": "string", "description": "max 8 words"},
            "reasons": {"type": "array", "maxItems": 4, "items": {"type": "object", "properties": {
                "kind": {"type": "string", "enum": ["fit", "caution", "money"]},
                "text": {"type": "string", "description": "one short sentence, max 16 words"}},
                "required": ["kind", "text"]}}},
        "required": ["crop_id", "headline", "reasons"]}}}, "required": ["crops"]}


async def explain(view: dict, lang: str, timer: Timer | None = None) -> dict:
    timer = timer or Timer()
    base = template(view)
    if not get_settings().llm_enabled:
        return {**base, "timings_ms": timer.done()}
    facts = {"farmer": {k: v for k, v in view["facts"].items() if v not in (None, [], "")},
             "crops": [{"crop_id": c["crop_id"], "status": c["status"], "variety": c["variety"],
                        "sow_date": c["sow_date_label"], "best_window": c["window_label"],
                        "facts": [r["text"] for r in c["reasons"]],
                        "per_acre": {"yield_q_base": c["economics"]["yield_q_acre"]["base"],
                                     "cost_rs": c["economics"]["cost_rs_acre"],
                                     "net_rs_low_base_high": c["economics"]["net_rs_acre"]}} for c in view["crops"]]}
    allowed = allowed_numbers(facts)
    system = (f"You explain crop options to a small farmer in Punjab who may have low literacy. Write in {LANG_NAME[lang]}. "
              "Use very short, everyday sentences. Use ONLY the facts given — no new numbers, chemicals, prices or "
              "promises. Every number you write must appear in the facts exactly. Do not translate variety names. "
              "For each crop give a headline and 2-4 reasons ordered by importance; mention cautions honestly.")
    prompt = "FACTS (JSON):\n" + json.dumps(facts, ensure_ascii=False)
    try:
        with timer.span("llm_explain"):
            out = await gemini.generate_json(prompt, _schema([c["crop_id"] for c in view["crops"]]), system=system)
    except Exception as exc:
        log.warning("explain LLM failed: %s", exc)
        return {**base, "timings_ms": timer.done(), "llm_error": type(exc).__name__}
    by_id = {c["crop_id"]: c for c in out.get("crops", []) if c.get("crop_id") in crops()}
    result, dropped = [], 0
    for tc in base["crops"]:
        lc = by_id.get(tc["crop_id"])
        if not lc:
            result.append(tc)
            continue
        kept = [r for r in lc.get("reasons", []) if r.get("text") and guard(r["text"], allowed)]
        dropped += len(lc.get("reasons", [])) - len(kept)
        head_ok = guard(lc.get("headline", ""), allowed) and lc.get("headline")
        if kept:
            result.append({"crop_id": tc["crop_id"], "headline": lc["headline"] if head_ok else tc["headline"],
                           "reasons": kept, "source": "llm"})
        else:
            result.append(tc)
    src = "llm" if any(r["source"] == "llm" for r in result) else "template"
    return {"crops": result, "source": src, "guard_dropped": dropped, "timings_ms": timer.done()}
