"""Follow-up questions on the plan: Gemini grounded on the plan text, with a keyword fallback."""
from __future__ import annotations

import logging

from config import get_settings
from integrations import gemini
from integrations.http import Timer
from knowledge import load, t
from .explain import allowed_numbers, guard
from .text_norm import any_kw, normalize

log = logging.getLogger("assistant")
TOPICS = {
    "seed": (["ਬੀਜ", "ਕਿਸਮ", "बीज", "किस्म", "seed", "variety"], ["seed"]),
    "sow": (["ਬਿਜਾਈ", "ਬੀਜਣ", "ਬੀਜਾਂ", "बुवाई", "बोना", "बोएं", "बुआई", "sow", "sowing", "plant"], ["sow", "prep"]),
    "fert": (["ਖਾਦ", "ਯੂਰੀਆ", "ਡੀਏਪੀ", "ਸੁਪਰ", "खाद", "यूरिया", "डीएपी", "fertiliser", "fertilizer", "urea", "dap"], ["fert", "spray", "irr1", "irr2"]),
    "irr": (["ਪਾਣੀ", "ਸਿੰਚਾਈ", "ਰੌਣੀ", "पानी", "सिंचाई", "पलेवा", "water", "irrigation", "irrigate"], ["irr", "irr1", "irr2", "irr_rest", "prep"]),
    "weeds": (["ਨਦੀਨ", "ਗੋਡੀ", "ਘਾਹ", "ਕਸੀਆ", "खरपतवार", "गुड़ाई", "निराई", "weed", "hoe", "hoeing"], ["weeds", "thin"]),
    "watch": (["ਕੀੜਾ", "ਕੀੜੇ", "ਬਿਮਾਰੀ", "ਸਪਰੇਅ", "ਚੇਪਾ", "ਚੇਪੇ", "ਕੁੰਗੀ", "ਸੁੰਡੀ", "कीट", "कीड़ा", "बीमारी", "स्प्रे",
               "रोग", "चेपा", "माहू", "pest", "disease", "spray", "insect", "aphid", "rust"], ["watch"]),
    "harvest": (["ਵਾਢੀ", "ਕਟਾਈ", "ਪੱਕ", "कटाई", "पक", "harvest", "ripe"], ["harvest"]),
    "sell": (["ਭਾਅ", "ਮੰਡੀ", "ਵੇਚ", "ਕੀਮਤ", "ਐਮਐਸਪੀ", "भाव", "मंडी", "बेच", "कीमत", "एमएसपी", "price", "sell", "mandi", "msp", "rate"], ["sell"]),
    "weather": (["ਮੀਂਹ", "ਮੌਸਮ", "बारिश", "मौसम", "rain", "weather"], ["weather", "prep"]),
}
LANG_NAME = {"pa": "Punjabi (Gurmukhi)", "hi": "Hindi (Devanagari)", "en": "simple English"}


def keyword_answer(question: str, plan_view: dict, lang: str) -> dict:
    norm = normalize(question)
    ids: list[str] = []
    for kws, step_ids in TOPICS.values():
        if any_kw(norm, kws):
            ids += [s for s in step_ids if s not in ids]
    steps = [s for s in plan_view["steps"] if s["id"] in ids][:3]
    msgs = load("messages")["assistant"]
    if not steps:
        return {"answer": t(msgs["fallback"], lang), "source": "fallback", "steps": []}
    body = " ".join(f"{s['title']} ({s['when']}): {s['text']}" for s in steps)
    return {"answer": f"{t(msgs['from_plan'], lang)} {body}", "source": "plan", "steps": [s["id"] for s in steps]}


async def ask(question: str, plan_view: dict, lang: str, timer: Timer | None = None) -> dict:
    timer = timer or Timer()
    if not get_settings().llm_enabled:
        return {**keyword_answer(question, plan_view, lang), "timings_ms": timer.done()}
    ctx = {"crop": plan_view["name"], "variety": plan_view["variety"], "acres": plan_view["acres"],
           "steps": [{"title": s["title"], "when": s["when"], "text": s["text"]} for s in plan_view["steps"]]}
    help_line = t(load("messages")["assistant"]["fallback"], lang)
    system = (f"You are a farm helper. Answer the farmer in {LANG_NAME[lang]} in at most 3 short sentences, using ONLY "
              f"the plan below. If the plan does not cover the question, say so briefly and add: {help_line} "
              "Never invent doses, chemicals or numbers.")
    schema = {"type": "object", "properties": {"answer": {"type": "string"}, "covered": {"type": "boolean"}},
              "required": ["answer", "covered"]}
    try:
        with timer.span("llm_assistant"):
            out = await gemini.generate_json(f"PLAN: {ctx}\nQUESTION: {question}", schema, system=system)
        allowed = allowed_numbers(ctx) | allowed_numbers(help_line)
        if out.get("answer") and guard(out["answer"], allowed):
            return {"answer": out["answer"], "source": "llm", "covered": out.get("covered"), "timings_ms": timer.done()}
    except Exception as exc:
        log.warning("assistant LLM failed: %s", exc)
    return {**keyword_answer(question, plan_view, lang), "timings_ms": timer.done()}
