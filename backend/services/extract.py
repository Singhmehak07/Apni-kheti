"""Deterministic (no-LLM) answer understanding: the fast path for every question.

parse_field() returns a ParseResult for the question being asked; opportunistic()
pulls distinctive extra facts (district, land, water, crops) out of the same answer
so one sentence can fill several fields.
"""
from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from datetime import date, timedelta

from knowledge import districts
from .numbers import find_numbers
from .text_norm import any_kw, has_kw, normalize

DONT_KNOW = ["ਪਤਾ ਨਹੀਂ", "ਨਹੀਂ ਪਤਾ", "ਪਤਾ ਨੀ", "ਨੀ ਪਤਾ", "ਪਤਾ ਨਹੀ", "ਨਹੀ ਪਤਾ", "ਜਾਣਕਾਰੀ ਨਹੀਂ", "ਮੈਨੂੰ ਨਹੀਂ ਪਤਾ",
             "पता नहीं", "नहीं पता", "मालूम नहीं", "नहीं मालूम", "पता नही", "जानकारी नहीं",
             "don't know", "dont know", "do not know", "not sure", "no idea", "dunno", "skip",
             "pata nahi", "nahi pata", "pata ni", "malum nahi"]
NEG = ["ਨਹੀਂ", "ਨਹੀ", "ਨੀ", "ਨਾ", "ਨਹੀਂਜੀ", "नहीं", "नही", "ना", "no", "nahi", "nahin", "not", "none", "nope"]
YES = ["ਹਾਂ", "ਹਾਂਜੀ", "ਹਾਂ ਜੀ", "ਜੀ ਹਾਂ", "ਹੈਗਾ", "ਹੈਗੀ", "ਹੈ", "हां", "हाँ", "हां जी", "जी हां", "है",
       "yes", "yeah", "yep", "haan", "han", "ha", "have", "i have"]

LEX: dict[str, dict[str, list[str]]] = {
    "soil_type": {
        "salt_affected": ["ਕੱਲਰ", "ਕਲਰ", "ਖਾਰੀ", "ਸ਼ੋਰਾ", "ਲੂਣੀ", "कल्लर", "कलर", "खारी", "ऊसर", "रेह", "लवणीय",
                          "kallar", "kalar", "salty", "saline", "alkaline", "usar", "khari"],
        "sandy": ["ਰੇਤਲੀ", "ਰੇਤਾ", "ਰੇਤ", "ਟਿੱਬਾ", "ਟਿੱਬੇ", "ਟਿੱਬਿਆਂ", "ਭੂਰ", "ਰੇਤਲੀਆਂ", "रेतीली", "रेत", "बलुई", "टिब्बा",
                  "टिब्बे", "sandy", "sand", "retli", "ret", "tibba", "tibbe", "light soil"],
        "clay": ["ਰੋਹੀ", "ਚੀਕਣੀ", "ਭਾਰੀ", "ਚੀਕਨੀ", "ਮਟਿਆਰ", "चिकनी", "भारी", "मटियार", "काली", "clay", "heavy",
                 "chikni", "rohi", "bhari", "matiyar"],
        "loam": ["ਮੈਰਾ", "ਮੈਰ੍ਹਾ", "ਮੈਰਾ", "ਦੋਸ਼ਾਹੀ", "ਦੁਮਟ", "ਦੋਮਟ", "ਵਧੀਆ ਜ਼ਮੀਨ", "दोमट", "मैरा", "loam", "loamy",
                 "maira", "dumat", "domat", "medium"],
    },
    "water_source": {
        "both": ["ਦੋਵੇਂ", "ਦੋਨੋਂ", "ਦੋਨੋ", "ਦੋਵੇਂ ਹੀ", "दोनों", "दोनो", "both"],
        "rain": ["ਮੀਂਹ", "ਬਾਰਸ਼", "ਬਾਰਿਸ਼", "ਬਰਾਨੀ", "ਬਾਰਾਨੀ", "ਅਸਮਾਨੀ", "बारिश", "वर्षा", "बरानी", "बारानी",
                 "rain", "rainfed", "barani", "baarish", "mihn"],
        "canal": ["ਨਹਿਰ", "ਨਹਿਰੀ", "ਨਹਿਰੀ ਪਾਣੀ", "ਖਾਲ", "ਸੂਆ", "नहर", "नहरी", "canal", "nahar", "nehar", "nehri", "nahri"],
        "tubewell": ["ਟਿਊਬਵੈੱਲ", "ਟਿਊਬਵੈਲ", "ਟਿਊਬਲ", "ਟੂਵੈੱਲ", "ਟਿਊਬ", "ਮੋਟਰ", "ਬੋਰ", "ਬੋਰਵੈੱਲ", "ट्यूबवेल", "ट्यूब",
                     "मोटर", "बोरवेल", "बोर", "tubewell", "tube well", "tubwell", "motor", "bore", "borewell"],
    },
    "water_quality": {
        "salty": ["ਖਾਰਾ", "ਖਾਰਾ ਪਾਣੀ", "ਕੌੜਾ", "ਲੂਣਾ", "ਮਾੜਾ", "खारा", "कड़वा", "नमकीन", "salty", "saline", "khara",
                  "brackish", "bad"],
        "sweet": ["ਮਿੱਠਾ", "ਮਿੱਠਾ ਪਾਣੀ", "ਵਧੀਆ", "ਚੰਗਾ", "ਠੀਕ", "मीठा", "अच्छा", "ठीक", "sweet", "good", "fine", "mitha", "meetha"],
    },
    "usual_crop": {
        "wheat": ["ਕਣਕ", "ਗੇਹੂੰ", "गेहूं", "गेहूँ", "गेंहू", "wheat", "kanak", "gehun", "gehu"],
        "raya": ["ਰਾਇਆ", "ਸਰ੍ਹੋਂ", "ਸਰੋਂ", "ਸਰ੍ਹੋਂ", "ਸਰੋਂ", "ਸਰਸੋਂ", "ਰਾਈ", "सरसों", "सरसो", "राया", "राई",
                 "mustard", "raya", "sarson", "sarhon", "rai"],
        "gram": ["ਛੋਲੇ", "ਛੋਲਿਆਂ", "ਚਣੇ", "ਚਨੇ", "ਚਣਾ", "चना", "चने", "छोले", "gram", "chana", "chickpea", "chole", "chhole"],
        "barley": ["ਜੌਂ", "ਜੌ", "जौ", "barley", "jau", "jaun", "jon"],
        "potato": ["ਆਲੂ", "आलू", "potato", "aloo", "alu"],
    },
    "previous_crop": {
        "basmati": ["ਬਾਸਮਤੀ", "ਬਾਸਮਤੀ ਝੋਨਾ", "बासमती", "basmati", "1121", "1509", "1718"],
        "paddy": ["ਝੋਨਾ", "ਝੋਨੇ", "ਜੀਰੀ", "ਧਾਨ", "ਚੌਲ", "ਪਰਮਲ", "धान", "चावल", "जीरी", "परमल", "paddy", "rice",
                  "jhona", "jhone", "dhan", "parmal", "jiri"],
        "cotton": ["ਨਰਮਾ", "ਨਰਮੇ", "ਕਪਾਹ", "ਕਪਾਸ", "ਦੇਸੀ ਕਪਾਹ", "नरमा", "कपास", "cotton", "narma", "kapas", "kapah"],
        "maize": ["ਮੱਕੀ", "ਮਕੀ", "ਛੱਲੀਆਂ", "मक्का", "मक्की", "maize", "corn", "makki", "makka"],
        "fallow": ["ਖਾਲੀ", "ਵਿਹਲਾ", "ਕੁਝ ਨਹੀਂ", "ਕੁਛ ਨਹੀਂ", "खाली", "कुछ नहीं", "fallow", "empty", "nothing", "khali"],
    },
    "tractor": {
        "rent": ["ਕਿਰਾਏ", "ਕਿਰਾਇਆ", "ਕਿਰਾਏ ਤੇ", "ਭਾੜੇ", "ਭਾੜਾ", "ਮੰਗ ਕੇ", "ਕਸਟਮ", "किराए", "किराया", "किराये", "भाड़े",
                 "rent", "rented", "hire", "hired", "kiraye", "kiraya", "custom"],
        "none": ["ਨਹੀਂ ਹੈ", "ਨਹੀਂ", "ਕੋਈ ਨਹੀਂ", "ਨਹੀ", "ਨੀ", "नहीं है", "नहीं", "कोई नहीं", "no", "none", "nahi", "don't have", "dont have"],
        "own": ["ਆਪਣਾ", "ਅਪਣਾ", "ਆਪਣੇ", "ਆਪਦਾ", "ਹੈਗਾ", "ਹੈ", "ਹਾਂ", "अपना", "है", "हां", "हाँ", "own", "yes", "have", "apna", "haan"],
    },
}
ACRE_UNITS = {
    "killa": (["ਕਿੱਲੇ", "ਕਿੱਲਾ", "ਕਿੱਲਿਆਂ", "ਕਿਲ੍ਹੇ", "ਕਿਲੇ", "ਕਿੱਲੇਆਂ", "किल्ले", "किल्ला", "किले", "killa", "kille", "killey", "kila", "kile"], 1.0),
    "acre": (["ਏਕੜ", "ਏਕੜਾਂ", "एकड़", "एकड", "acre", "acres", "ekad", "ekar", "ekarh"], 1.0),
    "kanal": (["ਕਨਾਲ", "ਕਨਾਲਾਂ", "कनाल", "kanal", "kanals"], 0.125),
    "marla": (["ਮਰਲੇ", "ਮਰਲਾ", "मरला", "मरले", "marla", "marle"], 1 / 160),
    "hectare": (["ਹੈਕਟੇਅਰ", "ਹੈਕਟੇਅਰ", "हेक्टेयर", "hectare", "hectares", "ha"], 2.471),
    "bigha": (["ਵਿੱਘਾ", "ਵਿੱਘੇ", "ਬਿੱਘਾ", "ਬਿੱਘੇ", "बीघा", "बीघे", "bigha", "bighe", "vigha"], None),
}
MONTHS = {
    10: ["ਅਕਤੂਬਰ", "अक्टूबर", "अक्तूबर", "october", "oct", "aktubar"],
    11: ["ਨਵੰਬਰ", "ਨਵੰਬਰ", "नवंबर", "नवम्बर", "november", "nov", "navambar"],
    12: ["ਦਸੰਬਰ", "दिसंबर", "दिसम्बर", "december", "dec", "dasambar"],
    1: ["ਜਨਵਰੀ", "जनवरी", "january", "jan"],
}
FIRST_HALF = ["ਪਹਿਲੇ", "ਪਹਿਲਾ", "ਸ਼ੁਰੂ", "ਸ਼ੁਰੂਆਤ", "ਸ਼ੁਰੂ ਵਿੱਚ", "पहले", "शुरू", "शुरुआत", "first", "start", "early", "beginning"]
SECOND_HALF = ["ਅਖੀਰ", "ਅਖ਼ੀਰ", "ਆਖਰੀ", "ਆਖ਼ਰੀ", "ਅੰਤ", "ਦੂਜੇ", "ਪਿਛਲੇ", "आखिर", "आख़िर", "अंत", "आखरी", "दूसरे",
               "end", "last", "late", "second half"]
NOW = ["ਹੁਣੇ", "ਹੁਣ", "ਇਸ ਹਫ਼ਤੇ", "ਤਿਆਰ ਹੈ", "ਤਿਆਰ", "ਅੱਜ", "ਕੱਲ੍ਹ", "अभी", "इस हफ्ते", "तैयार है", "तैयार", "आज", "कल",
       "now", "ready", "this week", "today", "tomorrow"]
DAY_WORDS = ["ਦਿਨ", "ਦਿਨਾਂ", "ਦਿਨਾ", "दिन", "दिनों", "day", "days", "din"]
WEEK_WORDS = ["ਹਫ਼ਤੇ", "ਹਫ਼ਤਾ", "ਹਫਤੇ", "ਹਫਤਾ", "ਹਫ਼ਤਿਆਂ", "हफ्ते", "हफ़्ते", "हफ्ता", "सप्ताह", "week", "weeks", "hafte"]
MONEY_HINT = ["₹", "ਰੁਪਏ", "ਰੁਪਈਏ", "ਹਜ਼ਾਰ", "ਹਜਾਰ", "ਲੱਖ", "रुपये", "रुपए", "हज़ार", "हजार", "लाख", "rs", "rupees", "rupee",
              "thousand", "hazar", "lakh", "inr"]
MANY = ["ਬਹੁਤ", "ਜਿੰਨੇ ਮਰਜ਼ੀ", "ਜਿੰਨੇ ਚਾਹੀਏ", "ਪੂਰੇ", "ਜਿੰਨੇ ਲੋੜ", "बहुत", "जितने चाहें", "जितनी चाहें", "पूरे", "many", "plenty",
        "as many", "enough", "unlimited", "full"]


@dataclass
class ParseResult:
    status: str  # ok | unknown | unclear | invalid
    value: object = None
    code: str | None = None  # reason for unclear/invalid (e.g. bigha_unit)
    extra: dict = field(default_factory=dict)


def is_dont_know(norm: str) -> bool:
    return any_kw(norm, DONT_KNOW, prefix=False)


def _neg(norm: str) -> bool:
    return any_kw(norm, NEG, prefix=False)


def _lex(field_id: str, norm: str) -> str | None:
    for opt, kws in LEX[field_id].items():
        if any_kw(norm, kws):
            return opt
    return None


def match_district(norm: str) -> str | None:
    best = None
    for d in districts():
        for alias in d["aliases"] + [d["en"], d["pa"], d["hi"]]:
            if has_kw(norm, alias, prefix=True):
                a = normalize(alias)
                if best is None or len(a) > best[1]:
                    best = (d["id"], len(a))
    if best:
        return best[0]
    # fuzzy fallback for STT spelling drift (e.g. "bathindaa", "ਬਠੰਡਾ")
    alias_map = {}
    for d in districts():
        for alias in d["aliases"]:
            alias_map[normalize(alias)] = d["id"]
    toks = norm.split()
    grams = toks + [" ".join(toks[i:i + 2]) for i in range(len(toks) - 1)] + [" ".join(toks[i:i + 3]) for i in range(len(toks) - 2)]
    for g in grams:
        if len(g) < 4:
            continue
        hit = difflib.get_close_matches(g, alias_map.keys(), n=1, cutoff=0.84)
        if hit:
            return alias_map[hit[0]]
    return None


def _yes_no(norm: str) -> str | None:
    if _neg(norm):
        return "no"
    if any_kw(norm, YES, prefix=False):
        return "yes"
    return None


def parse_land(norm: str, require_unit: bool = False) -> ParseResult:
    unit, factor = None, None
    for uid, (kws, f) in ACRE_UNITS.items():
        if any_kw(norm, kws):
            unit, factor = uid, f
            break
    all_nums = find_numbers(norm)
    nums = [n for n in all_nums if n > 0]
    if unit is None and require_unit:
        return ParseResult("unclear")
    if all_nums and not nums:
        return ParseResult("invalid", code="invalid_area")
    if not nums:
        return ParseResult("unclear")
    if unit == "bigha":
        return ParseResult("invalid", code="bigha_unit")
    unit = unit or "killa"
    factor = factor if factor is not None else 1.0
    amount = nums[0]
    # "5 ਕਿੱਲੇ 4 ਕਨਾਲ" → add kanal part
    acres = amount * factor
    if unit in ("killa", "acre") and len(nums) > 1 and any_kw(norm, ACRE_UNITS["kanal"][0]):
        acres += nums[1] * 0.125
    acres = round(acres, 3)
    if acres <= 0 or acres > 500:
        return ParseResult("invalid", code="invalid_area")
    return ParseResult("ok", {"acres": acres, "amount": amount, "unit": unit})


def bucket_irrigations(n: float) -> str:
    if n <= 0:
        return "0"
    if n <= 2:
        return "1-2"
    if n <= 4:
        return "3-4"
    return "5+"


IRR_VALUE = {"0": 0, "1-2": 2, "3-4": 4, "5+": 5}


def _season_date(today: date, month: int, day: int) -> date:
    year = today.year if month >= 7 else today.year + 1
    if month >= 7 and today.month < 7:
        year = today.year - 1
    return date(year, month, day)


def field_ready_options(today: date, opts: list[dict]) -> list[dict]:
    out = []
    for o in opts:
        if o["id"] == "this_week":
            out.append({**o, "date": (today + timedelta(days=3)).isoformat()})
            continue
        sm, sd = map(int, o["start"].split("-"))
        em, ed = map(int, o["end"].split("-"))
        start, end = _season_date(today, sm, sd), _season_date(today, em, ed)
        if end <= today + timedelta(days=6):
            continue  # already covered by "this week" or in the past
        start = max(start, today + timedelta(days=7))
        mid = start + (end - start) // 2
        out.append({**o, "date": mid.isoformat()})
    return out


def option_for_date(d: date, options: list[dict]) -> str | None:
    best = None
    for o in options:
        od = date.fromisoformat(o["date"])
        if best is None or abs((od - d).days) < abs((date.fromisoformat(best["date"]) - d).days):
            best = o
    return best["id"] if best else None


def parse_field_ready(norm: str, today: date) -> ParseResult:
    nums = find_numbers(norm)
    month = next((m for m, kws in MONTHS.items() if any_kw(norm, kws)), None)
    if month:
        day_nums = [int(n) for n in nums if 1 <= n <= 31 and float(n).is_integer()]
        if day_nums and not any_kw(norm, WEEK_WORDS):
            d = _season_date(today, month, day_nums[0])
        elif any_kw(norm, FIRST_HALF) and any_kw(norm, WEEK_WORDS):
            d = _season_date(today, month, 4)
        elif any_kw(norm, SECOND_HALF) and any_kw(norm, WEEK_WORDS):
            d = _season_date(today, month, 26)
        elif any_kw(norm, FIRST_HALF):
            d = _season_date(today, month, 8)
        elif any_kw(norm, SECOND_HALF):
            d = _season_date(today, month, 23)
        elif any_kw(norm, WEEK_WORDS) and day_nums:
            d = _season_date(today, month, min(28, (day_nums[0] - 1) * 7 + 4))
        elif month == 10:
            d = _season_date(today, 10, 28)
        elif month == 12:
            d = _season_date(today, 12, 10)
        elif month == 1:
            d = _season_date(today, 1, 8)
        else:
            return ParseResult("unclear", code="month_half")
        if d < today:
            d = today
        return ParseResult("ok", {"date": d.isoformat()})
    if nums and any_kw(norm, DAY_WORDS):
        return ParseResult("ok", {"date": (today + timedelta(days=int(nums[0]))).isoformat()})
    if nums and any_kw(norm, WEEK_WORDS):
        return ParseResult("ok", {"date": (today + timedelta(days=int(nums[0] * 7))).isoformat()})
    if any_kw(norm, NOW, prefix=False):
        return ParseResult("ok", {"date": (today + timedelta(days=3)).isoformat()})
    return ParseResult("unclear")


def parse_budget(norm: str) -> ParseResult:
    nums = [n for n in find_numbers(norm) if n > 0]
    if not nums:
        return ParseResult("unclear")
    v = max(nums)
    if v < 100 and any_kw(norm, MONEY_HINT):
        v *= 1000  # "20 हज़ार" handled by multiplier; "20 rupees thousand" edge
    if v < 1000:
        v *= 1000 if v <= 100 else 1  # "ਵੀਹ" said alone to a money question means thousands
    if v < 1000 or v > 200000:
        return ParseResult("invalid", code="invalid_budget")
    return ParseResult("ok", {"rs_per_acre": int(round(v, -2))})


def parse_irrigations(norm: str) -> ParseResult:
    if any_kw(norm, MANY):
        return ParseResult("ok", {"bucket": "5+", "count": 5})
    nums = find_numbers(norm)
    if nums:
        n = max(nums)
        if n > 20:
            return ParseResult("invalid", code="invalid_irrigations")
        b = bucket_irrigations(n)
        return ParseResult("ok", {"bucket": b, "count": IRR_VALUE[b] if n > 5 else n})
    if any_kw(norm, ["ਕੋਈ ਨਹੀਂ", "ਇੱਕ ਵੀ ਨਹੀਂ", "कोई नहीं", "एक भी नहीं", "none", "zero"], prefix=False) or _neg(norm):
        return ParseResult("ok", {"bucket": "0", "count": 0})
    return ParseResult("unclear")


def parse_field(field_id: str, text: str, today: date) -> ParseResult:
    norm = normalize(text)
    if not norm:
        return ParseResult("unclear")
    if is_dont_know(norm):
        return ParseResult("unknown")
    if field_id == "soil_report":
        v = _yes_no(norm)
        return ParseResult("ok", v) if v else ParseResult("unclear")
    if field_id == "district":
        d = match_district(norm)
        return ParseResult("ok", d) if d else ParseResult("unclear")
    if field_id == "land_area":
        return parse_land(norm)
    if field_id == "soil_type":
        v = _lex("soil_type", norm)
        if v is None:
            return ParseResult("unclear")
        salt = v == "salt_affected" or any_kw(norm, LEX["soil_type"]["salt_affected"])
        if v == "salt_affected":
            # "sandy and a bit kallar" → keep texture, flag salt
            tex = next((o for o in ("sandy", "clay", "loam") if any_kw(norm, LEX["soil_type"][o])), None)
            if tex:
                return ParseResult("ok", tex, extra={"salt_concern": True})
        return ParseResult("ok", v, extra={"salt_concern": salt})
    if field_id == "water_source":
        canal = any_kw(norm, LEX["water_source"]["canal"])
        tube = any_kw(norm, LEX["water_source"]["tubewell"])
        if (canal and tube) or any_kw(norm, LEX["water_source"]["both"]):
            return ParseResult("ok", "both")
        if canal:
            return ParseResult("ok", "canal")
        if tube:
            return ParseResult("ok", "tubewell")
        if any_kw(norm, LEX["water_source"]["rain"]):
            return ParseResult("ok", "rain")
        return ParseResult("unclear")
    if field_id == "water_quality":
        v = _lex("water_quality", norm)
        return ParseResult("ok", v) if v else ParseResult("unclear")
    if field_id == "irrigations":
        return parse_irrigations(norm)
    if field_id in ("usual_crop", "previous_crop"):
        v = _lex(field_id, norm)
        if v:
            return ParseResult("ok", v)
        if any_kw(norm, ["ਹੋਰ", "और", "अन्य", "other", "something else"], prefix=False):
            return ParseResult("ok", "other")
        return ParseResult("unclear")
    if field_id == "field_ready":
        return parse_field_ready(norm, today)
    if field_id == "tractor":
        v = _lex("tractor", norm)
        return ParseResult("ok", v) if v else ParseResult("unclear")
    if field_id == "budget":
        return parse_budget(norm)
    return ParseResult("unclear")


OPPORTUNISTIC = ("district", "land_area", "water_source", "soil_type", "previous_crop", "usual_crop")


def opportunistic(text: str, exclude: str) -> dict[str, ParseResult]:
    """Distinctive facts mentioned in passing ("ਬਠਿੰਡੇ ਵਿੱਚ 5 ਕਿੱਲੇ, ਨਹਿਰੀ ਪਾਣੀ")."""
    norm = normalize(text)
    found: dict[str, ParseResult] = {}
    if not norm or is_dont_know(norm):
        return found
    for fid in OPPORTUNISTIC:
        if fid == exclude:
            continue
        if fid == "district":
            d = match_district(norm)
            if d:
                found[fid] = ParseResult("ok", d)
        elif fid == "land_area":
            r = parse_land(norm, require_unit=True)
            if r.status == "ok":
                found[fid] = r
        elif fid in ("usual_crop", "previous_crop"):
            v = _lex(fid, norm)
            if v:
                found[fid] = ParseResult("ok", v)
        else:
            r = parse_field(fid, text, date.today())
            if r.status == "ok":
                found[fid] = r
    return found
