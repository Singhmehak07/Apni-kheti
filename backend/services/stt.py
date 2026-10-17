"""Speech-to-text routing: Sarvam Saaras (default) → Gemini → browser (client-side)."""
from __future__ import annotations

import logging
import time

from config import get_settings
from integrations import gemini, sarvam
from knowledge import districts

log = logging.getLogger("stt")
TERMS = {
    "pa": ["ਕਿੱਲੇ", "ਏਕੜ", "ਕਨਾਲ", "ਨਹਿਰ", "ਟਿਊਬਵੈੱਲ", "ਕੱਲਰ", "ਖਾਰਾ", "ਰੇਤਲੀ", "ਮੈਰਾ", "ਕਣਕ", "ਸਰ੍ਹੋਂ", "ਛੋਲੇ", "ਜੌਂ", "ਝੋਨਾ", "ਨਰਮਾ", "ਟਰੈਕਟਰ"],
    "hi": ["किल्ले", "एकड़", "कनाल", "नहर", "ट्यूबवेल", "कल्लर", "खारा", "रेतीली", "दोमट", "गेहूं", "सरसों", "चना", "जौ", "धान", "नरमा", "ट्रैक्टर"],
    "en": ["killa", "acre", "kanal", "canal", "tubewell", "kallar", "wheat", "mustard", "gram", "barley", "paddy", "cotton"],
}


class STTUnavailable(RuntimeError):
    pass


def keyterms(lang: str) -> list[str]:
    names = [d.get(lang) or d["en"] for d in districts()]
    return (TERMS.get(lang, []) + names)[:50]


async def transcribe(audio: bytes, filename: str, mime: str, lang: str) -> dict:
    s = get_settings()
    provider = s.resolved_stt
    t0 = time.perf_counter()
    if provider == "browser":
        raise STTUnavailable("no server STT configured")
    errors = []
    order = [provider] + [p for p in ("sarvam", "gemini") if p != provider]
    for p in order:
        try:
            if p == "sarvam" and s.sarvam_api_key:
                r = await sarvam.stt(audio, filename, mime, lang, keyterms(lang))
                return {"transcript": r["transcript"], "provider": "sarvam", "model": s.sarvam_stt_model,
                        "ms": round((time.perf_counter() - t0) * 1000, 1)}
            if p == "gemini" and s.gemini_api_key:
                text = await gemini.transcribe(audio, mime, lang, keyterms(lang))
                return {"transcript": text, "provider": "gemini", "model": s.gemini_stt_model,
                        "ms": round((time.perf_counter() - t0) * 1000, 1)}
        except Exception as exc:
            log.warning("stt %s failed: %s", p, exc)
            errors.append(f"{p}: {type(exc).__name__}")
    raise STTUnavailable("; ".join(errors) or "no provider")
