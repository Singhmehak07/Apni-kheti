"""Soil Health Card reading: PDF text layer first (fast, free), Gemini vision for photos/scans."""
from __future__ import annotations

import io
import logging
import re

from config import get_settings
from integrations import gemini

log = logging.getLogger("report")

PARAMS = {
    "ph": {"label": "pH", "unit": "", "range": (3.0, 11.0),
           "re": r"(?<![a-z])p\.?\s?h(?![a-z])|ਪੀ\.?\s?ਐਚ|पी\.?\s?एच"},
    "ec": {"label": "EC", "unit": "dS/m", "range": (0.0, 20.0),
           "re": r"electrical\s+conductivity|(?<![a-z])e\.?\s?c\.?(?![a-z])|ਬਿਜਲਈ ਚਾਲਕਤਾ|विद्युत चालकता"},
    "oc": {"label": "Organic carbon", "unit": "%", "range": (0.0, 5.0),
           "re": r"organic\s+carbon|(?<![a-z])o\.?\s?c\.?(?![a-z])|ਜੈਵਿਕ ਕਾਰਬਨ|जैविक कार्बन"},
    "n": {"label": "Nitrogen (N)", "unit": "kg/ha", "range": (0.0, 1500.0),
          "re": r"nitrogen|\(\s*n\s*\)|ਨਾਈਟ੍ਰੋਜਨ|नाइट्रोजन"},
    "p": {"label": "Phosphorus (P)", "unit": "kg/ha", "range": (0.0, 400.0),
          "re": r"phosphorus|\(\s*p\s*\)|ਫਾਸਫੋਰਸ|फास्फोरस|फॉस्फोरस"},
    "k": {"label": "Potassium (K)", "unit": "kg/ha", "range": (0.0, 2500.0),
          "re": r"potassium|potash|\(\s*k\s*\)|ਪੋਟਾਸ਼|पोटाश|पोटेशियम"},
    "s": {"label": "Sulphur (S)", "unit": "ppm", "range": (0.0, 300.0),
          "re": r"sulphur|sulfur|\(\s*s\s*\)|ਗੰਧਕ|गंधक|सल्फर"},
    "zn": {"label": "Zinc (Zn)", "unit": "ppm", "range": (0.0, 50.0),
           "re": r"zinc|(?<![a-z])zn(?![a-z])|ਜ਼ਿੰਕ|ਜਿੰਕ|जिंक|ज़िंक"},
    "fe": {"label": "Iron (Fe)", "unit": "ppm", "range": (0.0, 300.0),
           "re": r"(?<![a-z])iron|(?<![a-z])fe(?![a-z])|ਲੋਹਾ|लोहा"},
    "cu": {"label": "Copper (Cu)", "unit": "ppm", "range": (0.0, 50.0),
           "re": r"copper|(?<![a-z])cu(?![a-z])|ਤਾਂਬਾ|तांबा"},
    "mn": {"label": "Manganese (Mn)", "unit": "ppm", "range": (0.0, 200.0),
           "re": r"manganese|(?<![a-z])mn(?![a-z])|ਮੈਂਗਨੀਜ਼|मैंगनीज"},
    "b": {"label": "Boron (B)", "unit": "ppm", "range": (0.0, 20.0),
          "re": r"boron|\(\s*b\s*\)|ਬੋਰੋਨ|बोरॉन|बोरोन"},
}
_RATIO = re.compile(r"\(?\s*1\s*:\s*\d+(?:\.\d+)?\s*\)?")
_NUMBER = re.compile(r"(?<![a-z0-9.])(\d+(?:\.\d+)?)(?![0-9])", re.I)
_RATING = re.compile(r"\b(very\s+low|low|medium|high|very\s+high|normal|deficient|sufficient|alkaline|acidic|saline|neutral)\b", re.I)


def flags(params: dict) -> list[str]:
    out = []
    if (params.get("ec") or {}).get("value", 0) > 0.8:
        out.append("saline")
    if (params.get("ph") or {}).get("value", 0) > 9.3:
        out.append("alkali")
    return out


def parse_text(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    found: dict[str, dict] = {}
    for i, raw in enumerate(lines):
        line = _RATIO.sub(" ", raw.lower())
        hits = []
        for key, spec in PARAMS.items():
            for m in re.finditer(spec["re"], line, re.I):
                hits.append((m.start(), m.end(), key))
        hits.sort()
        # drop overlapping/duplicate label hits, keep first per position
        dedup = []
        for h in hits:
            if dedup and h[0] < dedup[-1][1]:
                continue
            dedup.append(h)
        for j, (s, e, key) in enumerate(dedup):
            if key in found:
                continue
            seg_end = dedup[j + 1][0] if j + 1 < len(dedup) else len(line)
            seg = line[e:seg_end]
            m = _NUMBER.search(seg)
            if not m and j + 1 == len(dedup) and i + 1 < len(lines):
                seg = _RATIO.sub(" ", lines[i + 1].lower())
                m = _NUMBER.search(seg)
            if not m:
                continue
            v = float(m.group(1))
            lo, hi = PARAMS[key]["range"]
            if not (lo <= v <= hi):
                continue
            rating = _RATING.search(seg[m.end():])
            found[key] = {"value": v, "unit": PARAMS[key]["unit"], "label": PARAMS[key]["label"],
                          "rating": rating.group(1).title() if rating else None}
    return found


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join((p.extract_text() or "") for p in reader.pages[:4])


VISION_SCHEMA = {"type": "object", "properties": {
    **{k: {"type": "number"} for k in PARAMS}, "is_soil_report": {"type": "boolean"}}, "required": ["is_soil_report"]}


async def _vision(data: bytes, mime: str) -> dict:
    prompt = ("This is a photo or scan of an Indian Soil Health Card / soil test report. Read the TEST VALUE for each "
              "parameter (pH, EC in dS/m, organic carbon %, N, P, K in kg/ha, S, Zn, Fe, Cu, Mn, B in ppm). Omit any "
              "value you cannot read clearly. Do not guess. Do not return names or personal details.")
    out = await gemini.generate_json(prompt, VISION_SCHEMA, model=get_settings().gemini_vision_model,
                                     extra_parts=[gemini.inline(data, mime)], timeout=20)
    if not out.get("is_soil_report"):
        return {}
    res = {}
    for k, spec in PARAMS.items():
        v = out.get(k)
        if isinstance(v, (int, float)) and spec["range"][0] <= v <= spec["range"][1]:
            res[k] = {"value": float(v), "unit": spec["unit"], "label": spec["label"], "rating": None}
    return res


async def read_report(data: bytes, filename: str, mime: str) -> dict:
    method, params = None, {}
    is_pdf = mime == "application/pdf" or filename.lower().endswith(".pdf") or data[:4] == b"%PDF"
    if is_pdf:
        try:
            params = parse_text(_pdf_text(data))
            method = "pdf_text"
        except Exception as exc:
            log.warning("pdf text failed: %s", exc)
    if len(params) < 2 and get_settings().llm_enabled:
        try:
            params = await _vision(data, "application/pdf" if is_pdf else (mime or "image/jpeg"))
            method = "gemini_vision"
        except Exception as exc:
            log.warning("vision failed: %s", exc)
    status = "ok" if len(params) >= 2 else ("partial" if params else "unreadable")
    return {"status": status, "method": method, "params": params, "flags": flags(params),
            "count": len(params), "of": len(PARAMS)}
