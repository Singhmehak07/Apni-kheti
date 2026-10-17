"""Sarvam AI: Saaras speech-to-text and Bulbul text-to-speech (REST)."""
from __future__ import annotations

import base64
import json

from config import get_settings
from . import http

LANG_CODES = {"pa": "pa-IN", "hi": "hi-IN", "en": "en-IN"}


class SarvamError(RuntimeError):
    pass


async def stt(audio: bytes, filename: str, mime: str, lang: str | None, keyterms: list[str] | None = None) -> dict:
    s = get_settings()
    if not s.sarvam_api_key:
        raise SarvamError("SARVAM_API_KEY not set")
    data = {"model": s.sarvam_stt_model, "mode": s.sarvam_stt_mode,
            "language_code": LANG_CODES.get(lang or "", "unknown")}
    if keyterms and s.sarvam_stt_model.endswith("v4"):
        data["keyterms"] = json.dumps(keyterms[:50], ensure_ascii=False)
    resp = await http.request(
        "POST", f"{s.sarvam_base_url.rstrip('/')}/speech-to-text",
        headers={"api-subscription-key": s.sarvam_api_key},
        data=data, files={"file": (filename, audio, mime)}, timeout=s.http_timeout_s)
    if resp.status_code != 200:
        raise SarvamError(f"stt {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    return {"transcript": (body.get("transcript") or "").strip(), "language_code": body.get("language_code"),
            "request_id": body.get("request_id")}


async def tts(text: str, lang: str) -> bytes:
    s = get_settings()
    if not s.sarvam_api_key:
        raise SarvamError("SARVAM_API_KEY not set")
    body = {"text": text[:2500], "target_language_code": LANG_CODES.get(lang, "pa-IN"),
            "speaker": s.sarvam_tts_speaker, "model": s.sarvam_tts_model, "pace": s.tts_pace,
            "output_audio_codec": "mp3"}
    resp = await http.request("POST", f"{s.sarvam_base_url.rstrip('/')}/text-to-speech",
                              headers={"api-subscription-key": s.sarvam_api_key}, json=body, timeout=s.http_timeout_s)
    if resp.status_code != 200:
        raise SarvamError(f"tts {resp.status_code}: {resp.text[:300]}")
    audios = resp.json().get("audios") or []
    if not audios:
        raise SarvamError("tts returned no audio")
    return b"".join(base64.b64decode(a) for a in audios)
