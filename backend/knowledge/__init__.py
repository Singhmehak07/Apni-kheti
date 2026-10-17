"""Loads the curated JSON knowledge base once (crops, districts, questions, texts)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DIR = Path(__file__).resolve().parent
LANGS = ("pa", "hi", "en")


@lru_cache
def load(name: str) -> dict:
    with open(DIR / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def crops() -> dict:
    return load("crops")["crops"]


def districts() -> list[dict]:
    return load("districts")["districts"]


def district_by_id(did: str | None) -> dict | None:
    return next((d for d in districts() if d["id"] == did), None)


def district_zone(did: str | None) -> str:
    meta = load("districts")
    if did in meta["south_western"]:
        return "south_western"
    if did in meta["sub_mountainous"]:
        return "sub_mountainous"
    return "central"


def t(obj: dict | str | None, lang: str) -> str:
    """Pick a language from an {en, pa, hi} dict, falling back to English."""
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    return obj.get(lang) or obj.get("en") or ""
