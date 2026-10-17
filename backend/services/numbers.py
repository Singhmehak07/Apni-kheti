"""Spoken-number parsing for Punjabi, Hindi and English (incl. ਡੇਢ/ਢਾਈ/ਸਾਢੇ style fractions)."""
from __future__ import annotations

import re

from .text_norm import normalize

_EN = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13,
    "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90, "a": None, "an": None,
}
_PA = {
    "ਇੱਕ": 1, "ਇਕ": 1, "ਦੋ": 2, "ਤਿੰਨ": 3, "ਚਾਰ": 4, "ਪੰਜ": 5, "ਛੇ": 6, "ਸੱਤ": 7, "ਅੱਠ": 8,
    "ਨੌਂ": 9, "ਨੌ": 9, "ਦਸ": 10, "ਗਿਆਰਾਂ": 11, "ਬਾਰਾਂ": 12, "ਤੇਰਾਂ": 13, "ਚੌਦਾਂ": 14,
    "ਪੰਦਰਾਂ": 15, "ਸੋਲਾਂ": 16, "ਸਤਾਰਾਂ": 17, "ਅਠਾਰਾਂ": 18, "ਉੱਨੀ": 19, "ਵੀਹ": 20,
    "ਪੱਚੀ": 25, "ਤੀਹ": 30, "ਪੈਂਤੀ": 35, "ਚਾਲੀ": 40, "ਪੰਜਾਹ": 50, "ਸੱਠ": 60, "ਸੱਤਰ": 70,
    "ਅੱਸੀ": 80, "ਨੱਬੇ": 90, "ਕੋਈ": None,
}
_HI = {
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "पाँच": 5, "छह": 6, "छः": 6, "छे": 6,
    "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "तेरह": 13, "चौदह": 14,
    "पंद्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18, "उन्नीस": 19, "बीस": 20, "पच्चीस": 25,
    "तीस": 30, "पैंतीस": 35, "चालीस": 40, "पचास": 50, "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
}
# Romanised (codemix STT output)
_ROMAN = {"ik": 1, "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "panj": 5,
          "paanch": 5, "panch": 5, "chhe": 6, "che": 6, "saat": 7, "sat": 7, "ath": 8, "aath": 8,
          "nau": 9, "das": 10, "vih": 20, "bees": 20, "bis": 20, "tih": 30, "tees": 30,
          "pachas": 50, "panjah": 50}
_FRACTION = {"ਡੇਢ": 1.5, "ਡੇਡ": 1.5, "डेढ़": 1.5, "डेढ": 1.5, "dedh": 1.5, "derh": 1.5,
             "ਢਾਈ": 2.5, "ਢਾਈਂ": 2.5, "ढाई": 2.5, "dhai": 2.5, "ਅੱਧਾ": 0.5, "ਅੱਧੀ": 0.5,
             "आधा": 0.5, "आधी": 0.5, "half": 0.5, "adha": 0.5}
_PLUS_HALF = {"ਸਾਢੇ", "साढ़े", "साढे", "sadhe", "saadhe"}
_PLUS_QUARTER = {"ਸਵਾ", "सवा", "sawa", "sava"}
_MINUS_QUARTER = {"ਪੌਣੇ", "पौने", "paune"}
_MULT = {"ਹਜ਼ਾਰ": 1000, "ਹਜਾਰ": 1000, "हज़ार": 1000, "हजार": 1000, "thousand": 1000, "hazar": 1000,
         "hazaar": 1000, "k": 1000, "ਲੱਖ": 100000, "लाख": 100000, "lakh": 100000, "lac": 100000,
         "ਸੌ": 100, "सौ": 100, "hundred": 100, "sau": 100}


def _norm_dict(d: dict) -> dict:
    return {normalize(k): v for k, v in d.items()}


WORDS = {**_norm_dict(_EN), **_norm_dict(_PA), **_norm_dict(_HI), **_ROMAN}
FRACTION = _norm_dict(_FRACTION)
PLUS_HALF = {normalize(x) for x in _PLUS_HALF}
PLUS_QUARTER = {normalize(x) for x in _PLUS_QUARTER}
MINUS_QUARTER = {normalize(x) for x in _MINUS_QUARTER}
MULT = _norm_dict(_MULT)
_NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
_NUM_K = re.compile(r"^(\d+(?:\.\d+)?)k$")


def find_numbers(text: str) -> list[float]:
    """Return the numbers spoken/written in order. 'ਸਾਢੇ ਪੰਜ' → 5.5, 'ਵੀਹ ਹਜ਼ਾਰ' → 20000,
    'two and a half' → 2.5, 'twenty five' → 25."""
    toks = normalize(text).split()
    out: list[float] = []
    i, modifier = 0, 0.0
    while i < len(toks):
        tok = toks[i]
        val = None
        if tok in PLUS_HALF:
            modifier = 0.5; i += 1; continue
        if tok in PLUS_QUARTER:
            modifier = 0.25; i += 1; continue
        if tok in MINUS_QUARTER:
            modifier = -0.25; i += 1; continue
        m = _NUM_K.match(tok)
        if _NUM_RE.match(tok):
            val = float(tok)
        elif m:
            val = float(m.group(1)) * 1000
        elif tok in FRACTION:
            val = FRACTION[tok]
        elif tok in WORDS and WORDS[tok] is not None:
            val = float(WORDS[tok])
            # english compounds: twenty five
            if val >= 20 and val % 10 == 0 and i + 1 < len(toks) and toks[i + 1] in WORDS and (WORDS[toks[i + 1]] or 0) < 10:
                val += WORDS[toks[i + 1]] or 0
                i += 1
        if val is None:
            # "and a half" after a number
            if tok in ("and", "ਤੇ", "ਅਤੇ", "और", "te") and out and i + 1 < len(toks):
                nxt = toks[i + 1:i + 3]
                if "half" in nxt or normalize("ਅੱਧਾ") in nxt or normalize("आधा") in nxt:
                    out[-1] += 0.5
                    i += 1 + (1 if len(nxt) > 1 and nxt[0] in ("a", "an") else 0) + 1
                    continue
            if tok in MULT and out:
                out[-1] *= MULT[tok]
            i += 1
            continue
        val += modifier
        modifier = 0.0
        # multiplier directly after
        j = i + 1
        while j < len(toks) and toks[j] in MULT:
            val *= MULT[toks[j]]
            j += 1
        out.append(round(val, 3))
        i = j
    return out
