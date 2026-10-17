"""Script-aware normalisation so that STT spelling variants still match keywords.

Gurmukhi/Devanagari STT output varies (nukta, addak, tippi vs bindi, chandrabindu).
We fold these to a single canonical form before matching.
"""
from __future__ import annotations

import re
import unicodedata

_DIGITS = {ord(c): str(i) for i, c in enumerate("੦੧੨੩੪੫੬੭੮੯")}
_DIGITS.update({ord(c): str(i) for i, c in enumerate("०१२३४५६७८९")})
_DROP = {"\u0a3c", "\u093c", "\u0a71", "\u200c", "\u200d"}  # nukta (pa, hi), addak, ZWNJ, ZWJ
_MAP = {"\u0a70": "\u0a02", "\u0901": "\u0902", "।": " ", "॥": " "}
_PUNCT = re.compile(r"[\"'`’‘“”,;:!?()\[\]{}<>|/\\_*#@&=+~^%-]+")


def normalize(text: str | None) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFD", text).translate(_DIGITS)
    s = "".join(_MAP.get(ch, ch) for ch in s if ch not in _DROP)
    s = unicodedata.normalize("NFC", s).lower()
    s = s.replace("₹", " ₹ ")
    s = re.sub(r"(?<=\d),(?=\d)", "", s)  # 20,000 -> 20000
    s = _PUNCT.sub(" ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)  # keep decimal points only
    return re.sub(r"\s+", " ", s).strip()


def tokens(text: str) -> list[str]:
    return normalize(text).split()


def has_kw(norm_text: str, keyword: str, prefix: bool = True) -> bool:
    """Token-aware match. Multi-word keywords match as phrases; single words match a
    whole token or (for words of 3+ characters) a token prefix, to allow inflections
    such as ਬਠਿੰਡੇ / ਕਿੱਲਿਆਂ."""
    kw = normalize(keyword)
    if not kw:
        return False
    padded = f" {norm_text} "
    if " " in kw:
        return f" {kw} " in padded or (prefix and f" {kw}" in padded)
    for tok in norm_text.split():
        if tok == kw or (prefix and len(kw) >= 3 and tok.startswith(kw)):
            return True
    return False


def any_kw(norm_text: str, keywords, prefix: bool = True) -> bool:
    return any(has_kw(norm_text, k, prefix) for k in keywords)
